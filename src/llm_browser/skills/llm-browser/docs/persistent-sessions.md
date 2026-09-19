# Persistent browser sessions

`llm-browser open <url>` keeps the browser running across invocations instead
of launching and closing a fresh Chrome instance every time. The first
`open` starts a browser and leaves it running in the background; every
later `open` reuses that same browser, reconnecting over the Chrome
DevTools Protocol (CDP) and navigating the existing session to the new URL.

## Why a background daemon

Each `llm-browser` command is a separate, short-lived process. SeleniumBase's
CDP mode (`sb_cdp.Chrome`) ties a spawned Chrome process's lifetime to the
Python process that launched it — when that process exits normally, an
`atexit` hook in SeleniumBase terminates Chrome. So a single CLI invocation
can't just launch Chrome and exit while expecting it to keep running.

Instead, `llm-browser` spawns a small **daemon process**
(`llm_browser.daemon`) whose only job is to launch Chrome once and then
block, keeping both itself and the browser alive. It's started detached
(`start_new_session=True`), so it isn't tied to the invoking shell's
terminal or process group and survives after the CLI command that spawned
it returns.

Every `open` call after that connects to the daemon's Chrome over CDP using
`host`/`port` (SeleniumBase's "connect to an existing browser" mode). An
attached-only connection like this never gets a real process handle from
SeleniumBase's perspective, so its own `atexit` cleanup can't and doesn't
kill the shared browser when the CLI process exits.

## State layout — `~/.llm-browser/`

Set `LLM_BROWSER_HOME=/some/dir` to relocate the whole directory (state
files *and* the Chrome profile). Since everything below hangs off it,
that gives you fully isolated sessions - e.g. one per agent running on
the same machine, or a throwaway profile - instead of every invocation
sharing one Chrome, one active-tab pointer and one login state.

| Path | Purpose |
|---|---|
| `session.json` | `{"pid", "host", "port"}` for the running daemon. Presence + a live pid + a responsive port together mean "there's a session to reuse". |
| `profile/` | The Chrome `user_data_dir` used by the daemon. Passing an explicit profile dir marks it "custom" to SeleniumBase, so it's never auto-deleted on quit/crash — cookies, logins, and local storage persist across daemon restarts. |
| `daemon.log` | Combined stdout/stderr of the daemon process, for debugging startup failures. |
| `session.lock` | Lock file used only while deciding whether to spawn a new daemon (see below). |
| `command.lock` | `flock` every command takes so concurrent invocations queue rather than race on the shared Chrome. |
| `active_tab`, `labels.json` | Which tab the next command attaches to, and `tab new --label` names - see `commands.md`'s tabs section. |
| `screenshots/`, `pages/` | Default output locations for `screenshot` and `save-markdown` when no path is given. |

## How `open` decides to spawn vs. reuse

1. Read `session.json`. If it names a pid that's alive **and** a port that
   accepts a TCP connection, reuse it directly — connect and navigate.
2. Otherwise, take a non-blocking `flock` on `session.lock` so that two
   `open` calls racing to start the browser at the same time don't both
   spawn a daemon; the loser just waits and connects to the winner's daemon.
   Being an `flock` (not a marker file), the kernel drops it if the holder
   dies mid-spawn, so a killed `open` can't leave a stale lock behind.
3. If a stale `session.json` was left behind (e.g. the daemon was
   `kill -9`'d), the orphaned Chrome process it spawned wouldn't be killed
   by that alone — it's a plain, non-detached child of the daemon, not
   reachable by a "kill this one pid" call. Before spawning a replacement,
   `llm-browser` signals the *whole process group* of the old daemon
   (`os.killpg`), which reaches any orphaned Chrome too — this is what
   makes crash recovery actually work rather than getting stuck on a
   leftover `SingletonLock` in `profile/`.
4. Spawn the daemon, poll `session.json` until it reports an alive session
   (or time out after ~30s and surface an error pointing at `daemon.log`).
5. Navigate through the same attach path every other command uses, so
   `open` acts on the *active* tab (see `tab switch`) and waits for the
   page's `readyState` instead of a fixed sleep.

## `llm-browser close`

Sends `SIGTERM` to the daemon's pid; its handler calls `driver.quit()`
(cleanly closing Chrome) and removes `session.json`. If the daemon doesn't
shut down within the timeout, `close` falls back to the same process-group
kill described above and clears the state file itself. Running `close`
with no session running is a no-op that reports as much - though if a
stale `session.json` is found, the old daemon's process group is killed
first so an orphaned Chrome doesn't keep the profile locked.

The daemon also watches Chrome itself: if the browser goes away on its
own (last window closed by hand, crash), the daemon notices within a few
seconds, cleans up `session.json` and exits, rather than lingering with a
dead debug port until the next `open` reaps it.

## Errors

Any failure is reported as a single `error: <message>` line on stderr
with exit status 1 - no traceback, and nothing an agent has to page
through. Set `LLM_BROWSER_DEBUG=1` to get the full Python traceback when
debugging the CLI itself.

## `--headless` / `--headed`

These flags only have an effect the moment the daemon is first spawned —
they configure how that one long-lived Chrome instance is launched. If a
session is already running and you pass `--headless` or `--headed` on a
later `open`, it's ignored (with a printed note) rather than trying to
reconfigure a browser that's already up; run `llm-browser close` first if
you need to switch modes. `--headless` and `--headed` can't be combined on
the same command — passing both is a validation error.

`--headed` forces a real, visible Chrome window. On Linux, SeleniumBase's
default when neither flag is passed is to run Chrome for real (not
`--headless`) but inside an invisible, auto-started Xvfb virtual display —
which looks headless to you even though it isn't literally headless Chrome.
Pass `--headed` to skip that fallback and get an actual window on screen.
