#!/usr/bin/env python3
"""memory-lint — assert the memory store's invariants.

Usage:  lint.py [<memory_dir>] [--fix]
  (no dir) → uses cwd as the memory dir.
  --fix    → back up, then apply the DETERMINISTIC repairs only:
             name: → filename-stem, and rewrite [[links]] to stems
             (.md-strip + unique fuzzy match). Coverage, over-length, and
             slug-titles are NOT auto-fixed — they route to reindex/compact.

Exit 0 if every invariant passes, 1 if any fails (hook/CI friendly).
"""
import os, re, sys, time, tarfile

FIX = "--fix" in sys.argv
pos = [a for a in sys.argv[1:] if not a.startswith("--")]
D = pos[0] if pos else os.getcwd()
if not os.path.isdir(D):
    if "--brief" not in sys.argv: print(f"memory-lint: no memory store at {D} — skipping")
    sys.exit(0)
os.chdir(D)

SKIP = {"MEMORY.md", "CANDIDATES.md"}
OVER = 300  # hook-text length ceiling (== compact's giant allowance)

def files():   return [f for f in os.listdir(".") if f.endswith(".md") and f not in SKIP]
def stemset(): return set(f[:-3] for f in files())

def fm_name(text):
    if not text.startswith("---"): return None
    end = text.find("\n---", 3); fm = text[:end] if end > 0 else text
    m = re.search(r'^name:\s*(.+)$', fm, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None

def strip_pfx(s): return re.sub(r'^(project|feedback|reference|plan)_', '', s)
LINK = re.compile(r'\[\[([A-Za-z0-9_.\-]+)\]\]')
HOOK = re.compile(r'^- \[(?P<t>.*?)\]\((?P<f>[A-Za-z0-9_.\-]+\.md)\)(?: — (?P<h>.*))?$')

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

def check():
    stems = stemset(); n2s = name2stem()
    badname = [f for f in files() if fm_name(open(f, encoding="utf-8").read()) != f[:-3]]
    danglers = {}
    for f in files() + ["MEMORY.md", "CANDIDATES.md"]:
        if not os.path.exists(f): continue
        for X in LINK.findall(open(f, encoding="utf-8").read()):
            if X not in stems and X not in danglers:
                danglers[X] = resolve(X, stems, n2s)   # fuzzy target, or None
    slug = []; over = []; idx = []
    for l in open("MEMORY.md", encoding="utf-8"):
        if not l.startswith("- ["): continue
        m = HOOK.match(l.rstrip("\n"))
        if not m: continue
        t, f, h = m.group("t"), m.group("f"), m.group("h") or ""
        idx.append(f)
        if t == f or (" " not in t and re.match(r'^[a-z0-9][a-z0-9_\-]*$', t)): slug.append(f)
        if len(h) > OVER: over.append(f)
    disk = set(files())
    return dict(badname=badname, danglers=danglers, slug=slug, over=over,
                orphan=sorted(disk - set(idx)), stale=sorted(set(idx) - disk),
                dupes=sorted({f for f in idx if idx.count(f) > 1}),
                nfiles=len(disk), nidx=len(idx))

def report(r):
    bad = sorted(k for k, v in r['danglers'].items() if v is None)
    fixable = sorted(k for k, v in r['danglers'].items() if v is not None)
    def L(ok, label, detail, remedy):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}" + ("" if ok else f"   → {remedy}"))
    print(f"memory-lint — {D}  ({r['nfiles']} memories)")
    L(not r['badname'], "name == filename-stem", f"{len(r['badname'])} off", "lint --fix")
    L(not r['danglers'], "[[links]] resolve",
      f"{len(fixable)} auto-fixable, {len(bad)} unresolvable",
      "; ".join(([f"lint --fix ({len(fixable)})"] if fixable else []) + ([f"manual: {bad}"] if bad else [])))
    L(not r['slug'], "no slug titles in index", f"{len(r['slug'])} slug-titled", "memory-reindex / retitle from body")
    L(not (r['orphan'] or r['stale'] or r['dupes']), "index 1:1 with files",
      f"{len(r['orphan'])} orphan, {len(r['stale'])} stale, {len(r['dupes'])} dup  ({r['nidx']} idx / {r['nfiles']} files)", "memory-reindex")
    L(not r['over'], f"no hook text > {OVER} chars", f"{len(r['over'])} bloated", "memory-compact")
    ok = not (r['badname'] or r['danglers'] or r['slug'] or r['orphan'] or r['stale'] or r['dupes'] or r['over'])
    print("RESULT:", "clean ✓" if ok else "violations — see remedies above")
    return ok

def do_fix():
    stems = stemset(); n2s = name2stem()
    pending = {}; nlink = nname = 0
    for f in files() + ["MEMORY.md", "CANDIDATES.md"]:
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
    if not pending:
        print("--fix: no name/link drift — store already normalized\n"); return
    os.makedirs(".backups", exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    with tarfile.open(f".backups/lint-fix-{ts}.tar.gz", "w:gz") as tar:
        for f in pending: tar.add(f)
    for f, text in pending.items(): open(f, "w", encoding="utf-8").write(text)
    print(f"--fix: normalized {nname} name: fields, rewrote {nlink} links in {len(pending)} files  (backup: .backups/lint-fix-{ts}.tar.gz)\n")

def brief():
    """One-line health summary for SessionStart injection — surfaces only
    skill-actionable issues; known-unresolvable danglers are a quiet note."""
    r = check()
    act = []
    if r['orphan'] or r['stale'] or r['dupes']:
        act.append(f"{len(r['orphan']) + len(r['stale']) + len(r['dupes'])} coverage (reindex)")
    if r['slug']: act.append(f"{len(r['slug'])} slug-titles (reindex)")
    if r['over']: act.append(f"{len(r['over'])} bloated (compact)")
    fixable = [k for k, v in r['danglers'].items() if v is not None]
    bad = [k for k, v in r['danglers'].items() if v is None]
    if fixable: act.append(f"{len(fixable)} fixable links (lint --fix)")
    note = f"; {len(bad)} unresolvable links pending manual triage" if bad else ""
    if act: print(f"memory-lint: needs attention — {'; '.join(act)}{note}  ({r['nfiles']} memories)")
    else:   print(f"memory-lint: clean ✓  ({r['nfiles']} memories{note})")

if "--brief" in sys.argv:
    brief(); sys.exit(0)
if FIX: do_fix()
sys.exit(0 if report(check()) else 1)
