---
name: memory-reindex
description: Rebuild MEMORY.md as a topically-shelved index — a library classification for the memory store. A subagent assigns every memory file to exactly one topical shelf; the curated one-line hooks are preserved verbatim, and orphan files (present in the store but missing from the index) are found and shelved too. Coverage is verified (every file appears once, no phantom lines), the old index is backed up, and the reorg is shown before replacing. Run when the index is lopsided — giant catch-all buckets, a tail of one-entry sections — or after adding several memories.
---

# memory-reindex

The index drifts: new memories land in a catch-all `## Gotchas` pile, topics
fragment into one-entry sections, and some files never get an index line at all
(orphans — invisible to the always-loaded index). This reshelves the whole
library: every memory under one topical heading, nothing lost.

**Safety stance:** the index is *derived* from the files, so rebuilding it is
reversible — but the curated hooks are hand-written and must not be paraphrased.
So hooks are copied **verbatim**; only the *grouping* changes. Never overwrite
the live index without a backup and a coverage check.

## Steps

1. **Resolve the memory dir:** `~/.claude/projects/$(pwd | sed 's#/#-#g')/memory/`.
   If absent, say so and stop.

2. **Audit coverage.** List `*.md` (excluding `MEMORY.md`). Extract the
   `file.md` target from every `- [..](file.md) —` line in the current index.
   - **Orphans** = files with no index line.
   - **Stale** = index lines whose target file no longer exists.
   Report both counts.

3. **Classify — one `general-purpose` subagent that self-verifies and writes
   the result to disk** (an `Explore` agent can't, because it can only return
   text and won't catch its own miscount — observed: a classifier confidently
   reported "no duplicates, complete coverage" while six files were shelved
   twice). Prompt it with the dir and:

   > Assign **every** memory file to exactly **one** topical shelf. Get the
   > files + signals via `rg -N '^(name|description):' <DIR>/*.md` (ignore
   > `MEMORY.md`). Shelves emerge from content — aim for ~8–15 real subjects
   > (terminal/keyboard, proot & local Linux, desktop/GPU, FIDO/security,
   > networking/transports, email, mesh/Reticulum, release & CI workflow,
   > collaboration & process, roadmap/upcoming…). No shelf over ~25 (split it);
   > fold one-offs into a broader shelf, not singletons; `Misc` is a last
   > resort.
   >
   > **Before returning, prove coverage against the filesystem and fix any gap
   > — do not self-report, check:** write your mapping to `<SCRATCH>/shelves.json`
   > as `{"shelves":[{"name":..,"files":[..]}]}`, then run
   > `jq -r '.shelves[].files[]' <SCRATCH>/shelves.json | sort` and `comm` it
   > against `ls <DIR> | grep -v '^MEMORY.md$' | sort`. There must be **zero**
   > duplicates (`... | uniq -d` empty) and **zero** files only-on-disk and
   > **zero** entries only-in-json. Iterate until clean.
   >
   > Once coverage is clean, do ONE cheap extra pass over the **same
   > descriptions** (don't open every file) and write `<DIR>/CANDIDATES.md` —
   > the backlog for later, deeper consolidation passes. Two short sections,
   > each capped at ~8 entries, each item clearly heuristic:
   > - **Linking candidates** — clusters of 2–5 memories (usually within one
   >   shelf) that read as the same sub-thread and probably should cross-link
   >   via `[[wikilinks]]`. List the members + one line on the shared thread.
   > - **Abstraction candidates** — themes where ≥3 memories share a root cause
   >   or schema that could collapse into one higher-order memory. List the
   >   members + a one-line proposed schema (e.g. several "act as the
   >   maintainer" rules → one rule).
   > These are advisory only — do NOT modify shelves.json, the index, or any
   > memory file. Then return: shelf names + counts, the three coverage checks
   > (all empty), candidate counts, and confirmation both files exist.

4. **Assemble `MEMORY.md.new`** mechanically (small script, not by hand):
   - Preamble: keep the current file's header lines (down to the first `## `).
   - For each shelf in the subagent's order: emit `## <Shelf>`, then for each
     file pull its **existing** `- [..](file.md) — ...` line **verbatim** from
     the old index. For an **orphan** (no old line), read the file and write a
     fresh `- [Title](file.md) — <hook>` line (≤200 chars). Derive a **short
     human `[Title]` from the body** (3–8 words, like the other titles) — do NOT
     use the `name:` slug as the title, or reindex becomes a slug-title factory
     (lint flags those). The hook is a one-line summary of the body.
   - Drop **stale** lines (their files are gone).

5. **Verify, or abort.** Assert the set of `file.md` targets in `MEMORY.md.new`
   equals the set of `*.md` files on disk, each exactly once. If not, do not
   replace — report the discrepancy.

6. **Back up + confirm.** `cp MEMORY.md MEMORY.md.bak-$(date +%Y%m%d)`. Show the
   user: new shelf names + counts, orphans now shelved, stale lines dropped.
   Replace the live index only after they're happy (first run especially —
   the classification is unproven until they've seen it).

## Notes

- Single shelf per memory (one shelf location); cross-topic links stay as
  `[[wikilinks]]` in the bodies — that's the catalog cross-reference.
- This restructures the index only; it never edits or deletes memory files.
- Pairs with `recall`: reindex keeps the passive index legible; recall does
  task-targeted retrieval. Different jobs.
- `CANDIDATES.md` (written beside the index) is the backlog for the deeper
  consolidation passes this skill *doesn't* do yet — **linking** (wire the
  `[[links]]` it flags) and **abstraction** (distil a schema across kin). It's
  heuristic and is **not** loaded into context, so it adds no truncation
  pressure; build those passes only when the backlog visibly piles up. The
  triage pass tagging work for the deeper passes mirrors how slow-wave sleep
  marks what later REM integrates — cheap-frequent feeds deep-rare.
