#!/usr/bin/env bash
# Symlinks memory skills into:
# 1. Antigravity Global: ~/.gemini/config/skills/
# 2. Agent Ecosystem:    ~/.agents/skills/
# 3. Claude Code:        ~/.claude/skills/
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

for dest in "$HOME/.gemini/config/skills" "$HOME/.agents/skills" "$HOME/.claude/skills"; do
  mkdir -p "$dest"
  for s in "$here"/skills/*/; do
    name="$(basename "$s")"
    rm -rf "$dest/$name"
    ln -s "${s%/}" "$dest/$name"
    echo "linked  $dest/$name -> ${s%/}"
  done
done

echo
echo "Skills installed across Antigravity and Claude Code."
echo "For Antigravity hooks, merge hooks/agy_hooks.snippet.json into ~/.gemini/config/hooks.json or .agents/hooks.json."
echo "Verify with:"
echo "  python3 $here/skills/memory-lint/lint.py --brief"
