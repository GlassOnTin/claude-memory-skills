---
name: memory-lint
description: Audit the memory store against its invariants and report violations with the remedy for each — name: equals filename-stem, every [[link]] resolves, no slug titles in the index, the index is 1:1 with the files, no bloated hooks. `--fix` applies only the deterministic repairs (normalise name:→stem, rewrite [[links]] to stems); coverage/over-length/slug-titles route to reindex/compact. Run after manual edits, after adding memories, or as a SessionEnd health check.
---

# memory-lint

The doctor for the store — the one place the invariants the other skills assume
are actually *asserted*, so drift gets caught instead of silently rotting. The
deterministic checks live in `lint.py` (don't re-derive them in the model):

```
python3 ~/.claude/skills/memory-lint/lint.py <memory_dir> [--fix]
```

Resolve `<memory_dir>` as `~/.claude/projects/$(pwd | sed 's#/#-#g')/memory`.
Exit 0 = clean, 1 = violations (so it works as a SessionEnd hook / CI gate).

## What it asserts (and the remedy it prints)

| invariant | why | remedy if it fails |
|---|---|---|
| `name:` == filename-stem | `[[links]]` resolve against `name:`; one convention only | `lint --fix` |
| every `[[link]]` resolves | dangling cross-refs are dead | `lint --fix` (auto), else manual for the unresolvable |
| no slug titles in the index | `[project_foo.md]` is unreadable | `memory-reindex` (orphans) / retitle from body |
| index 1:1 with files | orphans are invisible, stale lines are dead | `memory-reindex` |
| no hook text > 300 chars | bloat is what truncates the index | `memory-compact` |

## `--fix` — only the safe, deterministic repairs

Backs up the whole store to `<dir>/.backups/lint-fix-<ts>.tar.gz` first, then:
- sets every `name:` to its filename-stem,
- rewrites every `[[link]]` to the target's stem (strips a stray `.md`, and
  resolves an old kebab/sentence name to its file by **unique** fuzzy match;
  ambiguous or unmatched links are left and reported).

It deliberately does **not** touch coverage (→ `memory-reindex`), over-length
hooks (→ `memory-compact`), or slug titles (judgement — retitle from the body).
So `--fix` is idempotent and never guesses a destructive change.

## Notes

- This encodes the one-off name/link normalisation as a repeatable pass — the
  convention is now enforceable, not just a cleanup that happened once.
- Pairs with the others: lint **detects** → reindex (structure) / compact (size)
  / lint --fix (names+links) **repair**. Run lint last to confirm clean.
