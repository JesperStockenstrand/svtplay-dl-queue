#!/usr/bin/env bash
# Remove the svtplay-dl Queue helper app and its browser registrations.
# Usage: ./uninstall.sh [--keep-data]   (--keep-data keeps queue and settings)
set -euo pipefail

HOST_NAME="svtplay_dl_queue"
APP="svtplay-dl-queue"
KEEP_DATA=0
[ "${1:-}" = "--keep-data" ] && KEEP_DATA=1

case "$(uname -s)" in
  Darwin)
    DATA="$HOME/Library/Application Support/$APP"
    shopt -s nullglob
    manifests=(
      "$HOME/Library/Application Support"/*/NativeMessagingHosts/$HOST_NAME.json
      "$HOME/Library/Application Support"/*/*/NativeMessagingHosts/$HOST_NAME.json
      "$HOME/Library/Application Support"/*/*/*/NativeMessagingHosts/$HOST_NAME.json
    )
    ;;
  Linux)
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP"
    CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
    shopt -s nullglob
    manifests=(
      "$CONFIG"/*/NativeMessagingHosts/$HOST_NAME.json
      "$CONFIG"/*/*/NativeMessagingHosts/$HOST_NAME.json
      "$HOME/.mozilla/native-messaging-hosts/$HOST_NAME.json"
    )
    ;;
  *) echo "Unsupported system." >&2; exit 1 ;;
esac

for m in "${manifests[@]}"; do
  rm -f "$m" && echo "Removed: $m"
done

if [ -x "$DATA/bin/svtdl-queue" ]; then
  # Stop a running worker; downloads in progress are canceled.
  pkill -f "$DATA/bin/svtdl_queue.py --worker" 2>/dev/null || true
fi

if [ $KEEP_DATA -eq 1 ]; then
  rm -rf "$DATA/bin"
  echo "Removed the helper. Queue and settings kept in: $DATA"
else
  rm -rf "$DATA"
  echo "Removed: $DATA"
fi
echo "Downloaded files are not touched. Remove the extension from your browser separately."
