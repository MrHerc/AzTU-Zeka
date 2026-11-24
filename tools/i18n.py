"""Zəka i18n toolchain (stdlib only). The Azerbaijani source text is the translation key.

  python tools/i18n.py lint [files…]     report UI text that is not wrapped in t() (JS) or S/E/T3/S_ (Python)
  python tools/i18n.py extract           write i18n/source/{ui,server,content}.json and i18n/todo/<chunk>.json (untranslated)
  python tools/i18n.py build             merge i18n/<lang>/*.json into frontend/locales/<lang>.json and backend/zeka/core/locales/<lang>.json
  python tools/i18n.py stats             coverage per language
  python tools/i18n.py rename MAP.json [--apply]   rewrite Azerbaijani keys and move their translations (dry run by default)

Translation files: i18n/en/*.json and i18n/ru/*.json, each a flat object {"<az source>": "<translation>"}.
A value may be an object of plural forms when the source contains {n}: {"one": "...", "other": "..."} (en) or
{"one": "...", "few": "...", "many": "..."} (ru)."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "frontend" / "js"
PY_DIR = ROOT / "backend" / "zeka"
CONTENT = ROOT / "content"
I18N = ROOT / "i18n"
LANGS = ("en", "ru")
AZ_LETTERS = re.compile(r"[əƏğĞıİöÖüÜşŞçÇ]")
WORDS = re.compile(r"[A-Za-zƏəĞğİıÖöÜüŞşÇç]{2,}")
PH = re.compile(r"\{(\w+)\}")


BRAND = {"ctrl", "esc", "enter", "tab", "shift", "aztu", "zəka", "pdf", "csv", "nps", "qr", "ai", "llm", "sso", "lms", "id", "ok", "kb", "mb", "az", "en", "ru",
         "google", "maps", "openstreetmap", "facebook", "instagram", "linkedin", "youtube", "wikipedia", "safarov", "industries", "by", "the", "wur", "qs",
         "gpa", "ects", "akts", "csat", "sla", "api", "docx", "png", "jpg", "jpeg", "pptx", "md", "txt", "url", "http", "https", "www", "edu", "gov", "news",
         "zoom", "moodle", "python", "matlab", "geogebra", "github", "email", "e-mail"}


def _technical(s: str) -> bool:
    """True for tokens that need no translation: paths, units, brand names, numbers, punctuation."""
    if re.fullmatch(r"[\w\-./#:?&=%+]+", s) and not AZ_LETTERS.search(s) and " " not in s and not re.fullmatch(r"[A-ZƏÖÜŞÇĞİ][a-zəıöüşçğ]{2,}", s):
        return True
    words = [w.lower() for w in WORDS.findall(s)]
    return bool(words) and all(w in BRAND or re.fullmatch(r"[a-z]{1,3}\d*|px|vh|vw|rem|em", w) for w in words)


# ============================================================== JS tokenizer
REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "instanceof", "yield", "await", None}


class Tok:
    __slots__ = ("kind", "val", "start", "end", "parts", "exprs", "line")

    def __init__(self, kind, val, start, end, line, parts=None, exprs=None):
        self.kind, self.val, self.start, self.end, self.line, self.parts, self.exprs = kind, val, start, end, line, parts, exprs


def _read_string(src, i):
    q = src[i]
    j = i + 1
    out = []
    while j < len(src):
        c = src[j]
        if c == "\\":
            nxt = src[j + 1] if j + 1 < len(src) else ""
            out.append({"n": "\n", "t": "\t", "r": "\r", "u": "\\u"}.get(nxt, nxt))
            j += 2
            continue
        if c == q:
            return "".join(out), j + 1
        if c == "\n":
            break
        out.append(c)
        j += 1
    return "".join(out), j


def _read_template(src, i):
    """Return (static parts, expression sources, end index)."""
    j = i + 1
    parts, exprs, cur = [], [], []
    while j < len(src):
        c = src[j]
        if c == "\\":
            cur.append(src[j:j + 2])
            j += 2
            continue
        if c == "`":
            parts.append("".join(cur))
            return parts, exprs, j + 1
        if c == "$" and src[j + 1:j + 2] == "{":
            parts.append("".join(cur))
            cur = []
            depth, k = 1, j + 2
            while k < len(src) and depth:
                ch = src[k]
                if ch in "\"'":
                    _, k = _read_string(src, k)
                    continue
                if ch == "`":
                    _, _, k = _read_template(src, k)
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            exprs.append((src[j + 2:k], j + 2))
            j = k + 1
            continue
        cur.append(c)
        j += 1
    parts.append("".join(cur))
    return parts, exprs, j


def tokenize(src, base=0, line_of=None):
    toks, i, n, prev = [], 0, len(src), None
    line_of = line_of or (lambda pos: 0)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            v, j = _read_string(src, i)
            toks.append(Tok("str", v, base + i, base + j, line_of(base + i)))
            prev, i = "str", j
            continue
        if c == "`":
            parts, exprs, j = _read_template(src, i)
            toks.append(Tok("tpl", None, base + i, base + j, line_of(base + i), parts, [(e, base + off) for e, off in exprs]))
            prev, i = "tpl", j
            continue
        if c == "/" and (prev in REGEX_PREV or (isinstance(prev, str) and len(prev) == 1 and prev in REGEX_PREV)):
            j, in_cls = i + 1, False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_cls = True
                elif ch == "]":
                    in_cls = False
                elif ch == "/" and not in_cls:
                    break
                elif ch == "\n":
                    break
                j += 1
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            prev, i = "regex", j
            continue
        if c.isalpha() or c in "_$":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word = src[i:j]
            toks.append(Tok("id", word, base + i, base + j, line_of(base + i)))
            prev, i = word, j
            continue
        if c.isdigit():
            j = i
            while j < n and (src[j].isalnum() or src[j] in "._"):
                j += 1
            prev, i = "num", j
            continue
        toks.append(Tok("p", c, base + i, base + i + 1, line_of(base + i)))
        prev, i = c, i + 1
    return toks


def _is_t_arg(toks, k):
    """True when toks[k] is the first argument of a bare t(…) call."""
    return (k >= 2 and toks[k - 1].kind == "p" and toks[k - 1].val == "(" and toks[k - 2].kind == "id" and toks[k - 2].val == "t"
            and not (k >= 3 and toks[k - 3].kind == "p" and toks[k - 3].val == "."))


def js_scan(path: Path):
    """Yield ('key', text, line) for t() source strings and ('raw', text, line, why) for untranslated UI text."""
    src = path.read_text(encoding="utf-8")
    nl = [m.start() for m in re.finditer("\n", src)]

    def line_of(pos):
        lo, hi = 0, len(nl)
        while lo < hi:
            mid = (lo + hi) // 2
            if nl[mid] < pos:
                lo = mid + 1
            else:
                hi = mid
        return lo + 1

    out = []

    def walk(code, base):
        toks = tokenize(code, base, line_of)
        for k, tk in enumerate(toks):
            is_t_arg = _is_t_arg(toks, k)
            if tk.kind == "str":
                if is_t_arg:
                    out.append(("key", tk.val, tk.line))
                elif len(tk.val) <= 2 or re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9 .,\-]+", tk.val) or _technical(tk.val):
                    continue
                elif AZ_LETTERS.search(tk.val):
                    out.append(("raw", tk.val, tk.line, "string literal with Azerbaijani text"))
                elif k >= 2 and toks[k - 1].kind == "p" and toks[k - 1].val == ":" and toks[k - 2].kind == "id" and \
                        toks[k - 2].val in ("label", "title", "text", "placeholder", "sub", "hint", "help", "message", "msg", "desc", "summary") and WORDS.search(tk.val) and " " in tk.val:
                    out.append(("raw", tk.val, tk.line, f"'{toks[k - 2].val}:' value not wrapped in t()"))
            elif tk.kind == "tpl":
                if is_t_arg:
                    if tk.exprs:
                        out.append(("raw", "".join(tk.parts), tk.line, "t() with a template literal containing ${} — use t(\"… {x} …\", {x})"))
                    else:
                        out.append(("key", tk.parts[0], tk.line))
                else:
                    is_html = any("<" in p for p in tk.parts)
                    for part in tk.parts:
                        if is_html:
                            for piece in re.split(r"<[^<>]*>", part):
                                s = piece.strip()
                                if not s or re.search(r"[<>=\";]", s) or _technical(s):
                                    continue
                                if AZ_LETTERS.search(s) or WORDS.search(s):
                                    out.append(("raw", s[:120], tk.line, "visible text in template"))
                            for attr, val in re.findall(r"\b(placeholder|title|aria-label|alt|label)=\"([^\"$]*)\"", part):
                                if WORDS.search(val) and not _technical(val):
                                    out.append(("raw", val[:120], tk.line, f"{attr}= attribute"))
                        elif AZ_LETTERS.search(part):
                            out.append(("raw", part.strip()[:120], tk.line, "Azerbaijani text in template literal"))
                for expr, off in tk.exprs:
                    walk(expr, off)
        return toks

    walk(src, 0)
    return out


# ============================================================== Python scanning
MARK_FUNCS = {"S", "S_", "E", "T3", "tr3", "J3", "s", "tr"}


def py_scan(path: Path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    keys, raws = [], []
    marked = set()
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_nodes.add(id(first.value))
    for node, fn, target in _py_targets(tree):
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            keys.append((target.value, node.lineno))
            marked.add(id(target))
        elif isinstance(target, ast.JoinedStr):
            raws.append(("f-string in " + fn, (ast.get_source_segment(src, target) or "")[:120], node.lineno))
            marked.add(id(target))
    implicit = _implicit_file(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and id(node) not in marked:
            lits = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if AZ_LETTERS.search(lits):
                seg = ast.get_source_segment(src, node) or lits
                raws.append(("f-string with Azerbaijani text (use T3/E with params)", seg[:120], node.lineno))
            for v in node.values:
                marked.add(id(v))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in marked and id(node) not in doc_nodes and implicit:
            if _implicit_text(node.value):
                keys.append((node.value, getattr(node, "lineno", 0)))  # implicit: translated by exact match in responses
    return keys, raws


def _py_targets(tree):
    """Yield (call, function name, argument node) for every argument the extractor reads as a translation key."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            args = node.args
            if fn in MARK_FUNCS and args:
                yield node, fn, args[0]
            elif fn == "HTTPError" and len(args) >= 2:
                yield node, fn, args[1]
            elif fn in ("ValueError", "RuntimeError", "TableError") and args:
                yield node, fn, args[0]


def _implicit_file(path: Path) -> bool:
    return path.name.startswith("r_") or path.name in ("common.py", "docs.py", "support.py", "tutor.py", "web.py")


def _implicit_text(text: str) -> bool:
    return bool(AZ_LETTERS.search(text)) and len(text) < 400 and text.count("\n") < 4 \
        and not re.match(r"\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|WITH)\b", text, re.I) \
        and "\\b" not in text and "(?" not in text and not text.startswith(("/", "<"))


# ============================================================== content extraction
SKIP_KEYS = {"code", "key", "icon", "color", "tone", "url", "link", "href", "prefix", "type", "kind", "role", "username", "email", "phone", "password",
             "start", "end", "date", "time", "id", "file", "filename", "audience", "status", "qtype", "category", "track", "teacher", "course", "group",
             "patronymic", "full_name", "student_no", "site", "short", "platform", "en", "answer_index", "accept", "roles", "keys",
             "name_en", "semester_en", "level_en", "document_en", "semester_dates", "cover", "event", "tools", "areas_keys", "dept", "material",
             "step_roles", "effect"}


def content_strings(reads: dict | None = None):
    """Translatable content strings; `reads`, when given, counts how many times each one is read."""
    out: dict = {}

    def add(s, where):
        if isinstance(s, str) and WORDS.search(s) and not re.match(r"https?://|/[a-z]", s):
            out.setdefault(s, where)
            if reads is not None:
                reads[s] = reads.get(s, 0) + 1

    def walk(v, path, where, skip_subtrees=()):
        if any(path.startswith(p) for p in skip_subtrees):
            return
        if isinstance(v, dict):
            for k, x in v.items():
                if k in SKIP_KEYS:
                    continue
                if k == "name" and path.endswith("fields[]"):
                    continue
                walk(x, f"{path}.{k}" if path else k, where, skip_subtrees)
        elif isinstance(v, list):
            for x in v:
                walk(x, path + "[]", where, skip_subtrees)
        else:
            add(v, where)

    seed = json.loads((CONTENT / "seed.json").read_text(encoding="utf-8"))
    for u in seed.get("users", []):
        for k in ("title", "funding", "form"):
            add(u.get(k), "seed.users")
        if u.get("username") in ("rektorluq", "admin"):      # system personas, not people
            add(u.get("full_name"), "seed.users.persona")
    for co in seed.get("courses", []):
        add(co.get("name"), "seed.courses")
        add(co.get("description"), "seed.courses")
        for sch in co.get("schedule", []):
            if len(sch) > 3:
                add(sch[3], "seed.courses.schedule")
            if len(sch) > 4:
                for part in str(sch[4]).split(", "):
                    if not re.fullmatch(r"[\d\s\w-]{0,6}\d+\w?", part):
                        add(part, "seed.rooms")
    for sem in seed.get("past_semesters", []):
        add(sem.get("name"), "seed.past_semesters")
        for row in sem.get("courses", []):
            if row:
                add(row[0], "seed.past_semesters")
    walk({k: seed[k] for k in ("university", "faculty", "specialty", "service_categories", "request_types") if k in seed}, "", "seed")
    grading = (seed.get("tenant") or {}).get("grading") or {}
    for comp in grading.get("components", []) + [grading.get("exam") or {}]:      # the grade table's headers (L7)
        add(comp.get("name"), "seed.tenant.grading")
    academy = json.loads((CONTENT / "academy.json").read_text(encoding="utf-8"))
    walk(academy, "", "academy")
    for tr_ in academy.get("tracks", []):
        add(tr_.get("audience"), "academy.audience")
    tools = json.loads((CONTENT / "tools.json").read_text(encoding="utf-8"))
    for v in tools.get("areas", {}).values():
        add(v, "tools.areas")
    for tl in tools.get("tools", []):
        walk({k: v for k, v in tl.items() if k not in ("name", "areas")}, "", "tools")
        for k in ("name", "type", "platform"):
            add(tl.get(k), f"tools.{k} (keep brand names)")
    news = json.loads((CONTENT / "news.json").read_text(encoding="utf-8"))
    for v in news.get("kinds", {}).values():
        add(v, "news.kinds")
    walk(news.get("news", []), "", "news")
    for n in news.get("news", []):
        loc = (n.get("event") or {}).get("location")
        if loc:
            add(loc, "news.event.location")
            for part in loc.split(", "):
                add(part, "news.event.location")
    walk(json.loads((CONTENT / "guide.json").read_text(encoding="utf-8")), "", "guide")
    return out


# ============================================================== commands
def lint(files):
    files = [Path(f) for f in files] or sorted(JS_DIR.glob("*.js")) + sorted(PY_DIR.rglob("*.py"))
    files = [f for f in files if f.name not in ("i18n.py", "i18n.js")]
    total = 0
    for f in files:
        f = f if f.is_absolute() else ROOT / f
        if f.suffix == ".js":
            items = [x for x in js_scan(f) if x[0] == "raw"]
            for _, text, line, why in items:
                print(f"{f.name}:{line}: {why}: {text}")
        else:
            _, raws = py_scan(f)
            items = raws
            for why, seg, line in raws:
                print(f"{f.name}:{line}: {why}: {seg}")
        total += len(items)
    print(f"LINT: {total} finding(s) in {len(files)} file(s)")
    return total


def gather():
    ui, server = {}, {}
    for f in sorted(JS_DIR.glob("*.js")):
        for item in js_scan(f):
            if item[0] == "key" and item[1].strip():
                ui.setdefault(item[1], f"{f.name}:{item[2]}")
    for f in sorted(PY_DIR.rglob("*.py")):
        if f.name in ("i18n.py",):
            continue
        keys, _ = py_scan(f)
        for v, line in keys:
            if v.strip():
                server.setdefault(v, f"{f.name}:{line}")
    content = content_strings()
    return ui, server, content


def load_tr(lang):
    d = {}
    for f in sorted((I18N / lang).glob("*.json")):
        try:
            d.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if v not in (None, "")})
        except ValueError as ex:
            print(f"!! {f}: invalid JSON ({ex})")
    return d


def extract(chunk_chars=14000):
    ui, server, content = gather()
    (I18N / "source").mkdir(parents=True, exist_ok=True)
    for name, d in (("ui", ui), ("server", server), ("content", content)):
        (I18N / "source" / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    have = {lg: load_tr(lg) for lg in LANGS}
    todo_dir = I18N / "todo"
    todo_dir.mkdir(parents=True, exist_ok=True)
    for old in todo_dir.glob("*.json"):
        old.unlink()
    seen, chunks = set(), []
    taken = {p.stem for lg in LANGS for p in (I18N / lg).glob("*.json")}

    def free(name, idx):
        while f"{name}-{idx:02d}" in taken:
            idx += 1
        taken.add(f"{name}-{idx:02d}")
        return f"{name}-{idx:02d}", idx

    for name, d in (("ui", ui), ("server", server), ("content", content)):
        cur, size, idx = {}, 0, 1
        for k, where in d.items():
            if k in seen or all(k in have[lg] for lg in LANGS):
                continue
            seen.add(k)
            cur[k] = where
            size += len(k)
            if size >= chunk_chars:
                cname, idx = free(name, idx)
                chunks.append((cname, cur))
                cur, size, idx = {}, 0, idx + 1
        if cur:
            cname, idx = free(name, idx)
            chunks.append((cname, cur))
    for cname, d in chunks:
        (todo_dir / f"{cname}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"source: ui={len(ui)} server={len(server)} content={len(content)}; untranslated chunks: {len(chunks)} -> {todo_dir}")
    for cname, d in chunks:
        print(f"  {cname}: {len(d)} strings, {sum(len(k) for k in d)} chars")


def _check(src, val, lang):
    want = set(PH.findall(src))
    vals = list(val.values()) if isinstance(val, dict) else [val]
    probs = []
    for v in vals:
        if not isinstance(v, str):
            probs.append("non-string value")
            continue
        got = set(PH.findall(v))
        if got != want:
            probs.append(f"placeholders {sorted(got)} != {sorted(want)}")
        if src.count("**") != v.count("**"):
            probs.append("bold markers (**) differ")
    if isinstance(val, dict) and "{n}" not in src:
        probs.append("plural forms used but source has no {n}")
    return probs


def build():
    ui, server, content = gather()
    for lg in LANGS:
        tr = load_tr(lg)
        bad = 0
        for k, v in tr.items():
            for p in _check(k, v, lg):
                bad += 1
                if bad <= 25:
                    print(f"[{lg}] {p}: {k[:70]!r}")
        static = {k: tr[k] for k in ui if k in tr}
        app = {k: tr[k] for k in list(server) + list(content) if k in tr}
        for k in ui:            # UI strings may also appear in server responses (statuses, labels)
            if k in tr and k not in app:
                app[k] = tr[k]
        (ROOT / "frontend" / "locales").mkdir(parents=True, exist_ok=True)
        (ROOT / "backend" / "zeka" / "core" / "locales").mkdir(parents=True, exist_ok=True)
        (ROOT / "frontend" / "locales" / f"{lg}.json").write_text(json.dumps(static, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (ROOT / "backend" / "zeka" / "core" / "locales" / f"{lg}.json").write_text(json.dumps(app, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        def cov(d, tr=tr):
            return f"{sum(1 for k in d if k in tr)}/{len(d)}"

        print(f"{lg}: ui {cov(ui)}  server {cov(server)}  content {cov(content)}  problems: {bad}")


def stats():
    ui, server, content = gather()
    for lg in LANGS:
        tr = load_tr(lg)
        for name, d in (("ui", ui), ("server", server), ("content", content)):
            miss = [k for k in d if k not in tr]
            print(f"{lg} {name}: {len(d) - len(miss)}/{len(d)}" + (f"  e.g. {miss[:3]}" if miss else ""))


# ============================================================== rename (Task 20)
JSON_STR = re.compile(r'"(?:[^"\\\n]|\\.)*"')
CONTENT_READ = ("seed.json", "academy.json", "tools.json", "news.json", "guide.json")    # the files content_strings() reads


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _py_lit(text: str, quote: str) -> str:
    body = text.replace("\\", "\\\\").replace(quote, "\\" + quote).replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return quote + body + quote


def _py_replacement(seg: str, new: str) -> str:
    """Source for `new` in the shape of the literal `seg`: its quote, and as many pieces as its implicit concatenation."""
    import io
    import tokenize as tk
    full = "(" + seg + ")"
    toks = [t for t in tk.generate_tokens(io.StringIO(full).readline) if t.type == tk.STRING]
    quote = "'" if seg.lstrip("rRuU").startswith("'") else '"'
    if len(toks) < 2:
        return _py_lit(new, quote)
    lines = full.splitlines(keepends=True)

    def at(rc):
        return sum(len(x) for x in lines[:rc[0] - 1]) + rc[1]
    vals = [ast.literal_eval(t.string) for t in toks]
    old_len, done = sum(len(v) for v in vals) or 1, 0
    cuts: list[int] = []
    for v in vals[:-1]:                                  # cut the new text after a space near each old boundary
        done += len(v)
        sp = new.find(" ", round(done / old_len * len(new)))
        cuts.append(max(len(new) if sp < 0 else sp + 1, cuts[-1] if cuts else 0))
    parts = [new[a:b] for a, b in zip([0, *cuts], [*cuts, len(new)], strict=True)]
    out = []
    for i, part in enumerate(parts):
        out.append(_py_lit(part, quote))
        if i < len(parts) - 1:
            out.append(full[at(toks[i].end):at(toks[i + 1].start)])
    return "".join(out)


def _py_literals(path: Path, src: str, test: bool):
    """(start, end, value, context) of every str constant outside f-strings, as character offsets. Context: 'key' (an
    argument the extractor reads, or an implicit key), 'test', or 'other' (an unrelated literal: a compared value, a
    dict key, a subscript, a docstring, or any literal the extractor does not read)."""
    tree = ast.parse(src)
    raw = src.encode("utf-8")
    starts = [0] + [m.end() for m in re.finditer(b"\n", raw)]

    def char(line, col):
        b = starts[line - 1] + col
        return len(raw[:b].decode("utf-8"))
    inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}     # an f-string's own text
    keys = {id(t) for _, _, t in _py_targets(tree)}
    other: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare):
            for x in [n.left, *n.comparators]:
                other.update(id(y) for y in [x, *getattr(x, "elts", [])])
        elif isinstance(n, ast.Dict):
            other.update(id(k) for k in n.keys if k is not None)
        elif isinstance(n, ast.Subscript):
            other.add(id(n.slice))
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                other.add(id(first.value))
    implicit = _implicit_file(path)
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inner and n.end_lineno is not None:
            ctx = ("test" if test else "key" if id(n) in keys else "other" if id(n) in other
                   else "key" if implicit and _implicit_text(n.value) else "other")
            out.append((char(n.lineno, n.col_offset), char(n.end_lineno, n.end_col_offset or 0), n.value, ctx))
    return out


def _js_literals(src: str, test: bool):
    out = []

    def walk(code, base):
        toks = tokenize(code, base)
        for k, tk in enumerate(toks):
            ctx = "test" if test else "key" if _is_t_arg(toks, k) else "other"
            if tk.kind == "str":
                out.append((tk.start, tk.end, tk.val, ctx))
            elif tk.kind == "tpl":
                if not tk.exprs:
                    out.append((tk.start, tk.end, tk.parts[0], ctx))
                for expr, off in tk.exprs:
                    walk(expr, off)
    walk(src, 0)
    return out


def _json_literals(src: str, read: bool):
    out = []
    for m in JSON_STR.finditer(src):
        is_key = src[m.end():m.end() + 40].lstrip().startswith(":")
        out.append((m.start(), m.end(), json.loads(m.group()), "other" if is_key or not read else "content"))
    return out


def _literal(kind: str, seg: str, new: str) -> str:
    if kind == "py":
        return _py_replacement(seg, new)
    if kind == "json":
        return json.dumps(new, ensure_ascii=False)
    q = seg[0]
    body = new.replace("\\", "\\\\").replace(q, "\\" + q).replace("\n", "\\n")
    return q + (body.replace("${", "\\${") if q == "`" else body) + q


def _scan_files():
    """Every file the rename reads: (path, kind, text, literals); kind 'other' files are only searched for notes."""
    files = []
    for top in ("backend", "frontend", "tests", "content"):
        for f in sorted((ROOT / top).rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts or "locales" in f.parts:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            test = top == "tests"
            if f.suffix == ".py":
                files.append((f, "py", text, _py_literals(f, text, test)))
            elif f.suffix == ".js":
                files.append((f, "js", text, _js_literals(text, test)))
            elif f.suffix == ".json" and top == "content":
                files.append((f, "json", text, _json_literals(text, f.parent == CONTENT and f.name in CONTENT_READ)))
            elif f.suffix in (".json", ".jsonl", ".sql", ".md", ".html", ".csv", ".txt"):
                files.append((f, "other", text, []))
    return files


def _tr_dump(d: dict, inline: bool, nl: bool = True) -> str:
    if inline:              # one line per key, plural objects inline: the style of most catalogue files
        return "{\n" + ",\n".join(f" {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "\n}\n"
    return json.dumps(d, ensure_ascii=False, indent=1) + ("\n" if nl else "")


def _tr_files(lang):
    out = []
    for f in sorted((I18N / lang).glob("*.json")):
        text = f.read_text(encoding="utf-8")
        d = json.loads(text)
        out.append({"path": f, "d": d, "inline": text == _tr_dump(d, True), "nl": text.endswith("\n"), "dirty": False})
    return out


def _tr_rename(files, old, new, val, keep_old, lang):
    """Move, merge or change one translation in a language's files; returns what was done ('' for nothing)."""
    has_old = [f for f in files if old in f["d"]]
    if new != old:
        if not has_old and val is None:
            return ""
        val = val if val is not None else has_old[-1]["d"][old]
        has_new = [f for f in files if new in f["d"]]
        did = "merged" if has_new else "copied" if keep_old else "moved"
        if has_new and (keep_old or not has_old) and all(f["d"][new] == val for f in has_new):
            return ""                                # done already (a second run)
        for f in has_new:                            # the new key exists already: the two keys merge
            if f["d"][new] != val:
                f["d"][new], f["dirty"] = val, True
        if not has_new and not has_old:
            has_new = [_tr_spare(files, lang)]
            has_new[0]["d"][new] = val
        for f in has_old:
            if keep_old and not has_new:
                f["d"][new] = val
            elif not keep_old and has_new:
                del f["d"][old]
            elif not keep_old:
                f["d"] = {(new if k == old else k): (val if k == old else v) for k, v in f["d"].items()}
            f["dirty"] = True
        return did
    if val is None:
        return ""
    did = ""
    for f in has_old or [_tr_spare(files, lang)]:
        if f["d"].get(old) != val:
            f["d"][old], f["dirty"], did = val, True, "changed"
    return did


def _tr_spare(files, lang):
    """The language's file for translations that had no file yet."""
    spare = I18N / lang / "language-20.json"
    for f in files:
        if f["path"] == spare:
            f["dirty"] = True
            return f
    files.append({"path": spare, "d": {}, "inline": True, "nl": True, "dirty": True})
    return files[-1]


def rename(mapping_path, apply=False):
    """Rewrite Azerbaijani keys and their translations from a mapping {old: {"az": new | null, "en": … | null,
    "ru": … | null, "only": [repo paths]?}} (null: keep). A key that also occurs as an unrelated literal, or inside a
    longer content string, is refused and nothing of it is written. With "only", code is rewritten in those files alone
    and the old key keeps its translations. Prints what it does; a dry run unless apply. Running it twice changes nothing."""
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    files = _scan_files()
    reads: dict = {}
    content_strings(reads)
    index: dict = {}
    whole: dict = {}
    for i, (_, _, _, lits) in enumerate(files):
        for j, lit in enumerate(lits):
            index.setdefault(lit[2], []).append((i, j))
            if lit[3] == "content":
                whole[lit[2]] = whole.get(lit[2], 0) + 1
    edits: dict = {}
    tr = {lg: _tr_files(lg) for lg in LANGS}
    total = {"renamed": 0, "refused": 0, "code": 0, "tests": 0, "translations": 0}
    for old, m in mapping.items():
        new = m.get("az") or old
        only = {ROOT / p for p in m.get("only") or ()}
        hits = [(i, j) for i, j in index.get(old, ()) if not only or files[i][0] in only]
        single = [(i, j) for i, j in hits if files[i][3][j][3] == "test" and " " not in old]
        hits = [h for h in hits if h not in single]       # a one-word test literal may be unrelated (a sheet name, a value)
        if new != old and (hits or (not only and any(old in f["d"] for lg in LANGS for f in tr[lg]))):
            if single:
                print(f"  NOTE test literal left as it is: {', '.join(f'{files[i][0].relative_to(ROOT).as_posix()}:{_line(files[i][2], files[i][3][j][0])}' for i, j in single[:4])}")
            bad = [(i, j) for i, j in hits if files[i][3][j][3] == "other"]
            if bad:
                where = ", ".join(f"{files[i][0].relative_to(ROOT).as_posix()}:{_line(files[i][2], files[i][3][j][0])}" for i, j in bad[:4])
                print(f"REFUSED {old[:70]!r}: also an unrelated literal at {where}")
                total["refused"] += 1
                continue
            if not only and reads.get(old, 0) != whole.get(old, 0):
                print(f"REFUSED {old[:70]!r}: content reads it {reads[old]} time(s), {whole.get(old, 0)} as a whole string")
                total["refused"] += 1
                continue
            for i, j in hits:
                edits.setdefault(i, []).append((files[i][3][j], new))
            ncode = sum(1 for i, j in hits if files[i][3][j][3] != "test")
            total["code"] += ncode
            total["tests"] += len(hits) - ncode
            total["renamed"] += 1
            places = sorted({files[i][0].relative_to(ROOT).as_posix() for i, _ in hits})
            print(f"RENAME {old[:60]!r} -> {new[:60]!r}: {ncode} in code, {len(hits) - ncode} in tests ({', '.join(places[:5])})")
            inside = sorted({f.relative_to(ROOT).as_posix() for i, (f, _, text, _) in enumerate(files)
                             if len(old) >= 8 and old in text and all(i != a for a, _ in hits)})
            if inside:
                print(f"  NOTE inside other text, not rewritten: {', '.join(inside[:6])}")
        for lg in LANGS:
            did = _tr_rename(tr[lg], old, new, m.get(lg), bool(only), lg)
            if did:
                total["translations"] += 1
                print(f"  {lg}: {did} {new[:60]!r}")
    for i, lst in edits.items():
        f, kind, text, _ = files[i]
        for (start, end, _, _), new in sorted(lst, key=lambda x: -x[0][0]):
            text = text[:start] + _literal(kind, text[start:end], new) + text[end:]
        if kind == "py":
            ast.parse(text)                          # a rewrite never leaves a file that does not parse
        if apply:
            f.write_text(text, encoding="utf-8")
    for lg in LANGS:
        for f in tr[lg]:
            if f["dirty"] and apply:
                f["path"].write_text(_tr_dump(f["d"], f["inline"], f["nl"]), encoding="utf-8")
    print(f"{'APPLIED' if apply else 'DRY RUN (add --apply to write)'}: {total['renamed']} key(s) renamed, {total['refused']} refused, "
          f"{total['code']} code and {total['tests']} test literal(s), {total['translations']} translation(s) moved or changed, "
          f"{len(edits)} file(s)")
    return total


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "lint":
        sys.exit(1 if lint(sys.argv[2:]) else 0)
    elif cmd == "extract":
        extract()
    elif cmd == "build":
        build()
    elif cmd == "rename" and len(sys.argv) > 2:
        rename(sys.argv[2], apply="--apply" in sys.argv[3:])
    else:
        stats()
