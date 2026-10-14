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

agy_hooks="$HOME/.gemini/config/hooks.json"
if [ ! -f "$agy_hooks" ]; then
  cp "$here/hooks/agy_hooks.snippet.json" "$agy_hooks"
  echo "installed $agy_hooks"
else
  python3 - "$agy_hooks" "$here/hooks/agy_hooks.snippet.json" <<'PY'
import json, sys
dst_p, src_p = sys.argv[1], sys.argv[2]
dst = json.load(open(dst_p, encoding="utf-8"))
src = json.load(open(src_p, encoding="utf-8"))
dst.update(src)
json.dump(dst, open(dst_p, "w", encoding="utf-8"), indent=2)
print(f"merged memory-guardian into {dst_p}")
PY
fi

echo
echo "Skills and Antigravity hooks installed across Antigravity and Claude Code."
echo "Verify with:"
echo "  python3 $here/skills/memory-lint/lint.py --brief"
