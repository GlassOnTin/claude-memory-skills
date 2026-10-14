#!/usr/bin/env python3
"""memory-lint — assert the memory store's invariants across Antigravity & Claude Code.

Usage:  lint.py [<memory_dir>] [--fix] [--brief] [--canary-check]
                [--hook-pre-invocation] [--hook-post-tool] [--hook-stop]
  (no dir)              → auto-resolves memory dir (.agents/memory or ~/.claude/projects/<slug>/memory,
                          walking up parent directories to $HOME if the child repo has no own store)
  --fix                 → back up, then apply DETERMINISTIC repairs only:
                          name: → filename-stem, rewrite [[links]] to stems
                          (.md-strip + unique fuzzy match), drop stale/duplicate index
                          lines, and STAGE orphan index lines in CANDIDATES.md
                          (never auto-promoted into MEMORY.md); keeps the newest
                          5 lint-fix backups in .backups/.
  --brief               → one-line health summary.
  --canary-check        → verify canaries survive in candidate index files.
  --hook-pre-invocation → Antigravity PreInvocation hook (loads MEMORY.md + brief summary once per conversation).
  --hook-post-tool      → Antigravity/Claude PostToolUse hook (logs view_file/Read of memory files to USAGE.log).
  --hook-stop           → Antigravity Stop hook (runs safe repairs + logs to ~/.claude/memory-lint.log).

Exit 0 if every invariant passes, 1 if any fails (hook/CI friendly).
"""
import contextlib, json, os, re, subprocess, sys, time, tarfile

# CANDIDATES.md is a staging area, not an index for coverage: a file indexed
# only there is "staged" (visible in report/brief), not an orphan and not hot.
INDEXES = ["MEMORY.md", "ARCHIVE.md", "CANDIDATES.md"]
SKIP = {"MEMORY.md", "ARCHIVE.md", "CANDIDATES.md", "CANARIES.md"}
OVER = 300  # hook-text length ceiling (== compact's giant allowance)
HOTCAP = 24_000  # bytes; loader cap guidance

def _resolve_from_dir(start_dir):
    """Walk from start_dir up to $HOME looking for a real memory store
    (.agents/memory/MEMORY.md or ~/.claude/projects/<slug>/memory/MEMORY.md)."""
    cur = os.path.abspath(start_dir)
    home = os.path.abspath(os.path.expanduser("~"))
    visited = set()
    while cur and cur not in visited:
        visited.add(cur)
        cand1 = os.path.join(cur, ".agents", "memory")
        if os.path.isfile(os.path.join(cand1, "MEMORY.md")):
            return cand1
        slug = cur.replace("/", "-")
        cand2 = os.path.expanduser(f"~/.claude/projects/{slug}/memory")
        if os.path.isfile(os.path.join(cand2, "MEMORY.md")):
            return cand2
        if cur == home or cur == "/":
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None

def find_memory_dir(target=None):
    if target and os.path.isdir(target):
        return os.path.abspath(target)
    if target and not target.startswith("--"):
        return None
    # Check if current directory is already a memory directory
    if os.path.exists("MEMORY.md"):
        return os.path.abspath(".")
    # Find workspace/repo root
    try:
        root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        root = os.getcwd()

    found = _resolve_from_dir(root)
    if found:
        return found
    # Fallback to exact directory even if MEMORY.md isn't created yet but dir has .md files
    cand1 = os.path.join(root, ".agents", "memory")
    if os.path.isdir(cand1):
        return cand1
    slug = root.replace("/", "-")
    cand2 = os.path.expanduser(f"~/.claude/projects/{slug}/memory")
    if os.path.isdir(cand2):
        return cand2
    return None

def files():   return [f for f in os.listdir(".") if f.endswith(".md") and f not in SKIP]
def stemset(): return set(f[:-3] for f in files())

def fm_name(text):
    if not text.startswith("---"): return None
    end = text.find("\n---", 3); fm = text[:end] if end > 0 else text
    m = re.search(r'^name:\s*(.+)$', fm, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None

def fm_description(f):
    text = open(f, encoding="utf-8").read()
    if not text.startswith("---"): return ""
    end = text.find("\n---", 3); fm = text[:end] if end > 0 else text
    m = re.search(r'^description:\s*(.+)$', fm, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""

def strip_pfx(s): return re.sub(r'^(project|feedback|reference|plan)_', '', s)
LINK = re.compile(r'\[\[([A-Za-z0-9_.\-]+)\]\]')
# hook text must be non-empty: a line with ' — ' but no text parses as a
# mangled line (reported) rather than a valid index entry
HOOK = re.compile(r'^- \[(?P<t>.*?)\]\((?P<f>[A-Za-z0-9_.\-]+\.md)\)(?: — (?P<h>\S.*))?$')

def name2stem():
    m = {}
    for f in files():
        nm = fm_name(open(f, encoding="utf-8").read())
        if nm and nm != f[:-3]: m.setdefault(nm, f[:-3])
    return m

def resolve(X, stems, n2s):
    if X in stems: return X
    if X.endswith(".md") and X[:-3] in stems: return X[:-3]
    if X in n2s: return n2s[X]
    xn = X.replace("-", "_"); xn = xn[:-3] if xn.endswith(".md") else xn
    c = {S for S in stems if S == xn or S.endswith("_" + xn) or strip_pfx(S) == strip_pfx(xn)}
    return next(iter(c)) if len(c) == 1 else None

CANARY = re.compile(r'^- ([A-Za-z0-9_.\-]+\.md)\s*\|\s*(hot|any)\s*\|\s*(.+?)\s*$')

def canaries():
    """Parse CANARIES.md → [(target_file, tier, fragment)]. Empty if absent."""
    if not os.path.exists("CANARIES.md"): return []
    out = []
    for l in open("CANARIES.md", encoding="utf-8"):
        m = CANARY.match(l.rstrip("\n"))
        if m: out.append((m.group(1), m.group(2), m.group(3)))
    return out

def canary_check(hot="MEMORY.md", archive="ARCHIVE.md"):
    fails = []
    hot_text = open(hot, encoding="utf-8").read() if os.path.exists(hot) else ""
    arc_text = open(archive, encoding="utf-8").read() if os.path.exists(archive) else ""
    def index_line(text, f):
        return next((l for l in text.splitlines()
                     if HOOK.match(l) and HOOK.match(l).group("f") == f), None)
    for target, tier, frag in canaries():
        if target == "MEMORY.md":
            if frag.lower() not in hot_text.lower():
                fails.append((target, f"fragment {frag!r} missing from hot index"))
            continue
        if not os.path.exists(target):
            fails.append((target, "memory file deleted")); continue
        line = index_line(hot_text, target)
        if line is None and tier == "any":
            line = index_line(arc_text, target)
        if line is None:
            where = "hot index" if tier == "hot" else "either index"
            fails.append((target, f"no index line in {where}")); continue
        if frag.lower() not in line.lower():
            fails.append((target, f"fragment {frag!r} lost from its index line"))
    return fails

def check():
    stems = stemset(); n2s = name2stem()
    badname = [f for f in files() if fm_name(open(f, encoding="utf-8").read()) != f[:-3]]
    nodesc = [f for f in files() if not fm_description(f)]
    danglers = {}
    for f in files() + list(SKIP):
        if not os.path.exists(f): continue
        for X in LINK.findall(open(f, encoding="utf-8").read()):
            if X not in stems and X not in danglers:
                danglers[X] = resolve(X, stems, n2s)
    slug = []; over = []; mangled = []; per_ix = {}
    for ix in INDEXES:
        if not os.path.exists(ix): continue
        per_ix[ix] = per = []
        for l in open(ix, encoding="utf-8"):
            ls = l.rstrip("\n")
            if not ls.startswith("- ["): continue
            m = HOOK.match(ls)
            if not m:
                mangled.append(f"{ix}: {ls[:60]}"); continue
            t, f, h = m.group("t"), m.group("f"), m.group("h") or ""
            per.append(f)
            if t == f or (" " not in t and re.match(r'^[a-z0-9][a-z0-9_\-]*$', t)): slug.append(f)
            if ix == "MEMORY.md" and len(h) > OVER: over.append(f)
    disk = set(files())
    hot = per_ix.get("MEMORY.md", []) + per_ix.get("ARCHIVE.md", [])
    cand = per_ix.get("CANDIDATES.md", [])
    coverage = set(hot)
    staged = sorted(f for f in set(cand) if f not in coverage and f in disk)
    dupcounts = {f: (hot + cand).count(f) for f in set(hot + cand) if (hot + cand).count(f) > 1}
    hotbytes = os.path.getsize("MEMORY.md") if os.path.exists("MEMORY.md") else 0
    return dict(badname=badname, danglers=danglers, slug=slug, over=over,
                orphan=sorted(disk - coverage - set(cand)), stale=sorted((set(hot) | set(cand)) - disk),
                dupes=sorted(dupcounts), dupcounts=dupcounts,
                staged=staged, nodesc=nodesc, mangled=mangled,
                canary=canary_check(),
                nfiles=len(disk), nidx=len(hot) + len(cand), hotbytes=hotbytes)

def report(r, d_path):
    bad = sorted(k for k, v in r['danglers'].items() if v is None)
    fixable = sorted(k for k, v in r['danglers'].items() if v is not None)
    def L(ok, label, detail, remedy):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}" + ("" if ok else f"   → {remedy}"))
    print(f"memory-lint — {d_path}  ({r['nfiles']} memories)")
    L(not r['badname'], "name == filename-stem", f"{len(r['badname'])} off" + (f": {_names(r['badname'])}" if r['badname'] else ""), "lint --fix")
    L(not r['danglers'], "[[links]] resolve",
      f"{len(fixable)} auto-fixable, {len(bad)} unresolvable",
      "; ".join(([f"lint --fix ({len(fixable)})"] if fixable else []) + ([f"manual: {bad}"] if bad else [])))
    L(not r['slug'], "no slug titles in index", f"{len(r['slug'])} slug-titled" + (f": {_names(r['slug'])}" if r['slug'] else ""), "memory-reindex / retitle from body")
    det = (f"{len(r['orphan'])} orphan, {len(r['stale'])} stale, {len(r['dupes'])} dup, {len(r['staged'])} staged"
           f"  ({r['nidx']} idx / {r['nfiles']} files)")
    named = []
    if r['orphan']: named.append(f"orphan: {_names(r['orphan'])}")
    if r['stale']: named.append(f"stale: {_names(r['stale'])}")
    if r['dupes']: named.append("dup: " + _counts(r['dupes'], r['dupcounts']))
    det += ("  [" + "; ".join(named) + "]") if named else ""
    L(not (r['orphan'] or r['stale'] or r['dupes']), "index 1:1 with files", det,
      "lint --fix (orphans → CANDIDATES.md; reindex to shelve)")
    if r['staged']:
        print(f"  [note] {len(r['staged'])} staged in CANDIDATES.md, pending reindex: {_names(r['staged'])}")
    L(not r['over'], f"no MEMORY.md hook > {OVER} chars", f"{len(r['over'])} bloated" + (f": {_names(r['over'])}" if r['over'] else ""), "memory-compact")
    L(not r['nodesc'], "frontmatter description present",
      f"{len(r['nodesc'])} empty: {_names(r['nodesc'])}" if r['nodesc'] else "all present",
      "write one (index staging borrows it)")
    L(not r['mangled'], "index lines parse",
      f"{len(r['mangled'])} unparseable: {' | '.join(r['mangled'][:3])}" if r['mangled'] else "all parse",
      "hand-edit (hook text / ' — ' separator) or memory-reindex")
    nc = len(canaries())
    L(not r['canary'], "canaries survive in the index",
      "; ".join(f"{t}: {why}" for t, why in r['canary'])
      or (f"{nc}/{nc} pass" if nc else "none defined"),
      "restore from .backups / re-add the lost detail to the index line")
    L(r['hotbytes'] <= HOTCAP, f"hot index fits the loader (~{HOTCAP//1000}KB)",
      f"{r['hotbytes']/1000:.1f}KB", "memory-reindex (archive cold shelves to ARCHIVE.md — compact can't cut line count)")
    ok = not (r['badname'] or r['danglers'] or r['slug'] or r['orphan'] or r['stale'] or r['dupes'] or r['over'] or r['canary'] or r['nodesc'] or r['mangled']) and r['hotbytes'] <= HOTCAP
    print("RESULT:", "clean ✓" if ok else "violations — see remedies above")
    return ok

def _names(items, cap=3):
    items = sorted(items)
    out = ", ".join(i if len(i) <= 32 else i[:31] + "…" for i in items[:cap])
    return out + (f" (+{len(items)-cap} more)" if len(items) > cap else "")

def _counts(files, counts, cap=3):
    out = ", ".join(f"{f}×{counts[f]}" for f in files[:cap])
    return out + (f" (+{len(files)-cap} more)" if len(files) > cap else "")

def do_fix():
    stems = stemset(); n2s = name2stem()
    pending = {}; nlink = nname = 0
    for f in files() + list(SKIP):
        if not os.path.exists(f): continue
        orig = open(f, encoding="utf-8").read()
        def repl(m):
            nonlocal nlink
            X = m.group(1); r = resolve(X, stems, n2s)
            if r and r != X: nlink += 1; return f"[[{r}]]"
            return m.group(0)
        text = LINK.sub(repl, orig)
        if f not in SKIP and text.startswith("---"):
            end = text.find("\n---", 3); head, rest = text[:end], text[end:]
            nh, n = re.subn(r'(?m)^name:.*$', f"name: {f[:-3]}", head, count=1)
            if n and nh != head: nname += 1; text = nh + rest
        if text != orig: pending[f] = text

    ts = time.strftime("%Y%m%d-%H%M%S")
    r = check()
    nstale = ndupe = 0
    seen = set()
    for ix in INDEXES:
        if not os.path.exists(ix): continue
        out = []
        for l in open(ix, encoding="utf-8"):
            m = HOOK.match(l.rstrip("\n"))
            if m:
                tgt = m.group("f")
                if tgt in r['stale']: nstale += 1; continue
                if tgt in seen: ndupe += 1; continue
                seen.add(tgt)
            out.append(l)
        new = "".join(out)
        if new != open(ix, encoding="utf-8").read(): pending[ix] = new
    nstaged = nskipped = 0
    if r['orphan']:
        base = pending.get("CANDIDATES.md") or (open("CANDIDATES.md", encoding="utf-8").read() if os.path.exists("CANDIDATES.md") else "")
        have = {m.group("f") for l in base.splitlines() if (m := HOOK.match(l))}
        todo = [f for f in r['orphan'] if f not in have]
        nskipped = len(r['orphan']) - len(todo)
        if todo:
            lines = []
            for f in todo:
                title = strip_pfx(f[:-3]).replace("_", " ")
                hook = fm_description(f)[:240] or "(no description — write one)"
                lines.append(f"- [{title}]({f}) — {hook}\n")
            if base and not base.endswith("\n"): base += "\n"
            header = f"## Orphans — auto-staged by lint --fix {ts}\n"
            pending["CANDIDATES.md"] = base + ("\n" if base else "") + header + "".join(lines)
            nstaged = len(lines)

    if not pending:
        print("--fix: no drift — store already normalized\n"); return
    os.makedirs(".backups", exist_ok=True)
    bp = f".backups/lint-fix-{ts}.tar.gz"
    i = 1
    while os.path.exists(bp):  # two fixes in one second (parallel sessions) → don't clobber
        i += 1
        bp = f".backups/lint-fix-{ts}-{i}.tar.gz"
    with tarfile.open(bp, "w:gz") as tar:
        for f in pending:
            if os.path.exists(f): tar.add(f)
    for f, text in pending.items(): open(f, "w", encoding="utf-8").write(text)
    backups = sorted(f for f in os.listdir(".backups") if f.startswith("lint-fix-") and f.endswith(".tar.gz"))
    npruned = max(0, len(backups) - 5)
    for old in backups[:npruned]: os.remove(os.path.join(".backups", old))
    note = f" ({nskipped} already staged)" if nskipped else ""
    pr = f", pruned {npruned} old backup(s)" if npruned else ""
    print(f"--fix: {nname} name: fields, {nlink} links, {nstale} stale + {ndupe} dup index lines dropped, "
          f"{nstaged} orphans staged in CANDIDATES.md{note}, {len(pending)} files touched{pr}  "
          f"(backup: {bp})\n")

def get_brief_summary():
    r = check()
    act = []
    if r['hotbytes'] > HOTCAP:
        act.append(f"hot index {r['hotbytes']/1000:.0f}KB > ~{HOTCAP//1000}KB loader cap (reindex: archive cold shelves)")
    if r['badname']: act.append(f"{len(r['badname'])} name:≠stem: {_names(r['badname'])} (lint --fix)")
    if r['orphan']: act.append(f"{len(r['orphan'])} orphan: {_names(r['orphan'])} (lint --fix)")
    if r['stale']: act.append(f"{len(r['stale'])} stale: {_names(r['stale'])} (lint --fix)")
    if r['dupes']: act.append(f"{len(r['dupes'])} dup: {_counts(r['dupes'], r['dupcounts'])} (lint --fix)")
    if r['nodesc']: act.append(f"{len(r['nodesc'])} no description: {_names(r['nodesc'])}")
    if r['mangled']: act.append(f"{len(r['mangled'])} unparseable index line(s) (hand-edit or reindex)")
    if r['slug']: act.append(f"{len(r['slug'])} slug-titles: {_names(r['slug'])} (reindex)")
    if r['over']: act.append(f"{len(r['over'])} bloated: {_names(r['over'])} (compact)")
    if r['canary']: act.append(f"{len(r['canary'])} canaries FAILING (index lost load-bearing detail)")
    fixable = [k for k, v in r['danglers'].items() if v is not None]
    bad = [k for k, v in r['danglers'].items() if v is None]
    if fixable: act.append(f"{len(fixable)} fixable links (lint --fix)")
    notes = []
    if bad: notes.append(f"{len(bad)} unresolvable links pending manual triage: {_names(bad)}")
    if r['staged']: notes.append(f"{len(r['staged'])} staged in CANDIDATES.md — pending reindex")
    note = ("; " + "; ".join(notes)) if notes else ""
    if act: return f"memory-lint: needs attention — {'; '.join(act)}{note}  ({r['nfiles']} memories)"
    return f"memory-lint: clean ✓  ({r['nfiles']} memories{note})"

def hook_target(ws_paths):
    """Hook-mode memory-dir resolution: only accept a REAL store (MEMORY.md
    present), walking up parent directories if the workspace has no own store."""
    for ws in ws_paths:
        if os.path.isfile(os.path.join(ws, "MEMORY.md")):
            return os.path.abspath(ws)
        cand = _resolve_from_dir(ws)
        if cand:
            return cand
    return None

def handle_agy_hook_pre_invocation():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    target_dir = hook_target(payload.get("workspacePaths", []))
    if not target_dir or not os.path.isdir(target_dir):
        print(json.dumps({}))
        sys.exit(0)
    # Only inject once per conversation (tracked via sentinel in artifactDirectoryPath)
    art_dir = payload.get("artifactDirectoryPath", "")
    sentinel = os.path.join(art_dir, ".memory_injected") if art_dir else None
    if sentinel and os.path.exists(sentinel):
        print(json.dumps({}))
        sys.exit(0)
    os.chdir(target_dir)
    summary = get_brief_summary()
    mem_path = os.path.join(target_dir, "MEMORY.md")
    mem_text = ""
    if os.path.isfile(mem_path):
        with open(mem_path, encoding="utf-8", errors="replace") as fh:
            mem_text = fh.read(HOTCAP)
    msg = (
        f"[Memory Store: {target_dir}]\n"
        f"{summary}\n\n"
        f"# MEMORY.md (Hot Index)\n{mem_text}"
    )
    if sentinel:
        try:
            os.makedirs(art_dir, exist_ok=True)
            with open(sentinel, "w", encoding="utf-8") as fh:
                fh.write(f"{target_dir}\n")
        except OSError:
            pass
    print(json.dumps({"injectSteps": [{"ephemeralMessage": msg}]}))
    sys.exit(0)

def handle_agy_hook_post_tool():
    """Log reads of memory files to USAGE.log (supports Claude Read and Antigravity view_file)."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = (
        payload.get("tool_input", {}).get("file_path")
        or payload.get("toolCall", {}).get("args", {}).get("AbsolutePath")
        or ""
    )
    if not path:
        ts_path = payload.get("transcriptPath", "")
        if ts_path and os.path.isfile(ts_path):
            try:
                with open(ts_path, "rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    sz = fh.tell()
                    fh.seek(max(0, sz - 16384))
                    lines = fh.read().decode("utf-8", errors="replace").splitlines()
                for raw in reversed(lines[-15:]):
                    try:
                        step = json.loads(raw)
                    except Exception:
                        continue
                    for tc in step.get("tool_calls") or []:
                        p = (tc.get("args") or tc.get("arguments") or {}).get("AbsolutePath", "")
                        if p:
                            path = p
                            break
                    if path:
                        break
            except OSError:
                pass
    m = re.match(r"^(.*/(?:\.claude/projects/[^/]+/memory|\.agents/memory))/([A-Za-z0-9_.\-]+\.md)$", path)
    if m and m.group(2) not in SKIP:
        try:
            with open(os.path.join(m.group(1), "USAGE.log"), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\tread\t{m.group(2)}\n")
        except OSError:
            pass
    print(json.dumps({}))
    sys.exit(0)

def handle_agy_hook_stop():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    target_dir = hook_target(payload.get("workspacePaths", []))
    if target_dir and os.path.isdir(target_dir):
        os.chdir(target_dir)
        log_path = os.path.expanduser("~/.claude/memory-lint.log")
        try:
            if os.path.isfile(log_path) and os.path.getsize(log_path) > 1048576:
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    tail = fh.readlines()[-4000:]
                with open(log_path + ".tmp", "w", encoding="utf-8") as fh:
                    fh.writelines(tail)
                os.replace(log_path + ".tmp", log_path)
            with open(log_path, "a", encoding="utf-8") as log_fh:
                log_fh.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} (agy) ===\n")
                with contextlib.redirect_stdout(log_fh), contextlib.redirect_stderr(log_fh):
                    do_fix()
                    report(check(), target_dir)
        except Exception:
            pass
    print(json.dumps({}))
    sys.exit(0)

def main():
    if "--hook-pre-invocation" in sys.argv:
        handle_agy_hook_pre_invocation()
    if "--hook-post-tool" in sys.argv:
        handle_agy_hook_post_tool()
    if "--hook-stop" in sys.argv:
        handle_agy_hook_stop()

    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = pos[0] if pos else None
    mem_dir = find_memory_dir(target)
    if not mem_dir or not os.path.isdir(mem_dir):
        if "--brief" not in sys.argv:
            print(f"memory-lint: no memory store found — skipping")
        sys.exit(0)
    os.chdir(mem_dir)

    if "--canary-check" in sys.argv:
        rest = sys.argv[sys.argv.index("--canary-check") + 1:]
        hot = rest[0] if rest else "MEMORY.md"
        arc = rest[1] if len(rest) > 1 else "ARCHIVE.md"
        fails = canary_check(hot, arc)
        n = len(canaries())
        if fails:
            for t, why in fails: print(f"  CANARY FAIL {t}: {why}")
            print(f"canary-check: {len(fails)}/{n} FAILING against {hot} — do not replace")
        else:
            print(f"canary-check: {n}/{n} pass against {hot}")
        sys.exit(1 if fails else 0)

    if "--brief" in sys.argv:
        print(get_brief_summary())
        sys.exit(0)

    if "--fix" in sys.argv:
        do_fix()

    sys.exit(0 if report(check(), mem_dir) else 1)

if __name__ == "__main__":
    main()
