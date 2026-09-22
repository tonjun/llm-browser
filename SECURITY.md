# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub Security Advisories](https://github.com/tonjun/llm-browser/security/advisories/new)
rather than a public issue. Include the version (`llm-browser --version`), your OS, and steps to
reproduce. You can expect an initial response within a week.

Only the latest release is supported.

## Things to know when running llm-browser

- The first `open` starts a background Chrome that exposes a Chrome DevTools Protocol (CDP)
  port on the local machine. Any local process that can reach that port can control the browser,
  so don't run llm-browser on a shared machine you don't trust.
- Browser state lives in `~/.llm-browser/` (or `$LLM_BROWSER_HOME`): a persistent Chrome profile
  (cookies, logins, local storage), screenshots and a daemon log. Treat it like a browser profile;
  delete it (after `llm-browser close`) to clear everything.
- `eval` runs arbitrary JavaScript in the page and `cookies`/`storage` read and write session
  data. If an LLM agent drives the CLI, page content is untrusted input, so review what you let
  the agent do on logged-in sessions.
