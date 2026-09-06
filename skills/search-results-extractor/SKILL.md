---
name: search-results-extractor
description: Extract search results from browser automation page snapshots. Use when given a browser accessibility tree, page snapshot, or structured web page representation and asked to identify search results with their title, URL, and snippet.
---

# Search Results Extractor

Extract search results from a browser automation page snapshot and output them as plain text.

## Output Format

For every search result, output exactly:

Title: <title>
URL: <url>
Snippet: <snippet>

Separate each result with one blank line.

Do not output JSON, XML, YAML, Markdown tables, or any other structured data format.

Do not add an introduction, explanation, conclusion, numbering, or commentary.

## Extraction Procedure

### 1. Find the search results

Locate the main section containing the actual search results.

Search results are normally located under a heading such as:

* `Search Results`
* `Web results`
* `Search results`

Focus on result entries inside the main search-results area.

### 2. Identify result entries

A search result is normally represented by a result-level `link` containing:

* an `href` attribute
* a title, usually represented by an associated `heading`
* optional metadata

The descriptive snippet is usually **not** part of this link — see step 5 for where it actually lives and how to tell it apart from metadata. The simplified example below shows a case where a snippet-like `StaticText` happens to sit inside the link; treat this as the exception, not the default:

```text
link "Example Result" [href="https://example.com/article"]
  heading "Example Result"
  StaticText "Example Site"
  StaticText "This is the description of the search result."
```

This represents one search result:

```text
Title: Example Result
URL: https://example.com/article
Snippet: This is the description of the search result.
```

### 3. Extract the title

Use the heading associated with the result link as the title.

If there is no separate heading, use the title text of the result-level link.

Do not invent or infer a title.

### 4. Extract the URL

The URL MUST be taken directly from the `href` attribute of the result-level link.

The `href` is authoritative.

Always output the URL when an explicit `href` is available.

Do not:

* omit the URL
* infer the URL from the title
* construct a URL
* modify a URL
* replace the URL with a domain name
* use a URL from another link associated with the result

If a candidate result has no explicit `href`, do not output it.

### 5. Extract the snippet

The snippet is normally **not** inside the result-level `link` itself.

The result-level `link` typically contains only:

* a `heading` (the title)
* one or more short `StaticText` nodes giving the source/metadata, such as a site name (`"Reddit · r/Philippines"`) or a stats line (`"20+ comments · 2 months ago"`)

**Do not treat this metadata text as the snippet.** It is part of the link's title/name, not a description, even though it appears as `StaticText` right after the `heading`. A reliable signal: if a `StaticText` node's content matches (or is a substring of) the link's own accessible name/title string, it is metadata, not snippet.

The actual snippet is a **separate block that follows the result link** (and typically follows a `button "About this result"` if one is present), as a **sibling** of the link, not a child of it. For example:

```text
link "Example Result Reddit · r/Example 5 comments · 2 years ago" [href="https://example.com/article"]
  heading "Example Result"
  StaticText "Reddit · r/Example"
  StaticText "5 comments · 2 years ago"
button "About this result"
generic
  emphasis
    StaticText "Why isn't there"
  StaticText " a longer description continuing the snippet text ..."
```

Here the snippet to extract is `Why isn't there a longer description continuing the snippet text ...` (concatenating any `emphasis` and `StaticText` nodes in that following block, in order) — **not** `"Reddit · r/Example 5 comments · 2 years ago"`.

Sometimes the snippet block instead (or additionally) contains an inline answer preview, marked with a `StaticText "Top answer:"` followed by the answer text, and/or a `link "N answers"`. In that case:

* Ignore the `link "N answers"` (per the non-result-link rules below).
* Strip the literal `"Top answer:"` label text.
* Use the remaining answer text as the snippet if no other description text is present.

If both a query-matched description (with `emphasis`) and a "Top answer" preview are present, prefer the query-matched description.

Remove UI-only text such as:

* `About this result`
* `Read more`
* `Answers` / `N answers` / `Top answer:` (label only — keep the answer text itself)
* navigation labels
* unrelated controls
* source/metadata text that duplicates the link's own title (site name, comment count, age)

Preserve the substantive content of the snippet.

Do not invent or summarize information unless necessary to remove UI text.

### 6. Ignore non-result links

Do not treat every link in the snapshot as a search result.

Ignore links and controls such as:

* Skip to main content
* Accessibility help
* Search
* Clear
* Search by voice
* Search by image
* Google Home
* AI Mode
* Images
* Videos
* News
* Shopping
* More filters
* Tools
* Account links
* About this result
* Read more
* Answer/comment links
* Page 2, Page 3, etc.
* Next
* Footer links
* Privacy
* Terms
* Help
* Send feedback
* Location controls

Only extract links that represent actual search-result entries.

### 7. Preserve result order

Output results in exactly the order they appear in the snapshot.

### 8. Do not follow links

Extract information from the supplied snapshot only.

Do not assume information that would require opening or visiting the result URL.

### 9. Missing snippets

If a valid search result has a title and URL but no snippet, output:

Snippet:

Do not invent a snippet.

## Example

Given:

```text
heading "Web results"

link "Example Result" [href="https://example.com/article"]
  heading "Example Result"
  StaticText "Example Site"
  StaticText "This is the description of the search result."

link "Another Result" [href="https://example.org/page"]
  heading "Another Result"
  StaticText "Another description."
```

Output:

```text
Title: Example Result
URL: https://example.com/article
Snippet: This is the description of the search result.

Title: Another Result
URL: https://example.org/page
Snippet: Another description.
```

## Example: metadata inside the link vs. snippet outside it

Given:

```text
heading "Web results"

link "Example Result Reddit · r/Example 20+ comments · 2 months ago" [href="https://example.com/r/Example/comments/abc123/example_result/"]
  heading "Example Result"
  StaticText "Reddit · r/Example"
  StaticText "20+ comments · 2 months ago"
button "About this result"
generic
  emphasis
    StaticText "Why isn't there"
  StaticText " a clearer explanation for this in the sub? Some possible reasons include ..."
```

Output:

```text
Title: Example Result
URL: https://example.com/r/Example/comments/abc123/example_result/
Snippet: Why isn't there a clearer explanation for this in the sub? Some possible reasons include ...
```

Note that `"Reddit · r/Example 20+ comments · 2 months ago"` is **not** used as the snippet — it is metadata attached to the title link and must be discarded.

## Critical Rules

1. **Extract actual search results, not arbitrary links.**
2. **The snippet lives outside the result link, as a sibling block — never reuse the link's own title/metadata `StaticText` (site name, comment count, age) as the snippet.**
3. **Always extract the URL from the result link's `href`.**
4. **Never omit an available URL.**
5. **Never invent or modify URLs.**
6. **Preserve the order of results.**
7. **Output plain text only.**
8. **Do not output JSON.**
9. **Do not add commentary outside the extracted results.**