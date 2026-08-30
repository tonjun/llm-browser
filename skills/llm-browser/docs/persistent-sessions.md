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

| Path | Purpose |
|---|---|
| `session.json` | `{"pid", "host", "port"}` for the running daemon. Presence + a live pid + a responsive port together mean "there's a session to reuse". |
| `profile/` | The Chrome `user_data_dir` used by the daemon. Passing an explicit profile dir marks it "custom" to SeleniumBase, so it's never auto-deleted on quit/crash — cookies, logins, and local storage persist across daemon restarts. |
| `daemon.log` | Combined stdout/stderr of the daemon process, for debugging startup failures. |
| `session.lock` | Short-lived lock file used only while deciding whether to spawn a new daemon (see below). |

## How `open` decides to spawn vs. reuse

1. Read `session.json`. If it names a pid that's alive **and** a port that
   accepts a TCP connection, reuse it directly — connect and navigate.
2. Otherwise, acquire `session.lock` (atomic `O_CREAT|O_EXCL`) so that two
   `open` calls racing to start the browser at the same time don't both
   spawn a daemon; the loser just waits and connects to the winner's daemon.
3. If a stale `session.json` was left behind (e.g. the daemon was
   `kill -9`'d), the orphaned Chrome process it spawned wouldn't be killed
   by that alone — it's a plain, non-detached child of the daemon, not
   reachable by a "kill this one pid" call. Before spawning a replacement,
   `llm-browser` signals the *whole process group* of the old daemon
   (`os.killpg`), which reaches any orphaned Chrome too — this is what
   makes crash recovery actually work rather than getting stuck on a
   leftover `SingletonLock` in `profile/`.
4. Spawn the daemon, poll `session.json` until it reports an alive session
   (or time out after ~10s and surface an error pointing at `daemon.log`).

## `llm-browser close`

Sends `SIGTERM` to the daemon's pid; its handler calls `driver.quit()`
(cleanly closing Chrome) and removes `session.json`. If the daemon doesn't
shut down within the timeout, `close` falls back to the same process-group
kill described above and clears the state file itself. Running `close`
with no session running is a no-op that reports as much.

## `--headless`

This flag only has an effect the moment the daemon is first spawned — it
configures how that one long-lived Chrome instance is launched. If a
session is already running and you pass `--headless` on a later `open`,
it's ignored (with a printed note) rather than trying to reconfigure a
browser that's already up; run `llm-browser close` first if you need to
switch modes.
