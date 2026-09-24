#!/bin/bash
# Morning AI Daily run: headless Claude Code researches, writes and publishes today's brief.
# Fired by launchd (~/Library/LaunchAgents/com.ktdrv.earful.ai-daily.plist); safe to run by hand.
# Args pass through to /ai-daily (e.g. --dry-run). CLAUDE=<binary> overrides claude, for testing.
set -u
cd "$(dirname "$0")/.."
# launchd starts with a bare PATH; claude lives in ~/.local/bin, uv in ~/.cargo/bin.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
CLAUDE="${CLAUDE:-claude}"
LOG="$HOME/Library/Logs/earful-ai-daily.log"

fail() {
  echo "$(date '+%F %T') FAILED: $1" >> "$LOG"
  osascript -e "display notification \"$1\" with title \"Earful Daily\""
}

# Two Kokoro renders at once can exhaust this Mac's memory; yield to a manual render.
if pgrep -f "python.*produce\.py" > /dev/null; then
  fail "Skipped: another render is running. Rerun tools/ai-daily.sh when it's done."
  exit 1
fi

SCRIPTS=$(uv run --no-project python -c 'import tomllib; print(tomllib.load(open("config.toml", "rb")).get("scripts_dir", "scripts"))')
MARKER=$(mktemp)
echo "$(date '+%F %T') start $*" >> "$LOG"

# acceptEdits + --add-dir lets it write the script into the vault folder; the allowlist covers
# research and publishing; --permission-prompts none denies anything else instead of hanging.
"$CLAUDE" -p "/ai-daily $*" --model opus \
  --permission-mode acceptEdits --add-dir "$SCRIPTS" \
  --allowedTools "WebSearch" "WebFetch" "Bash(date)" "Bash(uv run --no-project python produce.py:*)" \
  --permission-prompts none >> "$LOG" 2>&1
status=$?

if [ $status -ne 0 ]; then
  fail "Run failed (exit $status). See $LOG"
elif [ -z "$(find "$SCRIPTS" -name 'ai-daily-*.md' -newer "$MARKER")" ]; then
  # claude -p exits 0 even when a denied tool stopped it short, so check for the artifact.
  fail "Run finished but wrote no episode. See $LOG"
  status=1
else
  echo "$(date '+%F %T') done" >> "$LOG"
fi
rm -f "$MARKER"
exit $status
