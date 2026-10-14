---
name: memory-reindex
description: Rebuild MEMORY.md as a topically-shelved index and split into a HOT index (auto-loaded) and ARCHIVE.md (cold shelves). Spawns a subagent to classify memories into topical shelves and tiers. Preserves hooks verbatim, verifies 1:1 coverage against filesystem, backs up old index, and validates canaries.
---

# memory-reindex

As new memories accumulate, they often land in a generic catch-all section or become fragmented. This skill reshelves the entire memory library into clean topical shelves without losing any content or detail.

**Safety stance:** The index is *derived* from the memory files, so rebuilding is reversible — but the curated hooks are hand-written and must not be paraphrased. Hooks are copied **verbatim**; only the *grouping* and *hot/cold tiering* changes. Never overwrite the live index without a backup and a mechanical coverage check.

## Steps

1. **Resolve the memory dir:**
   Run `python3 ~/.agents/skills/memory-lint/lint.py --print-dir` (checks `.agents/memory/`, `~/.gemini/config/projects/<slug>/memory/`, and `~/.claude/projects/<slug>/memory/`, walking up parent directories to `$HOME`).
   If absent, report to the user and stop.

2. **Audit current coverage:**
   List `*.md` files (excluding `MEMORY.md`, `ARCHIVE.md`, `CANDIDATES.md`, `CANARIES.md`). Extract the `file.md` target from every `- [..](file.md) —` line in `MEMORY.md`, `ARCHIVE.md` **and** `CANDIDATES.md` — `CANDIDATES.md` holds the lines `lint --fix` staged for files not yet in the hot index, so they are round-tripped into the rebuilt shelves rather than lost.
   - **Orphans** = files with no index line.
   - **Stale** = index lines whose target file no longer exists.
   Report both counts.

3. **Classify via Antigravity subagent:**
   Spawn a subagent via `invoke_subagent`:
   - `TypeName`: `"self"`
   - `Role`: `"Memory Reindex Classifier"`
   - `Model`: `"inherit"` (or `"flash"` / `"pro"` if explicitly requested)
   - `Prompt`:

   > Assign **every** memory file in `<DIR>` to exactly **one** topical shelf.
   > Scan descriptions via: `rg -N '^(name|description):' <DIR>/*.md` (ignore `MEMORY.md`/`ARCHIVE.md`).
   >
   > Shelves emerge from content — aim for ~8–15 substantive subjects (e.g. terminal/UI, proot/Linux, desktop/GPU, security/keys, networking/transports, email, mesh, release/CI workflow, process/collaboration, roadmap…). Avoid singletons; fold one-offs into broader shelves; `Misc` is a last resort.
   >
   > Mark every file `"hot"` or `"cold"` (a `tier` field in the shelf mapping):
   > - **Cold**: Resolved/shipped project history whose hook is a historical record, not an active constraint.
   > - **Hot**: `user`/`feedback`/`reference` types, recurring work, and any memory whose gotchas still constrain future code. When unsure, mark `hot`.
   >
   > **Usage evidence** (if `<DIR>/USAGE.log` exists):
   > Files with recent `used`/`recalled` activity stay hot. Guard: only demote based on usage if the log has ≥30 days of history.
   > Files listed in `<DIR>/CANARIES.md` with tier `hot` MUST stay hot regardless.
   >
   > **Coverage Gate (Verify mechanically before returning):**
   > Write your mapping to `<SCRATCH>/shelves.json` as `{"shelves":[{"name": "...", "files": [{"file": "...", "tier": "hot"}]}]}`.
   > Run:
   > `jq -r '.shelves[].files[].file' <SCRATCH>/shelves.json | sort`
   > and `comm` it against `ls <DIR> | grep -vE '^(MEMORY|ARCHIVE|CANDIDATES|CANARIES).md$' | sort`.
   > There must be **zero** duplicates, **zero** missing files, and **zero** extra files.
   >
   > Once coverage is clean, write `<DIR>/CANDIDATES.md` with:
   > - **Linking candidates**: Clusters of 2–5 memories that share a sub-thread and should cross-link via `[[wikilinks]]`.
   > - **Abstraction candidates**: Themes where ≥3 memories share a root cause or schema.
   >
   > Return: shelf names + counts, confirmation of 100% coverage, and candidate counts.

4. **Assemble `MEMORY.md.new` + `ARCHIVE.md.new` mechanically:**
   - `MEMORY.md.new` receives the hot entries of each shelf; `ARCHIVE.md.new` receives the cold ones under matching shelf headers.
   - Preamble in `MEMORY.md.new`: `Cold entries live in ARCHIVE.md (searched by /recall).`
   - Pull each existing `- [Title](file.md) — ...` line **verbatim** from the old index.
   - For an orphan, derive a concise human title and hook from the file.
   - Drop stale lines.

5. **Verify and run Canary Gate:**
   Assert that the union of files across both new index files equals the exact set on disk.
   Run canary check:
   ```bash
   python3 ~/.agents/skills/memory-lint/lint.py <DIR> --canary-check MEMORY.md.new ARCHIVE.md.new
   ```
   Exit code 1 means a load-bearing entry was dropped or demoted — do not proceed.

6. **Back up and confirm:**
   `cp MEMORY.md MEMORY.md.bak-$(date +%Y%m%d)` (and `ARCHIVE.md`).
   Show the summary (shelf counts, hot/cold split, size) and replace the live files upon verification.

## Claude Code variant

The steps above describe the Antigravity harness (`invoke_subagent`, `<SCRATCH>`). In Claude Code:

- Spawn the classifier with the built-in `Agent` tool instead of `invoke_subagent` — `subagent_type: "general-purpose"`, `model: "haiku"` (use `sonnet` for stores over ~150 memories), and lead the prompt with the same role text (`Role` is not a parameter there).
- The classifier needs **write** permission on the store: it writes `<SCRATCH>/shelves.json` and `<DIR>/CANDIDATES.md` itself. Instruct it to `Write` the files at absolute paths instead of `<SCRATCH>`.
- The parent agent assembles `MEMORY.md.new` / `ARCHIVE.md.new`, runs `python3 ~/.agents/skills/memory-lint/lint.py <DIR> --canary-check`, backs up and swaps (steps 4–6) as written.

The shelf rules, tiering and the mechanical coverage gate are unchanged.
