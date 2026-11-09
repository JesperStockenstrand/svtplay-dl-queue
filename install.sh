#!/usr/bin/env bash
# Install the svtplay-dl Queue helper app (native messaging host).
#
# Usage: ./install.sh [--extension-id ID]... [--all-browsers]
#
#   --extension-id ID   Also allow this Chromium extension ID (e.g. a Chrome
#                       Web Store build). The ID of the unpacked extension in
#                       this repo is always allowed.
#   --all-browsers      Register with every supported browser, even ones that
#                       don't seem to be installed.
set -euo pipefail

HOST_NAME="svtplay_dl_queue"
APP="svtplay-dl-queue"
# Fixed by the "key" in extension/manifest.json.
CHROME_IDS=("oonjepebfihcafficfecahlgfafinoee")
FIREFOX_ID="svtplay-dl-queue@svtplay-dl-queue"
ALL_BROWSERS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --extension-id) CHROME_IDS+=("$2"); shift 2 ;;
    --all-browsers) ALL_BROWSERS=1; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
  Darwin)
    DATA="$HOME/Library/Application Support/$APP"
    SUPPORT="$HOME/Library/Application Support"
    CHROMIUM_DIRS=(
      "$SUPPORT/Google/Chrome"
      "$SUPPORT/Google/Chrome Beta"
      "$SUPPORT/Google/Chrome Canary"
      "$SUPPORT/Chromium"
      "$SUPPORT/BraveSoftware/Brave-Browser"
      "$SUPPORT/Microsoft Edge"
      "$SUPPORT/Vivaldi"
      "$SUPPORT/Arc/User Data"
    )
    FIREFOX_DIRS=("$SUPPORT/Mozilla")
    ;;
  Linux)
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP"
    CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
    CHROMIUM_DIRS=(
      "$CONFIG/google-chrome"
      "$CONFIG/google-chrome-beta"
      "$CONFIG/chromium"
      "$CONFIG/BraveSoftware/Brave-Browser"
      "$CONFIG/microsoft-edge"
      "$CONFIG/vivaldi"
    )
    FIREFOX_DIRS=("$HOME/.mozilla")
    ;;
  *)
    echo "Sorry, only macOS and Linux are supported for now." >&2
    exit 1
    ;;
esac

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "python3 is required but wasn't found." >&2
  exit 1
fi

# 1. Copy the helper to a stable location, so the repo can be moved or deleted.
mkdir -p "$DATA/bin"
cp "$REPO_DIR/host/svtdl_queue.py" "$DATA/bin/svtdl_queue.py"
LAUNCHER="$DATA/bin/svtdl-queue"
cat > "$LAUNCHER" <<EOF
#!/bin/sh
exec "$PYTHON" "$DATA/bin/svtdl_queue.py" "\$@"
EOF
chmod +x "$LAUNCHER" "$DATA/bin/svtdl_queue.py"

# 2. Register the native messaging host with each browser.
json_list() {
  local first=1 item
  printf '['
  for item in "$@"; do
    [ $first -eq 1 ] || printf ', '
    printf '"%s"' "$item"
    first=0
  done
  printf ']'
}

origins=()
for id in "${CHROME_IDS[@]}"; do origins+=("chrome-extension://$id/"); done

installed=0
for dir in "${CHROMIUM_DIRS[@]}"; do
  if [ $ALL_BROWSERS -eq 1 ] || [ -d "$dir" ]; then
    mkdir -p "$dir/NativeMessagingHosts"
    cat > "$dir/NativeMessagingHosts/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "svtplay-dl Queue helper",
  "path": "$LAUNCHER",
  "type": "stdio",
  "allowed_origins": $(json_list "${origins[@]}")
}
EOF
    echo "Registered with: $dir"
    installed=$((installed + 1))
  fi
done

for dir in "${FIREFOX_DIRS[@]}"; do
  if [ $ALL_BROWSERS -eq 1 ] || [ -d "$dir" ]; then
    target="$dir/NativeMessagingHosts"
    [ "$(uname -s)" = "Linux" ] && target="$dir/native-messaging-hosts"
    mkdir -p "$target"
    cat > "$target/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "svtplay-dl Queue helper",
  "path": "$LAUNCHER",
  "type": "stdio",
  "allowed_extensions": ["$FIREFOX_ID"]
}
EOF
    echo "Registered with: Firefox ($dir)"
    installed=$((installed + 1))
  fi
done

if [ $installed -eq 0 ]; then
  echo "No supported browser found. Use --all-browsers to register anyway." >&2
  exit 1
fi

echo
echo "Helper installed in: $DATA"
if ! PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin" command -v svtplay-dl >/dev/null; then
  echo
  echo "Note: svtplay-dl wasn't found. Install it (e.g. 'brew install svtplay-dl'"
  echo "or 'pipx install svtplay-dl'), or set its path in the extension settings."
fi
echo
echo "Next: load the 'extension' folder in your browser (see README.md),"
echo "then restart the browser if it was already running."
