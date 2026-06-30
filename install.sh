#!/usr/bin/env bash
# Symlink the memory-consolidation skills into ~/.claude/skills/ so edits in this
# repo are live. Then merge hooks/settings.snippet.json into ~/.claude/settings.json
# to wire the SessionEnd/SessionStart lifecycle hooks (see README).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/.claude/skills"
mkdir -p "$dest"
for s in "$here"/skills/*/; do
  name="$(basename "$s")"
  rm -rf "$dest/$name"          # replace an existing copy/symlink (avoid ln nesting into a real dir)
  ln -s "${s%/}" "$dest/$name"
  echo "linked  $dest/$name -> ${s%/}"
done
echo
echo "Skills installed. Next: wire the lifecycle hooks by merging"
echo "  $here/hooks/settings.snippet.json"
echo "into ~/.claude/settings.json (merge the SessionStart/SessionEnd arrays if you"
echo "already have a \"hooks\" block). Verify with:"
echo "  python3 $here/skills/memory-lint/lint.py <memory_dir> --brief"
