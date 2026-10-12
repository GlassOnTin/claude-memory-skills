---
name: memory-compact
description: Shrink over-length hooks in the MEMORY.md index while verifying fact recoverability from the underlying memory bodies. Parallelizes across subagents, validates canaries, and creates timestamped backups. Run when the index is over the target size threshold.
---

# memory-compact

`reindex` reorganizes the index losslessly without modifying hook text. When individual hooks bloat past ~250 chars, `memory-compact` tightens the pointers.

**The Golden Rule: Shrink the pointer, never the fact.** A hook is shortened only when its detail is already recoverable from the memory file's body. Anything a hook carries that the body does not (a specific commit SHA, a `★still-open` note, an untested flag) would be lost by shortening — so those hooks are kept verbatim and flagged, never trimmed.

## Steps

1. **Resolve memory directory:**
   - `.agents/memory/` or `~/.claude/projects/<slug>/memory/`.

2. **Find over-length hooks:**
   Identify index lines longer than 250 characters. Report the count and current size.

3. **Parallel rewrite via Antigravity subagents:**
   For >20 over-length hooks, partition into batches of ~15–20 files and launch parallel subagents in a single `invoke_subagent` call:
   - `TypeName`: `"self"`
   - `Role`: `"Memory Compaction Worker [Batch N]"`
   - `Model`: `"flash"`
   - `Prompt`:

   > For each filename in your batch: locate its line in `MEMORY.md` (`grep -F '(FILE)'`), read the memory's body in `<DIR>/<FILE>`, and generate a compacted hook (text after ` — `):
   > - Target length: **≤180 characters** (≤300 chars for giant hooks >1000 chars).
   > - Derived directly from the body.
   > - **Safety check**: If the original hook contains specific facts (SHAs, gotcha notes, versions) NOT present in the body, set the value to `"KEEP"`.
   > - Write `{FILE: hooktext | "KEEP"}` JSON to `<SCRATCH>/compact_batch_N.json`.
   > - Do not edit any memory files.

4. **Assemble and verify:**
   Merge batch JSON results.
   Build `MEMORY.md.compact` by splicing the new hook text onto the original `[Title](file.md) — ` prefixes.
   Verify that all `(file.md)` targets match the live `MEMORY.md` 1:1.
   Run canary validation:
   ```bash
   python3 ~/.gemini/config/skills/memory-lint/lint.py <DIR> --canary-check MEMORY.md.compact
   ```
   If any canary fails or prefixes mismatch, abort and report.

5. **Backup and confirm:**
   `cp MEMORY.md MEMORY.md.bak-$(date +%Y%m%d)`.
   Display before/after size, count of compacted hooks, and sample diffs. Replace live file upon confirmation.

## Claude Code variant

The steps above describe the Antigravity harness (`invoke_subagent`, `flash`, `<SCRATCH>`). In Claude Code:

- Workers: the built-in `Agent` tool instead of `invoke_subagent` — `subagent_type: "general-purpose"`, `model: "haiku"`, launched as several parallel Agent calls in **one message** (one per batch of ~15–20 files). Lead each prompt with the role text (`Role` is not a parameter there).
- Each worker `Write`s the same `{FILE: hooktext | "KEEP"}` JSON to an absolute scratch path outside the memory store (e.g. `/tmp/compact-batch-N.json`) instead of `<SCRATCH>/compact_batch_N.json`.
- Canary-gate path: `~/.gemini/config/skills/memory-lint/lint.py` → `~/.claude/skills/memory-lint/lint.py` (both are install symlinks to the same file).
- The parent agent does the splicing, 1:1 verification, backup and replace (steps 4–5) itself — same commands.

The Golden Rule, worker prompt and safety checks are harness-agnostic.
