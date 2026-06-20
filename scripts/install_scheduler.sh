#!/usr/bin/env bash
# Install a recurring schedule that runs the desk every 15 minutes during US
# market hours (Mon–Fri). macOS → launchd; Linux → cron. Re-run to update.
#   bash scripts/install_scheduler.sh          # install
#   bash scripts/install_scheduler.sh --remove # uninstall
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.sahjony.trading"
RUN="$REPO/scripts/run.sh"
chmod +x "$RUN" 2>/dev/null || true

remove() {
  if [[ "$(uname)" == "Darwin" ]]; then
    launchctl unload "$HOME/Library/LaunchAgents/$LABEL.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
    echo "Removed launchd agent $LABEL."
  else
    crontab -l 2>/dev/null | grep -v "$RUN" | crontab - || true
    echo "Removed cron entry."
  fi
}

if [[ "${1:-}" == "--remove" ]]; then remove; exit 0; fi

if [[ "$(uname)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  # 13:30–20:00 UTC ≈ US cash session; launchd uses local time, so adjust if needed.
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$RUN</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>$REPO/logs/cron.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/cron.err.log</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Installed launchd agent $LABEL (every 15 min)."
  echo "The desk itself skips trading when the market is closed, so off-hours ticks just report."
else
  LINE="*/15 13-20 * * 1-5 $RUN >> $REPO/logs/cron.out.log 2>&1"
  ( crontab -l 2>/dev/null | grep -v "$RUN"; echo "$LINE" ) | crontab -
  echo "Installed cron entry (every 15 min, 13:00–20:00 UTC, Mon–Fri):"
  echo "  $LINE"
fi
