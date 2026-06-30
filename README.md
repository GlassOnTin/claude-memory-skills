# claude-memory-skills

A small, self-maintaining toolkit for **Claude Code's file-based memory store** —
four skills and two lifecycle hooks that keep the always-loaded `MEMORY.md` index
legible, compact, and internally consistent so standing rules don't silently
vanish when the index grows past the loader cap.

These are generic: they resolve the memory directory from the current project, so
they work for any project, not a specific one. Nothing here is coupled to a
particular codebase.

## The problem

Claude Code auto-loads a per-project `MEMORY.md` index every session. As memories
accumulate the index bloats; past a size/line cap the loader **truncates** it —
so a standing instruction sitting in an unloaded entry is absent from context
exactly when it matters. (The motivating failure: a "commit on main, don't
branch" rule was truncated out, and the agent auto-branched against it.)

## The skills

| skill | does | when |
|---|---|---|
| **`recall`** | a subagent triages the whole store and returns the few memories relevant to a task — so the right ones surface even when the index truncated | before a substantive task, especially git/release/workflow actions |
| **`memory-reindex`** | rebuild `MEMORY.md` as topical shelves; hooks copied **verbatim** (lossless), coverage-verified against the filesystem, orphans recovered; emits a `CANDIDATES.md` backlog | when the index is lopsided, or after adding several memories |
| **`memory-compact`** | shorten over-length index hooks to one line, **body-verified** (only shortens when the fact is recoverable from the memory's own body, else keeps + flags) — the size lever | when the index is still over the loader cap after reindexing |
| **`memory-lint`** | the doctor: a real script (`lint.py`) asserting every invariant, with `--fix` for the deterministic repairs and `--brief` for a one-line health summary | after manual edits, after adding memories, or as a lifecycle hook |

**Pass order:** `recall` (retrieve) → `reindex` (structure) → `compact` (size) →
`lint` (assert / repair). Run `lint` last to confirm clean.

## Invariants `memory-lint` enforces

```
$ python3 skills/memory-lint/lint.py <memory_dir> [--fix|--brief]
```

- `name:` frontmatter **equals the filename-stem** (links resolve against `name:`)
- every `[[wikilink]]` **resolves** to a real memory
- **no slug titles** in the index (`[project_foo.md]` → a human title)
- the index is **1:1 with the files** (no orphans, no stale lines)
- **no bloated hooks** (hook text ≤ 300 chars)

`--fix` does only the safe, deterministic repairs (normalise `name:`→stem, rewrite
`[[links]]` to stems), backing up to `<dir>/.backups/` **only when it actually
changes something**. Coverage / over-length / slug-titles route to
`reindex`/`compact` — they need judgement, not a blind rewrite. Exit code is 0
when clean, 1 on any violation (so it works as a hook or CI gate).

## Lifecycle hooks (optional, recommended)

Wire `memory-lint` into Claude Code's session lifecycle so the store
self-maintains. Merge `hooks/settings.snippet.json` into `~/.claude/settings.json`:

- **SessionEnd** → `lint --fix`: auto-heals name/link drift and appends a
  timestamped report to `~/.claude/memory-lint.log`. Never fails the session;
  skips cleanly for projects with no store.
- **SessionStart** → `lint --brief`: injects a one-line store-health summary into
  the new session's context (e.g. `clean ✓ (165 memories)`), silent when there's
  no store.

So drift is auto-detected, the cheap part auto-repaired, and structural issues
(coverage/bloat) surfaced for a deliberate `reindex`/`compact`.

## Install

```sh
./install.sh          # symlinks skills/* into ~/.claude/skills/
```

Then merge `hooks/settings.snippet.json` into `~/.claude/settings.json` (it adds a
`hooks` block; if you already have one, merge the `SessionStart`/`SessionEnd`
arrays by hand).

## Memory-store contract

The skills assume the standard Claude Code layout:

- store dir: `~/.claude/projects/<cwd-with-slashes-as-dashes>/memory/`
- one markdown file per memory, frontmatter `name` / `description` / `metadata.type`
  (`user` | `feedback` | `project` | `reference`)
- `MEMORY.md` is the index: `## Shelf` headers, then one
  `- [Title](file.md) — hook` line per memory
- bodies cross-link with `[[filename-stem]]`; **`name:` is kept equal to the
  stem** so links resolve by filename

## Design notes

- **Cheap-frequent vs expensive-rare.** `recall`/`lint` are cheap and run often;
  `reindex`/`compact` are the rare, expensive deep passes (a full compact can run
  to millions of tokens across chunked agents — amortise, never nightly).
- **Lossless vs lossy is explicit.** `reindex` copies hooks verbatim (provably
  loses nothing). `compact` rewrites them, so it is body-verified — *shrink the
  pointer, never the fact*.
- **Gates over trust.** Every pass verifies its own output mechanically
  (coverage `comm`-vs-`ls`, body-recoverability, link resolution) — a subagent's
  self-report is not trusted.
- **One known limitation:** `lint` can't tell an example `[[link]]` written in
  prose from a real one — don't write a literal `[[X]]` in a memory body unless
  `X` is a real memory.
