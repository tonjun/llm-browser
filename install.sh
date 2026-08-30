#!/bin/sh
# Installs llm-browser as a standalone CLI tool.
#
#   curl -fsSL https://raw.githubusercontent.com/tonjun/llm-browser/main/install.sh | sh
#
# No git clone needed. Installs uv (https://astral.sh) if it isn't already
# on PATH, then uses `uv tool install` to put `llm-browser` on PATH.

set -eu

REPO_URL="git+https://github.com/tonjun/llm-browser"

if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required to run this installer." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found, installing it first..."
  curl -fsSL https://astral.sh/uv/install.sh | sh

  # uv's installer puts the binary in one of these, depending on version/platform.
  for uv_bin_dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -x "$uv_bin_dir/uv" ]; then
      PATH="$uv_bin_dir:$PATH"
      export PATH
      break
    fi
  done

  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv was installed but is not on PATH. Open a new shell and re-run this installer." >&2
    exit 1
  fi
fi

echo "Installing llm-browser..."
uv tool install --force "$REPO_URL"

echo
echo "llm-browser installed."
if command -v llm-browser >/dev/null 2>&1; then
  echo "Try it now:"
  echo "  llm-browser open https://example.com"
else
  echo "Open a new shell (or re-source your profile) so the uv tool shim directory is on PATH, then try:"
  echo "  llm-browser open https://example.com"
fi
