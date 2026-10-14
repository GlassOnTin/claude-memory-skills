# memory-skills

A small, self-maintaining toolkit for **file-based agent memory stores** (shared across **Antigravity / Gemini** and **Claude Code**) —
four skills and lifecycle hooks that keep the always-loaded `MEMORY.md` index
legible, compact, and internally consistent so standing rules don't silently
vanish when the index grows past the loader cap.

These are generic: they resolve the memory directory from the current project
(checking `.agents/memory/`, `~/.gemini/config/projects/<slug>/memory/`, and
`~/.claude/projects/<slug>/memory/`, walking up parent directories toward `$HOME`),
so they work for any project and either harness.

## The problem

Agents auto-load a per-project `MEMORY.md` index every session. As memories
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
$ python3 ~/.agents/skills/memory-lint/lint.py [<memory_dir>] [--fix|--brief|--print-dir]
```

- `name:` frontmatter **equals the filename-stem** (links resolve against `name:`)
- every `[[wikilink]]` **resolves** to a real memory
- `description:` frontmatter **present and non-empty** (orphan staging borrows it)
- **no slug titles** in the index (`[project_foo.md]` → a human title)
- the index is **1:1 with the files** (no orphans, no stale or duplicate lines)
- every index line **parses** as `- [Title](file.md) — hook` (empty hooks/malformed lines are flagged, not rewritten)
- **no bloated hooks** (hook text ≤ 300 chars)

`--fix` does only the safe, deterministic repairs (normalise `name:`→stem, rewrite
`[[links]]` to stems, drop stale/duplicate index lines, **stage** orphans into
`CANDIDATES.md` under a dated header), backing up to `<dir>/.backups/` **only when
it actually changes something** (and keeping the newest 5 backups). It never
auto-promotes staged lines into the hot index — a file indexed only in
`CANDIDATES.md` is reported as *staged* and stays pending until a `memory-reindex`
pass shelves it. Malformed index lines, missing descriptions, over-length hooks
and slug-titles are flagged with a remedy, never auto-repaired. Exit code is 0
when clean, 1 on any violation (so it works as a hook or CI gate).

## Lifecycle hooks (optional, recommended)

Wire `memory-lint` into Antigravity (`~/.gemini/config/hooks.json`) and Claude Code
(`~/.claude/settings.json`) so the store self-maintains across both harnesses:

- **SessionStart / PreInvocation** → injects a one-line store-health summary
  (`lint --brief`) and, in Antigravity, injects the project's `MEMORY.md` hot
  index once per conversation.
- **PostToolUse (`view_file` / `Read`)** → appends `<timestamp>\tread\t<file.md>`
  to the store's `USAGE.log` whenever a memory file is read.
- **SessionEnd / Stop** → `lint --fix`: auto-heals name/link drift, stages orphans
  into `CANDIDATES.md`, and appends a timestamped report to
  `~/.agents/memory-lint.log` (trimmed to its newest ~4000 lines past 1 MB).

So drift is auto-detected, the cheap part auto-repaired, and structural issues
(coverage/bloat) surfaced for a deliberate `reindex`/`compact`.

## Harnesses

`install.sh` symlinks the skills into `~/.agents/skills/` (shared canonical path),
`~/.gemini/config/skills/` (Antigravity), and `~/.claude/skills/` (Claude Code),
and installs `hooks/agy_hooks.snippet.json` into `~/.gemini/config/hooks.json` —
one toolkit, both harnesses. `lint.py` is harness-agnostic. The other three skills
describe both Antigravity (`invoke_subagent`) and Claude Code (`Agent` tool)
invocation mechanics so they translate 1:1.

## Install

```sh
./install.sh          # symlinks skills/* into ~/.agents/skills/, ~/.gemini/config/skills/, and ~/.claude/skills/
```

For Claude Code hooks, merge `hooks/settings.snippet.json` into `~/.claude/settings.json`.

## Memory-store contract

The skills resolve the store directory in order (walking up parent directories to `$HOME`):

- `.agents/memory/` in the project/workspace root
- `~/.gemini/config/projects/<cwd-with-slashes-as-dashes>/memory/`
- `~/.claude/projects/<cwd-with-slashes-as-dashes>/memory/`
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

## How it came about

This started from a single failure. An agent doing a routine task in a repo —
"commit and push this" — created a feature branch, contradicting a standing
"commit directly on main, don't branch" rule the maintainer had set. The rule
existed as a memory, but the `MEMORY.md` index had grown past the loader's cap
(281 lines / ~69 KB) and was being truncated on load, so that entry was simply
absent from context. The rule was there; it just never arrived.

The fix came in layers, each exposing the next:

- **Retrieval first** (`recall`) — pull the memories relevant to a task even when
  the index truncated. Its first version missed the very rule that motivated it;
  tuning it to prioritise memories that govern the *mechanics* of an action over
  topically-loud neighbours fixed that.
- **Then the index itself** (`memory-reindex`) — the flat catch-all was reshelved
  into topics, which surfaced 6 memories with no index entry at all (invisible to
  every session) and one classifier that confidently misreported its own coverage
  — hence the `comm`-vs-`ls` gate that doesn't trust self-reports.
- **Then size** (`memory-compact`) — reshelving didn't shrink anything (hooks
  copied verbatim); the bloat was the hooks themselves, 3–5× their own length
  guideline. Body-verified compaction roughly halved the index.
- **Then consistency** — fixing titles and wiring cross-links exposed that the
  link graph rested on inconsistent `name:` fields; a normalisation pass made
  `name == stem` everywhere so links resolve by filename.
- **Then "is this actually repeatable?"** — it wasn't: compaction's chunking
  wasn't codified, reindex re-introduced slug titles, and nothing *asserted* the
  invariants. That gap became `memory-lint` and the lifecycle hooks that run it.

A recurring analogy shaped the order: sleep consolidation is staged — light,
frequent filing feeds rarer, deeper integration and abstraction. The toolkit
mirrors that: cheap-frequent (`recall`, `lint`) vs expensive-rare (`reindex`,
`compact`, plus a one-off pass that distils recurring incidents into higher-order
schemas). The guiding rule throughout was to verify rather than trust — every
pass checks its own output mechanically, because a plausible-but-wrong
self-report is exactly how the original rule went missing.
