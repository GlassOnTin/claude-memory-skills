---
name: memory-lint
description: Audit the memory store against its invariants and report violations with the remedy for each — name equals filename-stem, every [[link]] resolves, no slug titles in the index, 1:1 file coverage, canary preservation, and hook size limits. Supports --fix for safe automated repairs and integrates with Antigravity lifecycle hooks.
---

# memory-lint

The mechanical doctor for the memory store. It asserts all store invariants so drift is detected and repaired deterministically rather than silently rotting.

## Running the Linter

```bash
python3 ~/.agents/skills/memory-lint/lint.py [<memory_dir>] [--fix|--brief|--print-dir|--canary-check]
```

(`~/.agents/skills/`, `~/.gemini/config/skills/`, and `~/.claude/skills/` all
symlink to the same `lint.py`. If `<memory_dir>` is omitted, `lint.py`
automatically resolves `.agents/memory/`, `~/.gemini/config/projects/<slug>/memory/`,
or `~/.claude/projects/<slug>/memory/`, walking up parent directories to `$HOME`.)

## Invariants Enforced

| Invariant | Purpose | Remedy |
| :--- | :--- | :--- |
| `name:` == filename-stem | `[[links]]` resolve cleanly against stems | `lint.py --fix` |
| Every `[[link]]` resolves | Prevents dead/dangling cross-references | `lint.py --fix` (auto) / manual |
| No slug titles in index | Index remains human-readable | `memory-reindex` |
| Index 1:1 with files | Prevents invisible orphan files or stale links | `lint.py --fix` orphans stage into `CANDIDATES.md`; `memory-reindex` shelves them |
| `description:` present & non-empty | Orphan staging borrows it for the hook text | write one by hand |
| Index lines parse | Malformed `- [..](..) — hook` lines would hide as coverage noise | hand-edit or `memory-reindex` |
| Hook length ceiling | Prevents index bloat | `memory-compact` |
| Canary retention | Asserts load-bearing rules survive in index | Restore from backup / fix hook |

`--fix` never auto-promotes staged orphans into `MEMORY.md` — a file indexed only
in `CANDIDATES.md` is reported as *staged* (not a violation) and stays pending
until a `memory-reindex` pass shelves it. Unparseable index lines and missing
descriptions are flagged, never auto-rewritten (no data-losing repairs).

## Antigravity Lifecycle Hook Integration

Installed by `./install.sh` into `~/.gemini/config/hooks.json` (or `.agents/hooks.json`):

```json
{
  "memory-guardian": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "python3 ~/.agents/skills/memory-lint/lint.py --hook-pre-invocation"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "view_file",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.agents/skills/memory-lint/lint.py --hook-post-tool"
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 ~/.agents/skills/memory-lint/lint.py --hook-stop"
      }
    ]
  }
}
```
