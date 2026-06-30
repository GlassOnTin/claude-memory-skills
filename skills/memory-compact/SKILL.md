---
name: memory-compact
description: Shrink the MEMORY.md index by tightening over-length hooks to one true line, so the always-loaded index fits the harness's memory-loader cap and stops truncating. Lossy where reindex is lossless — so it is body-verified: a hook is shortened ONLY when its detail is recoverable from the memory's own file; hooks carrying index-only detail are kept verbatim and flagged, never silently dropped, and no memory file is edited. Backs up and shows before/after before replacing. Run after reindex when the index is still over budget.
---

# memory-compact

`reindex` reorganises but copies hooks **verbatim**, so it doesn't change size —
the index truncates because individual hooks have bloated to 3–5× the index's
own "~200 chars" rule. Compaction tightens the *pointers*. The fact lives in the
memory's file; the hook is only a pointer to it.

**The one rule: shrink the pointer, never the fact.** A hook is shortened only
when its detail is already recoverable from the body. Anything a hook carries
that the body doesn't (a commit SHA, a `★still-open` note, an `untested` flag)
would be *lost* by shortening — so those hooks are kept verbatim and flagged,
not trimmed, and no memory file is edited to "fix" them (that's the human's
call). This is the lossy op, so it is conservative by construction.

## Steps

1. **Resolve the dir** (`~/.claude/projects/$(pwd | sed 's#/#-#g')/memory/`) and
   operate on its live `MEMORY.md`.

2. **Find over-length hooks** — index lines longer than the threshold
   (default **250 chars**). Report the count and current bytes/lines.

3. **Rewrite — CHUNK across parallel `general-purpose` agents.** Reading a body
   costs ~10–16k tokens/hook, so one agent for a large set blows context/cost
   (119 hooks ≈ 2M tokens). **>~30 over-length hooks → split the over-length
   filenames into batches of ~20 and run one agent per batch in parallel**
   (≤~30 → a single agent is fine). Each agent gets its batch list + an output
   path `<SCRATCH>/compact_batchN.json` and this prompt (it returns hook **text
   only** — the `[Title](file.md) — ` prefix is preserved mechanically in step 4,
   so titles/filenames stay byte-exact):

   > For each filename in your batch: find its line in `MEMORY.md`
   > (`grep -F '(FILE)'`), note the old length, open the memory's file and read
   > the body. Produce a compacted hook — only the text after ` — `:
   > **≤180 chars** (≤300 if the old full line is >1000, a "giant"), a faithful
   > pointer **derived from the body** — *only if* every specific the old hook
   > carries (commit SHAs, `★still-open`/status notes, `untested`, version tags,
   > counts) is present in the body. If the old hook has anything the body does
   > **not**, set the value to `"KEEP"`. Write `{FILE: hooktext|"KEEP"}` JSON to
   > the output path. Edit no memory file. Return one line: `batch N: X, Y kept`.

4. **Assemble + verify, or abort.** Merge the batch JSONs into one
   `{file: hooktext|"KEEP"}` map (assert it covers exactly the over-length set).
   Build `MEMORY.md.compact` by walking the live `MEMORY.md`: for an over-length
   hook with a non-KEEP value, splice the **new text onto the original
   `[Title](file.md) — ` prefix** (titles/filenames byte-exact); KEEP and all
   short hooks stay verbatim. Then verify the `(file.md)` targets in
   `MEMORY.md.compact` equal those in the live `MEMORY.md`, each exactly once —
   compaction changes hook *text*, never membership. If anything dropped/added
   or a prefix didn't splice cleanly, do not replace; report it.

5. **Back up + confirm.** `cp MEMORY.md MEMORY.md.bak-$(date +%Y%m%d)` (skip if
   today's backup exists). Show: bytes/lines before→after, # compacted,
   the kept-long list, and 3–4 sample old→new hook diffs. Replace the live index
   only after the user is happy.

## Notes

- Body is the source of truth; the hook is a derived pointer. Compaction never
  invents — a shortened hook can only claim what the body holds.
- Kept-long hooks are a to-do, not a failure: move their index-only detail into
  the body, then re-run to compact them — or loosen the threshold.
- The size lever of the three: `reindex` (structure, lossless) → `memory-compact`
  (size, body-verified) → `recall` (retrieval). This is the one that targets the
  loader cap.
- Default 250→180 chars; tune for gentler or more aggressive.
