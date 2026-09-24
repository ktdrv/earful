#!/bin/bash
# Morning AI Daily run: headless Claude Code researches and writes today's brief, then this
# script publishes it. Fired by launchd (~/Library/LaunchAgents/com.ktdrv.earful.ai-daily.plist);
# safe to run by hand. Args pass through to produce.py (e.g. --dry-run).
# CLAUDE=<binary> overrides claude, for testing.
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

SCRIPTS=$(uv run --no-project python -c 'import tomllib; print(tomllib.load(open("config.toml", "rb")).get("scripts_dir", "scripts"))')
MARKER=$(mktemp)
echo "$(date '+%F %T') start $*" >> "$LOG"

# The agent reads untrusted web pages with nobody watching, so it gets web research, reads of
# the repo and vault, and writes inside the vault folder only: no Bash, no repo edits, no .env.
# Anything else is denied rather than prompted. Publishing happens below, not in the agent,
# so a failed render or upload surfaces as this script's exit code.
"$CLAUDE" -p "/ai-daily today=$(date '+%A, %B %-d, %Y') scripts_dir=$SCRIPTS" --model opus \
  --add-dir "$SCRIPTS" \
  --allowedTools "WebSearch" "WebFetch" "Edit(/$SCRIPTS/**)" \
  --disallowedTools "Bash" "Read(./.env)" \
  --strict-mcp-config --permission-prompts none >> "$LOG" 2>&1
status=$?
new=$(find "$SCRIPTS" -name 'ai-daily-*.md' -newer "$MARKER" | head -1)
rm -f "$MARKER"

if [ $status -ne 0 ]; then
  fail "Research run failed (exit $status). See $LOG"
  exit 1
fi
if [ -z "$new" ]; then
  # claude -p exits 0 even when a denied tool stopped it short, so check for the artifact.
  fail "Run finished but wrote no episode. See $LOG"
  exit 1
fi
if ! uv run --no-project python produce.py "$new" --feed daily "$@" >> "$LOG" 2>&1; then
  fail "Publish failed for $(basename "$new"). See $LOG"
  exit 1
fi
echo "$(date '+%F %T') done" >> "$LOG"
