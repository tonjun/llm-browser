"""Post: structured data (author, date, title, content, media, comments) for
the social-media/forum post open in the browser.

Complements ``extract`` (readability-style Markdown, which flattens the
structure): this returns one JSON object. Extraction is layered - a generic
extractor (JSON-LD, OpenGraph/meta tags, then DOM heuristics) runs on every
page as the baseline, and a per-site adapter for known platforms (Reddit, X,
Hacker News, Facebook, Instagram) overrides it where the site's own markup
gives better data. Like ``search --json``, the extractors are JS snippets run
via ``d.evaluate`` and the results are normalized in Python.
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import with_driver

# Shared JS helpers, prepended to every extractor. `txt` keeps line breaks
# (post bodies are paragraphs) while collapsing runs of spaces; `ownText`
# reads an element's text minus any nested comment elements matching
# `nestedSel`, so a comment's text doesn't include its replies.
_PRELUDE = r"""
const txt = e => e
  ? (e.innerText || e.textContent || '')
      .replace(/[ \t\f\v\u00a0]+/g, ' ')
      .replace(/ ?\n ?/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  : '';
const abs = u => { try { return u ? new URL(u, location.href).href : ''; } catch (e) { return ''; } };
const attr = (e, n) => (e ? e.getAttribute(n) : null);
const ownText = (el, nestedSel) => {
  const c = el.cloneNode(true);
  if (nestedSel) c.querySelectorAll(nestedSel).forEach(n => n.remove());
  c.querySelectorAll('br').forEach(b => b.replaceWith('\n'));
  c.querySelectorAll('p,div,li,blockquote').forEach(b => b.append('\n'));
  return (c.textContent || '')
    .replace(/[ \t\f\v\u00a0]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
};
const kind = u =>
  /\.(mp4|webm|m3u8|mov)(\?|$)|v\.redd\.it|video\./i.test(u) ? 'video'
  : /\.(mp3|m4a|ogg|wav)(\?|$)/i.test(u) ? 'audio'
  : /\.(jpe?g|png|gif|webp|avif)(\?|$)|i\.redd\.it|preview\.redd\.it|pbs\.twimg\.com/i.test(u) ? 'image'
  : 'link';
const htmlText = s => (s && /[<&]/.test(s)
  ? ownText(new DOMParser().parseFromString(s, 'text/html').body, null) : s);
// Author from an author element: microdata name first (avoids reputation
// badges and "- " prefixes in the surrounding text), then the first link.
const authorOf = el => {
  if (!el) return null;
  const n = el.querySelector('[itemprop="name"]');
  const a = el.tagName === 'A' ? el : el.querySelector('a');
  const name = n ? (n.content || txt(n)) : (a ? txt(a) : txt(el));
  return person(name, null, abs(a ? a.href : ''));
};
const dateOf = scope => {
  const t = scope.querySelector('time[datetime]');
  if (t) return t.getAttribute('datetime');
  const m = scope.querySelector('[itemprop="datePublished"], [itemprop="dateCreated"]');
  if (m) return m.getAttribute('content') || m.getAttribute('datetime') || txt(m);
  return attr(scope.querySelector('.relativetime, .relativetime-clean, .comment-date [title]'), 'title');
};
const person = (name, handle, url) => (name || handle || url ? {name: name || null, handle: handle || null, url: url || null} : null);
"""


def _script(body: str) -> str:
    """Wrap an extractor body (which ``return``s an object or null) into an
    IIFE that hands the result back as a JSON string, so deeply nested
    comment trees survive CDP serialization intact."""
    return (
        "(() => { "
        f"{_PRELUDE} "
        f"const r = (() => {{ {body} }})(); "
        "return JSON.stringify(r); })()"
    )


_GENERIC_JS = _script(r"""
const out = {title: null, author: null, published: null, content: null,
             score: null, comment_count: null, media: [], comments: []};
const meta = n => {
  const e = document.querySelector(`meta[property="${n}"], meta[name="${n}"]`);
  return e && e.content ? e.content : null;
};
const COMMENT_SEL = '[itemprop="comment"], [itemtype*="schema.org/Comment"], li.comment, ' +
  'div.comment, article.comment, [data-comment-id], [id^="comment-"], [id^="comment_"]';

// 1. JSON-LD: the most reliable source when a site provides it.
const nodes = [];
const walk = n => {
  if (!n || typeof n !== 'object') return;
  if (Array.isArray(n)) return n.forEach(walk);
  nodes.push(n);
  walk(n['@graph']);
  walk(n.mainEntity);
};
document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
  try { walk(JSON.parse(s.textContent)); } catch (e) {}
});
const kinds = ['DiscussionForumPosting', 'SocialMediaPosting', 'BlogPosting',
               'NewsArticle', 'Article', 'Question'];
let ld = null;
for (const k of kinds) {
  ld = nodes.find(n => [].concat(n['@type'] || []).includes(k));
  if (ld) break;
}
const ldPerson = a => {
  if (Array.isArray(a)) a = a[0];
  if (!a) return null;
  if (typeof a === 'string') return person(a, null, null);
  return person(a.name, a.alternateName, a.url || a['@id']);
};
const ldMedia = (v, type) => [].concat(v || []).map(m =>
  typeof m === 'string'
    ? {type, url: m}
    : {type, url: m.contentUrl || m.embedUrl || m.url, alt: m.caption || m.name || null});
const ldStat = k => {
  const s = [].concat(ld.interactionStatistic || []).find(x =>
    JSON.stringify(x.interactionType || '').includes(k));
  return s && s.userInteractionCount != null ? s.userInteractionCount : null;
};
const ldComments = (list, depth) => [].concat(list || []).forEach(c => {
  if (!c || typeof c !== 'object') return;
  out.comments.push({
    depth,
    author: ldPerson(c.author),
    published: c.dateCreated || c.datePublished || null,
    content: htmlText(c.text || c.description) || null,
    score: c.upvoteCount != null ? c.upvoteCount : null,
    url: c.url || c['@id'] || null,
  });
  ldComments(c.comment, depth + 1);
});
if (ld) {
  out.title = ld.headline || ld.name || null;
  out.author = ldPerson(ld.author);
  out.published = ld.datePublished || ld.dateCreated || null;
  out.content = htmlText(ld.articleBody || ld.text || ld.description) || null;
  out.score = ldStat('Like');
  out.comment_count = ld.commentCount != null ? ld.commentCount : ldStat('Comment');
  out.media.push(...ldMedia(ld.image, 'image'), ...ldMedia(ld.video, 'video'));
  ldComments(ld.comment, 0);
  ldComments([].concat(ld.acceptedAnswer || [], ld.suggestedAnswer || [], ld.answer || []), 0);
}

// 2. OpenGraph / Twitter card / plain meta tags.
out.title = out.title || meta('og:title') || meta('twitter:title') || document.title || null;
if (!out.author) {
  const name = meta('author') || meta('article:author');
  const handle = meta('twitter:creator');
  out.author = person(name, handle, null);
}
out.published = out.published || meta('article:published_time') ||
  meta('og:article:published_time') || meta('datePublished') ||
  attr(document.querySelector('meta[itemprop="datePublished"]'), 'content');

// 3. DOM heuristics for whatever is still missing.
const root = document.querySelector('article, [role="article"], main');
const scope = root || document;
if (!out.published) out.published = dateOf(scope);
if (!out.author) out.author = authorOf(scope.querySelector('[itemprop="author"], [rel="author"], .author, .byline'));
if (!out.content) {
  // Microdata body (outside any comment) is more precise than a whole
  // <article>/<main>, which may also wrap the comments and page chrome.
  const body = Array.from(document.querySelectorAll('[itemprop="articleBody"], [itemprop="text"]'))
    .find(e => !e.closest(COMMENT_SEL));
  out.content = body ? ownText(body, COMMENT_SEL)
    : root ? ownText(root, COMMENT_SEL)
    : htmlText(meta('og:description') || meta('description'));
}
if (root) {
  root.querySelectorAll('img, video, audio').forEach(m => {
    if (m.closest(COMMENT_SEL)) return;
    const src = m.currentSrc || m.src || '';
    if (m.tagName === 'IMG') {
      if (!src || src.startsWith('data:') || /avatar|profile|emoji|icon|logo|\.svg(\?|$)/i.test(src + ' ' + m.className)) return;
      out.media.push({type: 'image', url: src, alt: m.alt || null});
    } else if (src && !src.startsWith('blob:')) {
      out.media.push({type: m.tagName.toLowerCase(), url: src, alt: null});
    } else if (m.poster) {
      out.media.push({type: 'image', url: m.poster, alt: null});
    }
  });
}
for (const [prop, type] of [['og:image', 'image'], ['og:video', 'video'],
                            ['og:video:url', 'video'], ['og:audio', 'audio']]) {
  const u = meta(prop);
  if (u) out.media.push({type, url: u, alt: null});
}
if (!out.comments.length) {
  document.querySelectorAll(COMMENT_SEL).forEach(el => {
    let depth = 0;
    for (let p = el.parentElement; p; p = p.parentElement) if (p.matches(COMMENT_SEL)) depth++;
    const body = el.querySelector('[itemprop="text"]') ||
      el.querySelector('.comment-body, .comment-content, .comment_text');
    const author = authorOf(el.querySelector(
      '[itemprop="author"], .comment-author, .comment-user, .author, .fn, [rel="author"]'));
    const published = dateOf(el);
    if (!author && !published) return;
    out.comments.push({
      depth, author, published,
      content: ownText(body || el, COMMENT_SEL),
      score: null,
      url: el.id ? location.href.split('#')[0] + '#' + el.id : null,
    });
  });
}
return out;
""")

_OLD_REDDIT_JS = _script(r"""
const t = document.querySelector('.thing.link');
if (!t) return null;
const media = [];
const target = t.getAttribute('data-url') || '';
if (target && !target.startsWith('/') && !(t.getAttribute('data-domain') || '').startsWith('self.')) {
  media.push({type: kind(target), url: target, alt: null});
}
const comments = Array.from(document.querySelectorAll('.commentarea .thing.comment')).map(c => {
  let depth = 0;
  for (let p = c.parentElement; p; p = p.parentElement) {
    if (p.classList.contains('thing') && p.classList.contains('comment')) depth++;
  }
  const e = c.querySelector(':scope > .entry');
  const a = e && e.querySelector('a.author');
  const s = e && e.querySelector('.tagline .score');
  return {
    depth,
    author: person(c.getAttribute('data-author'), null, a ? a.href : null),
    published: attr(e && e.querySelector('time'), 'datetime'),
    content: txt(e && e.querySelector('.usertext-body')),
    score: s ? (s.getAttribute('title') || s.textContent) : null,
    url: abs(c.getAttribute('data-permalink')),
  };
});
const a = t.querySelector('a.author');
return {
  title: txt(t.querySelector('a.title')),
  author: person(t.getAttribute('data-author'), null, a ? a.href : null),
  published: attr(t.querySelector('time'), 'datetime'),
  content: txt(t.querySelector('.usertext-body')),
  score: t.getAttribute('data-score'),
  comment_count: t.getAttribute('data-comments-count'),
  media,
  comments,
};
""")

_REDDIT_JS = _script(r"""
const p = document.querySelector('shreddit-post');
if (!p) return null;
const media = [];
const href = p.getAttribute('content-href');
if (href && p.getAttribute('post-type') === 'link') media.push({type: 'link', url: href, alt: null});
p.querySelectorAll('[slot="post-media-container"] img, [slot="thumbnail"] img').forEach(i => {
  if (i.src) media.push({type: 'image', url: i.src, alt: i.alt || null});
});
p.querySelectorAll('shreddit-player, shreddit-player-2, video').forEach(v => {
  const u = v.getAttribute('src') || v.getAttribute('preview') || v.currentSrc;
  if (u) media.push({type: 'video', url: u, alt: null});
});
if (href && /\.(jpe?g|png|gif|webp)(\?|$)/i.test(href)) media.push({type: 'image', url: href, alt: null});
const comments = Array.from(document.querySelectorAll('shreddit-comment')).map(c => {
  const author = c.getAttribute('author');
  return {
    depth: parseInt(c.getAttribute('depth') || '0', 10) || 0,
    author: person(author, null, author ? abs('/user/' + author) : null),
    published: attr(c.querySelector('time'), 'datetime') || c.getAttribute('created-timestamp'),
    content: txt(c.querySelector('[slot="comment"]')),
    score: c.getAttribute('score'),
    url: abs(c.getAttribute('permalink')),
  };
});
const author = p.getAttribute('author');
return {
  title: p.getAttribute('post-title'),
  author: person(author, null, author ? abs('/user/' + author) : null),
  published: p.getAttribute('created-timestamp'),
  content: txt(p.querySelector('[slot="text-body"]')),
  score: p.getAttribute('score'),
  comment_count: p.getAttribute('comment-count'),
  media,
  comments,
};
""")

# Replies on X are later <article>s in the conversation, not nested DOM, so
# they come back flat (depth 0). The main tweet is the article whose
# timestamp link points at the page's own /status/ URL.
_X_JS = _script(r"""
const arts = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
if (!arts.length) return null;
const parse = a => {
  const names = a.querySelector('[data-testid="User-Name"]');
  const links = names ? Array.from(names.querySelectorAll('a[href^="/"]')) : [];
  const handleLink = links.find(l => txt(l).startsWith('@'));
  const time = a.querySelector('time');
  const timeLink = time ? time.closest('a') : null;
  const media = [];
  a.querySelectorAll('[data-testid="tweetPhoto"] img').forEach(i => {
    if (i.src) media.push({type: 'image', url: i.src, alt: i.alt || null});
  });
  a.querySelectorAll('video').forEach(v => {
    const u = v.currentSrc || v.src;
    if (u && !u.startsWith('blob:')) media.push({type: 'video', url: u, alt: null});
    else if (v.poster) media.push({type: 'image', url: v.poster, alt: 'video poster'});
  });
  const like = a.querySelector('[data-testid="like"], [data-testid="unlike"]');
  return {
    author: person(links.length ? txt(links[0]) : null, handleLink ? txt(handleLink) : null,
                   links.length ? links[0].href : null),
    published: attr(time, 'datetime'),
    content: txt(a.querySelector('[data-testid="tweetText"]')),
    score: like ? (like.getAttribute('aria-label') || '').split(' ')[0] : null,
    url: timeLink ? timeLink.href : null,
    media,
  };
};
const parsed = arts.map(parse);
let main = parsed.findIndex(p => p.url && new URL(p.url).pathname === location.pathname);
if (main < 0) main = 0;
const m = parsed[main];
return {
  title: '',
  author: m.author,
  published: m.published,
  content: m.content,
  score: m.score,
  media: m.media,
  comments: parsed.filter((_, i) => i !== main).map(p => ({depth: 0, ...p})),
};
""")

_HN_JS = _script(r"""
const fat = document.querySelector('.fatitem');
if (!fat) return null;
const age = e => (attr(e, 'title') || '').split(' ')[0] || null;
const link = fat.querySelector('.titleline > a');
const media = link && link.href && !link.href.includes('news.ycombinator.com/item')
  ? [{type: 'link', url: link.href, alt: null}] : [];
const author = fat.querySelector('.hnuser');
const anchors = Array.from(fat.querySelectorAll('.subline a'));
const cc = anchors.find(a => /comment|discuss/.test(a.textContent));
const comments = Array.from(document.querySelectorAll('tr.athing.comtr')).map(tr => {
  const a = tr.querySelector('.hnuser');
  const ageLink = tr.querySelector('.age a');
  return {
    depth: parseInt(attr(tr.querySelector('td.ind'), 'indent') || '0', 10) || 0,
    author: person(a ? txt(a) : null, null, a ? a.href : null),
    published: age(tr.querySelector('.age')),
    content: txt(tr.querySelector('.commtext')),
    url: ageLink ? ageLink.href : null,
  };
});
return {
  title: link ? txt(link) : null,
  author: person(author ? txt(author) : null, null, author ? author.href : null),
  published: age(fat.querySelector('.age')),
  content: txt(fat.querySelector('.toptext, .commtext')),
  score: txt(fat.querySelector('.score')),
  comment_count: cc ? txt(cc) : null,
  media,
  comments,
};
""")

# Facebook's class names are obfuscated and most of it is login-walled, so
# this leans on ARIA: comments are nested [role=article] elements labeled
# "Comment by <name> <age>". Best-effort.
_FACEBOOK_JS = _script(r"""
const SEL = '[role="article"]';
const arts = Array.from(document.querySelectorAll(SEL));
if (!arts.length) return null;
const main = arts.find(a => !a.parentElement.closest(SEL) && !/^Comment/.test(attr(a, 'aria-label') || ''));
const media = [];
if (main) {
  main.querySelectorAll('img[src*="scontent"], img[src*="fbcdn"]').forEach(i => {
    if (i.width >= 100 || i.naturalWidth >= 100) media.push({type: 'image', url: i.src, alt: i.alt || null});
  });
  main.querySelectorAll('video').forEach(v => {
    const u = v.currentSrc || v.src;
    if (u && !u.startsWith('blob:')) media.push({type: 'video', url: u, alt: null});
  });
}
const comments = arts.filter(a => /^Comment/.test(attr(a, 'aria-label') || '')).map(a => {
  let depth = 0;
  for (let p = a.parentElement.closest(SEL); p; p = p.parentElement && p.parentElement.closest(SEL)) {
    if (/^Comment/.test(attr(p, 'aria-label') || '')) depth++;
  }
  const label = attr(a, 'aria-label') || '';
  const m = label.match(/^Comment by (.+?)(?: \d+ \w+ ago| a \w+ ago)?$/);
  const nameLink = a.querySelector('a[role="link"][href*="facebook.com/"], a[href^="/"]');
  return {
    depth,
    author: person(m ? m[1] : (nameLink ? txt(nameLink) : null), null, nameLink ? nameLink.href : null),
    content: txt(a.querySelector('div[dir="auto"][style], div[dir="auto"]')),
  };
});
const msg = main && main.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
const hdr = main && main.querySelector('h2 a, h3 a, h4 a, strong a');
return {
  author: hdr ? person(txt(hdr), null, hdr.href) : null,
  content: msg ? txt(msg) : null,
  media: main ? media : null,
  comments,
};
""")

# Instagram is login-walled and its markup is obfuscated. The og:description
# is the most stable thing: `123 likes, 4 comments - user on March 1, 2024:
# "caption"`.
_INSTAGRAM_JS = _script(r"""
const desc = (document.querySelector('meta[property="og:description"]') || {}).content || '';
const m = desc.match(/^([\d.,KMkm]+) likes?, ([\d.,KMkm]+) comments? - (.+?) on (.+?): [“"]([\s\S]*?)[”"]\.?$/);
const art = document.querySelector('article');
if (!m && !art) return null;
const media = [];
if (art) {
  art.querySelectorAll('img[src], video').forEach(el => {
    if (el.tagName === 'VIDEO') {
      const u = el.currentSrc || el.src;
      if (u && !u.startsWith('blob:')) media.push({type: 'video', url: u, alt: null});
      else if (el.poster) media.push({type: 'image', url: el.poster, alt: 'video poster'});
    } else if ((el.width >= 200 || el.naturalWidth >= 200) && !/profile|avatar/i.test(el.alt || '')) {
      media.push({type: 'image', url: el.src, alt: el.alt || null});
    }
  });
}
const comments = [];
if (art) {
  art.querySelectorAll('ul ul li, ul li').forEach(li => {
    const a = li.querySelector('h2 a, h3 a, a[role="link"]');
    const body = li.querySelector('span[dir="auto"]');
    if (!a || !body || !li.querySelector('time')) return;
    comments.push({
      depth: li.parentElement.closest('li') ? 1 : 0,
      author: person(txt(a), null, a.href),
      published: attr(li.querySelector('time'), 'datetime'),
      content: txt(body),
    });
  });
}
const handle = m ? m[3] : null;
const time = art && art.querySelector('time');
return {
  title: '',
  author: handle ? person(handle, '@' + handle, abs('/' + handle + '/')) : null,
  published: attr(time, 'datetime') || (m ? m[4] : null),
  content: m ? m[5] : null,
  score: m ? m[1] : null,
  comment_count: m ? m[2] : null,
  media: art ? media : null,
  comments,
};
""")

# LinkedIn's class names (BEM-style `update-components-*` / `comments-*`) are
# stable, but it exposes no absolute dates in the DOM - only "1yr". Post and
# comment ids are Snowflake-style, so the timestamp is recovered from the id
# (ms since epoch = id >> 22). A repost's original is nested inside
# `.feed-shared-update-v2__update-content-wrapper`; it is appended to
# `content` under a "Reshared from" line. Replies (LinkedIn allows one level)
# are recognised by their reply-list ancestor / `--reply` class.
_LINKEDIN_JS = _script(r"""
const root = document.querySelector('.feed-shared-update-v2');
if (!root) return null;
const isoFromId = id => {
  try { return new Date(Number(BigInt(id) >> 22n)).toISOString(); } catch (e) { return null; }
};
const clean = t => (t ? t.replace(/hashtag\s*#/g, '#') : t);
const inner = root.querySelector('.feed-shared-update-v2__update-content-wrapper');
const outside = e => !inner || !inner.contains(e);
const actorOf = c => {
  const name = c.querySelector('.update-components-actor__title span[dir="ltr"] span[aria-hidden="true"]') ||
    c.querySelector('.update-components-actor__title');
  const a = c.querySelector('a.update-components-actor__meta-link');
  return person(txt(name), null, a ? a.href.split('?')[0] : null);
};
const actors = Array.from(root.querySelectorAll('.update-components-actor__container'));
const mainActor = actors.find(outside) || actors[0];
const texts = Array.from(root.querySelectorAll('.update-components-text'));
const mainText = texts.find(outside);
const sharedText = inner ? texts.find(t => inner.contains(t)) : null;
const sharedActor = inner ? actors.find(a => inner.contains(a)) : null;
let content = mainText ? clean(txt(mainText)) : '';
if (sharedText) {
  const who = sharedActor ? actorOf(sharedActor).name : null;
  content += (content ? '\n\n' : '') + '— Reshared' + (who ? ' from ' + who : '') + ' —\n' + clean(txt(sharedText));
}
const media = [];
root.querySelectorAll(
  '[class*="update-components-image"] img, [class*="update-components-article"] img, ' +
  '[class*="update-components-document"] img, [class*="update-components-carousel"] img'
).forEach(i => {
  if (/^https?:/.test(i.src)) media.push({type: 'image', url: i.src, alt: /^view image$/i.test(i.alt) ? null : i.alt || null});
});
root.querySelectorAll('video').forEach(v => {
  const u = v.currentSrc || v.src;
  if (u && !u.startsWith('blob:')) media.push({type: 'video', url: u, alt: null});
  else if (v.poster) media.push({type: 'image', url: v.poster, alt: 'video poster'});
});
const art = root.querySelector('[class*="update-components-article"] a[href]');
if (art) media.push({type: 'link', url: art.href, alt: txt(art) || null});

const postId = (location.href + ' ' + (root.getAttribute('data-urn') || '')).match(/(?:activity|ugcPost|share)[-:](\d{15,})/);
const base = location.href.split('?')[0];
const comments = Array.from(root.querySelectorAll('article.comments-comment-entity')).map(c => {
  const reply = c.matches('[class*="--reply"]') || !!c.closest('[class*="comments-replies-list"]');
  const urn = c.getAttribute('data-id') || '';
  const cid = (urn.match(/,(\d{15,})\)/) || [])[1];
  const link = c.querySelector('a.comments-comment-meta__image-link, a.comments-comment-meta__description-container');
  const likes = c.querySelector('[class*="reactions-count"]');
  return {
    depth: reply ? 1 : 0,
    author: person(txt(c.querySelector('.comments-comment-meta__description-title')), null,
                   link ? link.href.split('?')[0] : null),
    published: cid ? isoFromId(cid) : null,
    content: clean(txt(c.querySelector('.comments-comment-item__main-content, .comments-comment-entity__content'))),
    score: likes ? txt(likes) : null,
    url: urn ? base + '?commentUrn=' + encodeURIComponent(urn) : null,
  };
});
return {
  title: '',
  author: mainActor ? actorOf(mainActor) : null,
  published: postId ? isoFromId(postId[1]) : null,
  content,
  score: txt(root.querySelector('.social-details-social-counts__reactions-count')),
  comment_count: txt(root.querySelector('.social-details-social-counts__comments')),
  media: media.length ? media : [],
  comments,
};
""")

# Trustpilot is a Next.js app whose review cards are truncated ("See more") in
# the DOM, but `__NEXT_DATA__` carries every review in full. A business page
# (`/review/<domain>`) has no author or date of its own: it is modelled as a
# "post" about the business whose `comments` are that page's reviews (20 per
# page - use `?page=N` for more), each rendered as `[rating/5] title` + text
# with `score` = helpful votes. A single-review page (`/reviews/<id>`) is a
# post by the reviewer. A company reply becomes a depth-1 comment.
_TRUSTPILOT_JS = _script(r"""
const el = document.getElementById('__NEXT_DATA__');
if (!el) return null;
let pp;
try { pp = JSON.parse(el.textContent).props.pageProps; } catch (e) { return null; }
const bu = pp.businessUnit || pp.business || {};
const buName = bu.displayName || null;
const reviewer = r => {
  const c = r.consumer || {};
  return person(c.displayName, null, c.id ? location.origin + '/users/' + c.id : null);
};
const stars = r => (r.rating ? '[' + r.rating + '/5] ' : '');
const withReply = (r, entry) => {
  const out = [entry];
  const msg = r.reply && (r.reply.message || r.reply.text);
  if (msg) {
    out.push({depth: 1, author: person(buName, null, null), published: r.reply.publishedDate || null,
              content: msg});
  }
  return out;
};
if (pp.review && !pp.reviews) {
  const r = pp.review;
  const comments = withReply(r, null).slice(1);
  return {
    title: r.title || '',
    author: reviewer(r),
    published: (r.dates && r.dates.publishedDate) || '',
    content: (r.rating ? 'Rated ' + r.rating + '/5' + (buName ? ' - ' + buName : '') + '\n\n' : '') + (r.text || ''),
    score: r.likes != null ? r.likes : '',
    comment_count: comments.length,
    media: [],
    comments: comments.map(c => ({...c, depth: 0})),
  };
}
if (!pp.reviews) return null;
const pg = (pp.filters && pp.filters.pagination) || {};
const comments = pp.reviews.flatMap(r => withReply(r, {
  depth: 0,
  author: reviewer(r),
  published: (r.dates && r.dates.publishedDate) || null,
  content: stars(r) + (r.title || '') + '\n\n' + (r.text || ''),
  score: r.likes != null ? r.likes : null,
  url: r.id ? location.origin + '/reviews/' + r.id : null,
}));
const media = [];
if (bu.profileImageUrl) media.push({type: 'image', url: bu.profileImageUrl, alt: buName});
if (bu.websiteUrl) media.push({type: 'link', url: bu.websiteUrl, alt: bu.websiteTitle || null});
return {
  title: (buName || '') + (bu.identifyingName ? ' (' + bu.identifyingName + ')' : '') + ' reviews',
  author: '',
  published: '',
  content: 'TrustScore ' + bu.trustScore + '/5 - ' + bu.numberOfReviews + ' reviews' +
    (pg.currentPage ? '\nShowing page ' + pg.currentPage + ' of ' + pg.totalPages : ''),
  score: '',
  comment_count: bu.numberOfReviews != null ? bu.numberOfReviews : null,
  media,
  comments,
};
""")

# G2: a product page (`/products/<slug>/reviews`) is modelled like Trustpilot's
# business page - a "post" about the product (no author/date; `content` = the
# rating summary and page number) whose `comments` are that page's 10 reviews
# (`?page=N` for more). Author, date, title and rating come from the page's
# JSON-LD `SoftwareApplication.review` list (the first SoftwareApplication has
# only G2's own summary "review" with no body, so the one whose reviews carry
# a `reviewBody` is used). The JSON-LD body is the like/dislike/problems
# answers run together with no labels, so the text is rebuilt from the review
# card (`article#<slug>-review-<id>`, same order): everything after the
# "N/5" line, split at each "Review collected by and hosted on G2.com." so
# every answer keeps its question as a heading. Falls back to the JSON-LD body
# if the cards don't line up. Each review is `[rating/5] title`.
_G2_JS = _script(r"""
const apps = [];
const walk = n => {
  if (!n || typeof n !== 'object') return;
  if (Array.isArray(n)) return n.forEach(walk);
  if ([].concat(n['@type'] || []).includes('SoftwareApplication')) apps.push(n);
  walk(n['@graph']);
  walk(n.mainEntity);
};
document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
  try { walk(JSON.parse(s.textContent)); } catch (e) {}
});
const app = apps.find(a => [].concat(a.review || []).some(r => r.reviewBody));
if (!app) return null;
const reviews = [].concat(app.review).filter(r => r.reviewBody);
const arts = Array.from(document.querySelectorAll('article[id*="-review-"]'));
const aligned = arts.length === reviews.length;
const MARK = 'Review collected by and hosted on G2.com.';
const cardBody = art => {
  const t = txt(art);
  const m = t.match(/^\d(?:\.\d)?\/5$/m);
  if (!m) return null;
  const chunks = t.slice(m.index + m[0].length).split(MARK);
  chunks.pop();  // trailing badges ("Show More", "Validated Reviewer", ...)
  const out = chunks.map(c => c.trim()).filter(Boolean).join('\n\n');
  return out || null;
};
const comments = reviews.map((r, i) => {
  const art = aligned ? arts[i] : null;
  const a = art && art.querySelector('a[href*="/users/"]');
  const rating = r.reviewRating && r.reviewRating.ratingValue;
  return {
    depth: 0,
    author: person(r.author && r.author.name, null, a ? a.href : null),
    published: r.datePublished || null,
    content: (rating ? '[' + rating + '/5] ' : '') + (r.name || '') + '\n\n' +
      ((art && cardBody(art)) || r.reviewBody),
    url: art ? location.origin + '/survey_responses/' + art.id : null,
  };
});
const agg = apps.map(a => a.aggregateRating).find(g => g && Number(g.bestRating) === 5) || app.aggregateRating || {};
const total = Number(agg.reviewCount) || null;
const page = Number(new URLSearchParams(location.search).get('page')) || 1;
const pages = total && reviews.length ? Math.ceil(total / reviews.length) : null;
const media = [];
const logo = app.image || app.logo;
if (typeof logo === 'string') media.push({type: 'image', url: logo, alt: app.name || null});
return {
  title: (app.name || '') + ' reviews',
  author: '',
  published: '',
  content: (agg.ratingValue ? 'G2 rating ' + agg.ratingValue + '/5' + (total ? ' - ' + total + ' reviews' : '') : '') +
    (pages ? '\nShowing page ' + page + ' of ' + pages : ''),
  score: '',
  comment_count: total,
  media,
  comments,
};
""")

# Threads: class names are hashed, but every post is a
# `[data-pressable-container]` card with a `time[datetime]` wrapped in its
# `/@user/post/<code>` permalink. A thread page is the main post (the card
# whose permalink is the page's own path) followed by its replies as later
# cards; parents of a reply URL come before it and are skipped. Replies are
# flat (depth 0) - nested ones sit behind "Show replies" - and counts are the
# abbreviated ones Threads shows ("1K"). The app is a SPA that keeps the home
# feed mounted (hidden) under the thread page, so only visible cards count. A
# cold load of a post URL is bounced to the home feed as
# `/?injected_media_ids=[id]`: the post is the feed's first card, with no
# replies, and the feed's column-title link keeps that param after the app
# strips it from `location`. There the adapter clicks the post's permalink (an
# in-app navigation) and returns `pending: true` until the thread renders.
# The post's shortcode is the media id in base 64.
_THREADS_JS = _script(r"""
const shown = e => e.getClientRects().length > 0;
const cards = Array.from(document.querySelectorAll('[data-pressable-container="true"]')).filter(shown);
const linkOf = c => Array.from(c.querySelectorAll('a[href*="/post/"]')).find(a => a.querySelector('time'));
const injLink = document.querySelector('a[href*="injected_media_ids"]');
if (injLink && shown(injLink)) {
  // Still the feed (the URL flips to the post path before the DOM does).
  const injected = decodeURIComponent(injLink.getAttribute('href')).match(/\d{10,}/);
  if (location.pathname === '/' && injected) {
    const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    const idOf = code => Array.from(code).reduce((n, ch) => n * 64n + BigInt(ALPHA.indexOf(ch)), 0n).toString();
    const links = cards.map(linkOf).filter(Boolean);
    const target = links.find(a => { try { return idOf(a.pathname.split('/post/')[1].split('/')[0]) === injected[0]; } catch (e) { return false; } });
    if (!target) return null;
    target.click();
  }
  return {pending: true};
}
if (!/\/post\//.test(location.pathname)) return null;
let main = cards.findIndex(c => { const a = linkOf(c); return a && a.pathname.replace(/\/$/, '') === location.pathname.replace(/\/$/, ''); });
if (main < 0) return null;
// The action icons are bare SVGs titled "Like"/"Reply"/...; the count is the
// rest of their button's text ("Like1K" -> "1K", "Reply" alone -> none).
const count = (c, ...labels) => {
  for (const t of c.querySelectorAll('svg > title')) {
    if (!labels.includes(t.textContent)) continue;
    const b = t.closest('[role="button"]');
    if (b) return txt(b).replace(t.textContent, '').trim() || null;
  }
  return null;
};
const parse = c => {
  const link = linkOf(c);
  const name = ((Array.from(c.querySelectorAll('a[href^="/@"]')).find(a => !a.href.includes('/post/')) || {}).textContent || '').trim();
  // Post text ends where the action row starts (the reply composer's
  // placeholder in the main card comes after it).
  const bar = Array.from(c.querySelectorAll('svg > title')).find(t => /^(Like|Unlike)$/.test(t.textContent));
  const body = Array.from(c.querySelectorAll('span[dir="auto"]')).filter(s =>
    !s.closest('a, [role="button"]') && !s.parentElement.closest('span[dir="auto"]') && !s.querySelector('time') &&
    !(bar && bar.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING));
  const media = [];
  c.querySelectorAll('img').forEach(i => {
    const src = i.currentSrc || i.src;
    if (!src || /profile picture/i.test(i.alt) || (i.naturalWidth || i.width) < 150) return;
    media.push({type: 'image', url: src, alt: i.alt || null});
  });
  c.querySelectorAll('video').forEach(v => {
    const u = v.currentSrc || v.src;
    if (u && !u.startsWith('blob:')) media.push({type: 'video', url: u, alt: null});
    else if (v.poster) media.push({type: 'image', url: v.poster, alt: 'video poster'});
  });
  return {
    author: name ? person(name, '@' + name, abs('/@' + name)) : null,
    published: attr(c.querySelector('time'), 'datetime'),
    content: body.map(txt).filter(Boolean).join('\n'),
    score: count(c, 'Like', 'Unlike'),
    replies: count(c, 'Reply'),
    url: link ? link.href : null,
    media,
  };
};
const m = parse(cards[main]);
return {
  title: '',
  author: m.author,
  published: m.published,
  content: m.content,
  score: m.score,
  comment_count: m.replies,
  media: m.media,
  comments: cards.slice(main + 1).map(parse).map(p => ({depth: 0, ...p})),
};
""")

# Quora: a question page is a post (the question, no author/date) whose
# `comments` are its answers. Class names are hashed, but Quora's own
# `dom_annotate_*` / `puppeteer_test_*` hooks are stable. The page also lists
# answers to *related* questions, so items are filtered to this question's
# path. Long answers are truncated behind "(more)": the adapter clicks those
# (expanding in place, no navigation) and returns `pending: true` so the
# caller re-reads until none are left. Answers only carry relative ages
# ("6y"), kept as-is. Quora+ paywalled answers end at an "Access this answer"
# block, which is cut off. Only the answers Quora has rendered are seen.
_QUORA_JS = _script(r"""
const title = document.querySelector('.puppeteer_test_question_main .puppeteer_test_question_title') ||
  document.querySelector('.puppeteer_test_question_title');
if (!title) return null;
const ITEM = '[class*="dom_annotate_question_answer_item_"]';
const path = location.pathname.replace(/\/$/, '');
const items = Array.from(document.querySelectorAll(ITEM)).filter(i => {
  const t = i.querySelector('a.answer_timestamp');
  return t && new URL(t.href).pathname.startsWith(path + '/answer/');
});
const more = items.flatMap(i => Array.from(i.querySelectorAll('.qt_read_more')));
more.forEach(m => m.click());
const tidy = t => t
  .split(/\nAccess this answer and support the author/)[0]
  .replace(/\s*(…|\.\.\.)?\s*\(more\)\s*$/, '…')
  .trim();
const media = [];
const comments = items.map(i => {
  const content = i.querySelector('.puppeteer_test_answer_content');
  const profile = Array.from(i.querySelectorAll('a[href*="/profile/"]')).find(a => txt(a));
  const ts = i.querySelector('a.answer_timestamp');
  const up = i.querySelector('.dom_annotate_answer_action_bar_upvote');
  if (content) content.querySelectorAll('img').forEach(m => {
    if (/^https?:/.test(m.src)) media.push({type: 'image', url: m.src, alt: m.alt || null});
  });
  return {
    depth: 0,
    author: person(profile ? txt(profile) : null, null, profile ? profile.href.split('?')[0] : null),
    published: txt(ts),
    content: content ? tidy(txt(content)) : null,
    score: up ? txt(up) : null,
    url: ts ? ts.href : null,
  };
});
const desc = (document.querySelector('meta[property="og:description"]') || {}).content || '';
const total = desc.match(/\(\d+ of (\d+)\)/);
return {
  title: txt(title),
  author: '',
  published: '',
  content: '',
  score: '',
  comment_count: total ? Number(total[1]) : null,
  media,
  comments,
  pending: more.length > 0,
};
""")

# Discourse forums live on arbitrary hostnames, so unlike the adapters above
# this one is detected from <meta name="generator"> (returns null elsewhere)
# and tried on every otherwise-generic page. Posts are a flat chronological
# list: the first is the topic itself, the rest are its replies. Discourse
# only renders the posts near the viewport, so long topics need scrolling.
_DISCOURSE_JS = _script(r"""
const gen = document.querySelector('meta[name="generator"]');
if (!gen || !/^Discourse/i.test(gen.content)) return null;
const posts = Array.from(document.querySelectorAll('article[data-post-id]')).map(a => {
  const user = a.querySelector('.names a[data-user-card], .names .username a, .username a');
  const date = a.querySelector('.post-info .relative-date, .post-date .relative-date');
  const ms = date && date.getAttribute('data-time');
  const media = [];
  a.querySelectorAll('.cooked img:not(.emoji):not(.avatar)').forEach(i => {
    const link = i.closest('a.lightbox');
    media.push({type: 'image', url: link ? link.href : i.src, alt: i.alt || null});
  });
  return {
    depth: 0,
    author: person(user ? txt(user) : null, null, user ? user.href : null),
    published: ms ? new Date(Number(ms)).toISOString() : null,
    content: ownText(a.querySelector('.cooked') || a, null),
    score: txt(a.querySelector('.like-count, .discourse-reactions-counter .reactions-counter')),
    url: abs(attr(a.querySelector('a.post-date'), 'href')),
    media,
  };
});
if (!posts.length) return null;
const t = document.querySelector('#topic-title .fancy-title, h1[data-topic-id] .fancy-title, h1');
const first = posts[0];
return {
  title: t ? txt(t) : null,
  author: first.author,
  published: first.published,
  content: first.content,
  score: first.score,
  media: first.media,
  comments: posts.slice(1),
};
""")

# adapter key -> (platform, extractor)
_ADAPTERS: dict[str, tuple[str, str]] = {
    "old_reddit": ("reddit", _OLD_REDDIT_JS),
    "reddit": ("reddit", _REDDIT_JS),
    "x": ("x", _X_JS),
    "hackernews": ("hackernews", _HN_JS),
    "facebook": ("facebook", _FACEBOOK_JS),
    "instagram": ("instagram", _INSTAGRAM_JS),
    "linkedin": ("linkedin", _LINKEDIN_JS),
    "trustpilot": ("trustpilot", _TRUSTPILOT_JS),
    "g2": ("g2", _G2_JS),
    "threads": ("threads", _THREADS_JS),
    "quora": ("quora", _QUORA_JS),
}

# Hostname (after stripping www./m./mobile./web.) -> adapter key.
_HOSTS: dict[str, str] = {
    "old.reddit.com": "old_reddit",
    "reddit.com": "reddit",
    "new.reddit.com": "reddit",
    "sh.reddit.com": "reddit",
    "x.com": "x",
    "twitter.com": "x",
    "news.ycombinator.com": "hackernews",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "trustpilot.com": "trustpilot",
    "g2.com": "g2",
    "threads.com": "threads",
    "threads.net": "threads",
    "quora.com": "quora",
}

# Sites served from per-country subdomains (nz.trustpilot.com, ...).
_HOST_SUFFIXES: dict[str, str] = {
    "trustpilot.com": "trustpilot",
    "quora.com": "quora",
}

_HOST_PREFIXES = ("www.", "m.", "mobile.", "web.")

_WAIT_SECONDS = 10.0
_POLL_INTERVAL = 0.5


def _adapter_for(url: str) -> tuple[str, str | None]:
    """(platform, extractor JS) for ``url``; ("generic", None) if unknown."""
    host = (urlparse(url).hostname or "").lower()
    for prefix in _HOST_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    key = _HOSTS.get(host)
    if key is None:
        key = next(
            (k for suffix, k in _HOST_SUFFIXES.items() if host.endswith("." + suffix)),
            None,
        )
    if key is None:
        return "generic", None
    return _ADAPTERS[key]


def _as_obj(raw: Any) -> dict[str, Any] | None:
    """Parse an extractor result (a JSON string, or already a dict)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if isinstance(raw, dict) else None


def _line(value: Any) -> str | None:
    """Single-line string: whitespace collapsed, empty -> None."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _text(value: Any) -> str | None:
    """Multi-line string: per-line whitespace collapsed, blank-line runs
    reduced to one, empty -> None."""
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in str(value).splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None


_COUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?")


def _count(value: Any) -> int | None:
    """Parse "1,234", "12 points", "1.2k", 5 -> int. None if no number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _COUNT_RE.search(str(value))
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    number *= {"k": 1_000, "m": 1_000_000}.get((match.group(2) or "").lower(), 1)
    return int(number)


def _person(value: Any, base: str) -> dict[str, str | None] | None:
    if isinstance(value, str):
        value = {"name": value}
    if not isinstance(value, dict):
        return None
    url = _line(value.get("url"))
    person = {
        "name": _line(value.get("name")),
        "handle": _line(value.get("handle")),
        "url": urljoin(base, url) if url else None,
    }
    return person if any(person.values()) else None


def _media(items: Any, base: str) -> list[dict[str, str | None]]:
    """Absolutize, keep http(s) only, dedupe by URL (first wins)."""
    seen: set[str] = set()
    result: list[dict[str, str | None]] = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        url = urljoin(base, str(item["url"]))
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        result.append(
            {
                "type": _line(item.get("type")) or "image",
                "url": url,
                "alt": _line(item.get("alt")),
            }
        )
    return result


def _merge(generic: dict[str, Any], adapter: dict[str, Any] | None) -> dict[str, Any]:
    """Adapter values win over generic ones. A missing/None adapter value
    falls through to generic; an empty string is a deliberate override (X
    and Instagram have no title, and generic would otherwise fill in the
    "X user on X: ..." og:title). An adapter's lists are authoritative even
    when empty - the generic DOM heuristics would otherwise pull in site
    chrome and other posts' media - so an adapter that can't locate the post
    reports ``media``/``comments`` as None to fall back to generic."""
    merged = dict(generic)
    for key, value in (adapter or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def _comment(raw: dict[str, Any], base: str) -> dict[str, Any]:
    url = _line(raw.get("url"))
    return {
        "author": _person(raw.get("author"), base),
        "published": _line(raw.get("published")),
        "content": _text(raw.get("content")),
        "score": _count(raw.get("score")),
        "url": urljoin(base, url) if url else None,
        "replies": [],
    }


def _nest_comments(flat: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    """Turn a document-order list of comments carrying ``depth`` into a
    tree of ``replies``. Comments with neither author nor content are
    dropped (placeholder rows, e.g. "load more")."""
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    for raw in flat:
        node = _comment(raw, base)
        if not node["author"] and not node["content"]:
            continue
        try:
            depth = max(0, int(raw.get("depth") or 0))
        except (TypeError, ValueError):
            depth = 0
        while stack and stack[-1][0] >= depth:
            stack.pop()
        (stack[-1][1]["replies"] if stack else roots).append(node)
        stack.append((depth, node))
    return roots


def _build_post(
    url: str,
    platform: str,
    merged: dict[str, Any],
    max_comments: int,
    include_comments: bool,
) -> dict[str, Any]:
    flat = [c for c in merged.get("comments") or [] if isinstance(c, dict)]
    comment_count = _count(merged.get("comment_count"))
    if comment_count is None and flat:
        comment_count = len(flat)
    # A prefix of the document-order list is still a well-formed tree, so
    # truncating before nesting never orphans a reply.
    comments = _nest_comments(flat[:max_comments], url) if include_comments else []
    return {
        "url": url,
        "platform": platform,
        "title": _line(merged.get("title")),
        "author": _person(merged.get("author"), url),
        "published": _line(merged.get("published")),
        "content": _text(merged.get("content")),
        "score": _count(merged.get("score")),
        "comment_count": comment_count,
        "media": _media(merged.get("media"), url),
        "comments": comments,
    }


def _read_page(d: CDPMethods) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    url = d.get_current_url()
    platform, adapter_js = _adapter_for(url)
    generic = _as_obj(d.evaluate(_GENERIC_JS)) or {}
    if adapter_js is None:
        # Unknown host: it may still be a Discourse forum.
        adapter = _as_obj(d.evaluate(_DISCOURSE_JS))
        if adapter is not None:
            platform = "discourse"
    else:
        adapter = _as_obj(d.evaluate(adapter_js))
    return url, platform, generic, adapter


def extract_post(max_comments: int = 200, include_comments: bool = True) -> str:
    """Structured JSON for the post on the currently open page."""
    deadline = time.monotonic() + _WAIT_SECONDS
    while True:
        url, platform, generic, adapter = with_driver(_read_page)
        merged = _merge(generic, adapter)
        # Known sites render client-side, so wait for the adapter to match;
        # on generic pages the baseline metadata is available immediately.
        ready = adapter if platform != "generic" else generic
        found = bool(ready and (ready.get("title") or ready.get("content")))
        # An adapter may set `pending` after triggering more content to load
        # (e.g. expanding truncated answers): re-read until it clears.
        pending = bool(adapter and adapter.get("pending"))
        if found and not pending:
            break
        if time.monotonic() >= deadline:
            if not found:
                print(
                    "No post found (possible login wall, or not a post page); "
                    "run `snapshot` to see what is on the page.",
                    file=sys.stderr,
                )
            break
        time.sleep(_POLL_INTERVAL)
    post = _build_post(url, platform, merged, max_comments, include_comments)
    return json.dumps(post, ensure_ascii=False)
