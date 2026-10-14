---
name: recall
description: Pull the few memory files relevant to a task by having a fast subagent triage the project memory store (.agents/memory/ or legacy ~/.claude/projects/ memory), so the main agent context receives only the relevant procedural constraints instead of a bloated index. Use before starting a substantive task — especially git, release, or workflow actions.
---

# recall

The auto-loaded `MEMORY.md` index can be truncated or omitted when memory grows past token/line budgets, so a relevant standing instruction can be absent from context exactly when it matters. This skill recovers it: a fast subagent reads the *whole* memory directory's frontmatter and returns only the handful that bear on the current task — its context absorbs the search, the parent context stays clean and focused.

## Steps

1. **Identify the task.** Use the argument after `/recall` as the task. If empty, infer it from the most recent user request in this conversation (one concise line).

2. **Resolve the memory dir** for the current workspace:
   - Check `.agents/memory/` in the workspace root, or `~/.claude/projects/<slug>/memory/`, walking up parent directories to `$HOME` if a child repository does not have its own store yet (e.g. `python3 -c 'import sys; sys.path.insert(0, "/home/ian/.gemini/config/skills/memory-lint"); import lint; print(lint.find_memory_dir() or "")'`).
   - If no store exists, tell the user there is no memory store for this project and stop. Note: triage reads the *directory*, so memories listed in cold `ARCHIVE.md` are retrieved just like hot ones.

3. **Spawn ONE fast triage subagent** via `invoke_subagent`:
   - `TypeName`: `"research"`
   - `Role`: `"Memory Triage Researcher"`
   - `Model`: `"inherit"` (or `"flash"` if explicitly requested)
   - `Prompt`:

   > You are triaging a project memory store for relevance to a task.
   > The memory store directory is: `<DIR>` (one markdown file per memory, each with YAML frontmatter `name`, `description`, `metadata.type`).
   >
   > Task at hand: **<TASK>**
   >
   > 1. Read every memory's `description` cheaply in one pass via Bash:
   >    `rg -N '^(name|description):' <DIR>/*.md` (ignore `MEMORY.md` and `ARCHIVE.md`).
   > 2. Judge *semantic* relevance to the task, not just keyword overlap — a memory about git branching IS relevant to "commit this" even with no shared words. Favour `feedback` and `project` memories that constrain how the task should be executed.
   > 3. **Highest priority: memories that govern the *mechanics* of this exact action** — for a git task, that means where commits go, branch vs. main, push policies, attribution, sign-offs, and auth requirements. These standing procedural rules outrank topically-adjacent informational memories (release notes, CI logs, terminology). If such a governing rule exists, it MUST be in your selection.
   > 4. Select **at most 5** genuinely relevant memories. Returning **zero** is correct when nothing applies — do not pad.
   > 5. Read each selected file in full and return, per memory:
   >    - its `name`,
   >    - one line explaining why it bears on this task,
   >    - the **verbatim body** (everything below the frontmatter).
   > 6. Log your selections to the usage log for hindsight data:
   >    `printf '%s\trecalled\t%s\n' "$(date +%FT%T)" "<file.md>" >> <DIR>/USAGE.log`
   >
   > Return nothing else — no preamble, no general summary of the store.

4. **Apply retrieved constraints.** Surface any binding instruction or policy to the user before acting on the task. Treat memory bodies as *written-at-the-time* facts: if one names a file, flag, or command, verify it still exists before relying on it.

5. **Close the hindsight loop.** If a recalled memory actually changed or guided what you did (blocked a wrong action, supplied the command, set the policy), append a `used` event:
   ```bash
   printf '%s\tused\t%s\n' "$(date +%FT%T)" "<file.md>" >> <DIR>/USAGE.log
   ```
   `recalled` records retrieval; `used` records impact — reindexing weighs `used` far above `recalled`.

## Notes

- One subagent call with `flash` model: fast, low token overhead, zero main-context bloat.
- Opt-in: call before high-stakes operations (rebases, tag releases, publishing, major refactors).

## Claude Code variant

The steps above describe the Antigravity harness. In Claude Code:

- Spawn the triage researcher with the built-in `Agent` tool instead of `invoke_subagent` — `subagent_type: "general-purpose"`, `model: "haiku"`, prompt unchanged (the `Role`/`TypeName` fields become the first line of the prompt text).
- The parent receives the researcher's final report as the tool result; apply step 4 and the usage-log loop as written.
- `rg -N '^(name|description):' <DIR>/*.md` runs the same in the Claude Code Bash shell.

The selection rules (mechanics-outrank-neighbours, at most 5, zero-is-correct) are the point of the skill — keep them verbatim in the prompt.
