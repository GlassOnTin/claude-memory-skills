---
name: recall
description: Pull the few memory files relevant to a task by having a subagent triage the full memory directory, so the main context gets only the relevant memories instead of the (often truncated) MEMORY.md index. Use before starting a substantive task — especially git/release/workflow actions where a standing instruction may be sitting in an unloaded memory.
---

# recall

The auto-loaded `MEMORY.md` index is truncated when memory grows (it already
warns past ~200 lines), so a relevant standing instruction can be absent from
context exactly when it matters. This skill recovers it: a subagent reads the
*whole* memory directory's frontmatter and returns only the handful that bear
on the current task — its context absorbs the index, mine stays clean.

## Steps

1. **Find the task.** Use the argument after `/recall` as the task. If empty,
   infer it from the most recent user request in this conversation (one line).

2. **Resolve the memory dir** for the current project:
   ```
   ~/.claude/projects/$(pwd | sed 's#/#-#g')/memory/
   ```
   (cwd with every `/` → `-`; e.g. `/home/ian/Code/Haven` →
   `-home-ian-Code-Haven`.) If that directory doesn't exist, tell the user
   there's no memory store for this project and stop.

3. **Spawn ONE `Explore` subagent** with this prompt (fill in `<TASK>` and the
   resolved `<DIR>`):

   > You are triaging a memory store for relevance. The store is `<DIR>` — one
   > markdown file per memory, each with YAML frontmatter (`name`,
   > `description`, `metadata.type`).
   >
   > Task at hand: **<TASK>**
   >
   > 1. Read every memory's `description` cheaply in one pass:
   >    `rg -N '^(name|description):' <DIR>/*.md` (ignore `MEMORY.md`).
   > 2. Judge *semantic* relevance to the task, not keyword overlap — a memory
   >    about git branching IS relevant to "commit this" even with no shared
   >    words. Favour `feedback` and `project` memories that constrain how the
   >    task should be done.
   > 3. **Highest priority: memories that govern the *mechanics* of this exact
   >    action** — for a git task that means where commits go, branch vs.
   >    main, push policy, attribution, sign-off. These standing procedural
   >    rules outrank topically-adjacent memories (release notes, CI lint,
   >    terminology). Don't let a cluster of loud same-topic memories crowd out
   >    the one plain rule that dictates *how to do the thing*. If such a rule
   >    exists, it MUST be in your selection.
   > 4. Select **at most 5** genuinely relevant memories. Returning **zero** is
   >    correct when nothing applies — do not pad.
   > 5. Read each selected file in full and return, per memory:
   >    - its `name`,
   >    - one line on why it bears on this task,
   >    - the **verbatim body** (everything below the frontmatter).
   >
   > Return nothing else — no preamble, no summary of the store.

4. **Apply what comes back.** Surface any binding instruction to the user
   before acting on the task. Treat memory bodies as *written-at-the-time*
   facts: if one names a file, flag, or command, verify it still exists before
   relying on it.

## Notes

- One subagent, read-only; cost is a single fan-out, not per-turn.
- This is opt-in, so it only catches what you think to look up. If you find it
  missing things you didn't know to ask for, the next rung is a
  `UserPromptSubmit` hook that runs this automatically — don't build that until
  the misses are measured.
