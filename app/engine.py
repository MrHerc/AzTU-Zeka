"""AI engine for the demo.

* Azerbaijani-aware tokenisation (I/İ casing, diacritic folding, light suffix
  stripping + 5-character truncation stemming) and an in-memory BM25 index.
* Offline "demo engine": composes grounded answers (Socratic / explain /
  practice) from retrieved course passages, always with citations.
* Optional LLM provider (OpenAI-compatible, Azure OpenAI, Anthropic) via
  urllib; on any failure the demo engine is used instead.
* Rule-based quiz generation from course material (glossary + parametric
  engineering/programming/maths templates).
"""
from __future__ import annotations

import io
import json
import math
import os
import random
import re
import threading
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from .i18n import S_

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- text utils
_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_FOLD = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ş": "s", "ç": "c", "ğ": "g"})
_WORD = re.compile(r"[0-9a-zəıöüşçğа-яё]+")
STOP = set("""
və ilə bu bir da də ki üçün olan olur edir nə necə hansı nədir nədi mən sən o biz siz onlar çox daha
isə amma lakin ya yaxud kimi görə qədər sonra əvvəl hər bütün belə elə artıq yalnız deyil var yox
olaraq edilir olunur etmək olmaq izah et edin elə mənə sənə ona bunu onu bunun onun niyə harada
zəhmət xahiş salam edək edim bilərəm bilər bilərsən lazımdır lazım ver verin de deyin göstər
the a an is of to in and or what how why
""".split())
_CASE = ("ndan", "nden", "dan", "den", "tan", "ten", "nda", "nde", "da", "de", "ta", "te", "nin", "nun")


def az_lower(s: str) -> str:
    return s.translate(_LOWER).lower()


def fold(s: str) -> str:
    return az_lower(s).translate(_FOLD)


def tokens(s: str) -> list[str]:
    return _WORD.findall(az_lower(s))


def stem(tok: str) -> str:
    t = tok.translate(_FOLD)
    if t.isdigit():
        return t
    if len(t) >= 6:
        for suf in _CASE:
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[: -len(suf)]
                break
        for suf in ("lar", "ler"):
            if t.endswith(suf) and len(t) - 3 >= 3:
                t = t[:-3]
                break
    return t[:5] if len(t) > 5 else t


def terms(s: str, drop_stop: bool = True) -> list[str]:
    out = []
    for t in tokens(s):
        if drop_stop and t in STOP:
            continue
        if len(t) < 2 and not t.isdigit():
            continue
        out.append(stem(t))
    return out


def plain(md: str) -> str:
    """Strip light markdown for sentence processing."""
    s = re.sub(r"```.*?```", " ", md, flags=re.S)
    s = re.sub(r"^#+\s*", "", s, flags=re.M)
    s = re.sub(r"^>\s*", "", s, flags=re.M)
    s = re.sub(r"^\s*[-*]\s+", "", s, flags=re.M)
    s = s.replace("**", "").replace("`", "")
    return s


def split_sentences(md: str) -> list[str]:
    text = re.sub(r"```.*?```", "\n", md, flags=re.S)
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        line = re.sub(r"^\s*[-*]\s+", "", line).replace("**", "").replace("`", "")
        for s in re.split(r"(?<=[.!?])\s+(?=[A-ZƏÖÜŞÇĞIİ0-9“\"(])", line):
            s = s.strip()
            if len(s) > 3:
                out.append(s)
    return out


def formulas(md: str) -> list[str]:
    return [l[1:].strip() for l in md.splitlines() if l.strip().startswith(">")]


def code_blocks(md: str) -> list[str]:
    return [m.strip("\n") for m in re.findall(r"```(?:\w+)?\n(.*?)```", md, flags=re.S)]


# ---------------------------------------------------------------- BM25 index
class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: dict = {}
        self.df: Counter = Counter()
        self.total_len = 0
        self.lock = threading.Lock()

    def add(self, doc_id, text: str, meta: dict | None = None, boost: str = ""):
        tf = Counter(terms(text) + terms(boost) * 2)
        with self.lock:
            if doc_id in self.docs:
                self._remove(doc_id)
            self.docs[doc_id] = (tf, sum(tf.values()), meta or {})
            self.df.update(tf.keys())
            self.total_len += sum(tf.values())

    def _remove(self, doc_id):
        tf, ln, _ = self.docs.pop(doc_id)
        self.df.subtract(tf.keys())
        self.total_len -= ln

    def remove(self, doc_id):
        with self.lock:
            if doc_id in self.docs:
                self._remove(doc_id)

    def search(self, query: str, k: int = 5, where=None) -> list[dict]:
        q = terms(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        avg = self.total_len / n if n else 1
        scores = []
        for doc_id, (tf, ln, meta) in list(self.docs.items()):
            if where and not where(meta):
                continue
            s = 0.0
            for t in set(q):
                f = tf.get(t)
                if not f:
                    continue
                df = self.df.get(t, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / avg))
            if s > 0:
                scores.append((s, doc_id, meta))
        scores.sort(key=lambda x: -x[0])
        return [{"id": d, "score": round(s, 3), **m} for s, d, m in scores[:k]]


INDEX = {"chunks": BM25(), "campus": BM25(), "questions": BM25()}

# ---------------------------------------------------------------- chunking
def chunk_markdown(md: str, max_chars: int = 1100) -> list[tuple[str, str]]:
    sections, heading, buf = [], "Giriş", []
    title = None
    for line in md.splitlines():
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((heading, "\n".join(buf).strip()))
    out = []
    for h, body in sections:
        if len(body) <= max_chars:
            out.append((h, body))
            continue
        part, cur = 1, ""
        for para in re.split(r"\n\s*\n", body):
            if cur and len(cur) + len(para) > max_chars:
                out.append((f"{h} ({part})", cur.strip()))
                part, cur = part + 1, ""
            cur += para + "\n\n"
        if cur.strip():
            out.append((f"{h} ({part})" if part > 1 else h, cur.strip()))
    return out


def glossary(md: str) -> list[tuple[str, str]]:
    pairs = []
    for line in md.splitlines():
        m = re.match(r"^\s*[-*]?\s*\*\*(.{2,60}?)\*\*\s*[—–-]\s+(.{12,})$", line)
        if not m:
            m = re.match(r"^\s*[-*]?\s*([A-ZƏÖÜŞÇĞİ][^—–\n]{1,50}?)\s+[—–]\s+(.{15,})$", line)
        if m:
            term = m.group(1).strip().strip("*")
            definition = m.group(2).strip()
            pairs.append((term, definition))
    return pairs


# ---------------------------------------------------------------- extraction
def _xml_text(data: bytes, para_tag: str, text_tag: str) -> list[str]:
    root = ET.fromstring(data)
    paras = []
    for p in root.iter():
        if p.tag.endswith("}" + para_tag):
            txt = "".join(t.text or "" for t in p.iter() if t.tag.endswith("}" + text_tag))
            if txt.strip():
                paras.append(txt.strip())
    return paras


def extract_text(filename: str, data: bytes) -> str:
    """Return markdown-ish text from .md/.txt/.docx/.pptx."""
    ext = Path(filename).suffix.lower()
    if ext in (".md", ".txt"):
        for enc in ("utf-8-sig", "cp1254", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    if ext == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        lines = []
        for p in root.iter():
            if not p.tag.endswith("}p"):
                continue
            style = ""
            for s in p.iter():
                if s.tag.endswith("}pStyle"):
                    style = next((v for k, v in s.attrib.items() if k.endswith("}val")), "")
            txt = "".join(t.text or "" for t in p.iter() if t.tag.endswith("}t")).strip()
            if not txt:
                continue
            if style.lower().startswith(("heading1", "title")):
                lines.append(f"# {txt}" if not lines else f"## {txt}")
            elif style.lower().startswith("heading"):
                lines.append(f"## {txt}")
            else:
                lines.append(txt)
            lines.append("")
        return "\n".join(lines)
    if ext == ".pptx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = sorted(
                (n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                key=lambda n: int(re.findall(r"\d+", n)[-1]),
            )
            out = []
            for i, n in enumerate(names, 1):
                paras = _xml_text(z.read(n), "p", "t")
                if not paras:
                    continue
                out.append(f"## Slayd {i}: {paras[0]}")
                out.extend(paras[1:])
                out.append("")
        return "\n".join(out)
    raise ValueError("Dəstəklənməyən fayl növü. Demo versiyada: .docx, .pptx, .txt, .md")


# ---------------------------------------------------------------- privacy
_PII = [
    ("E-POÇT", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("TELEFON", re.compile(r"(?:\+?994|0)[\s-]?(?:10|12|50|51|55|60|70|77|99)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")),
    ("KART", re.compile(r"\b(?:\d[ -]?){15,18}\d\b")),
    ("FİN", re.compile(r"\b(?=[0-9A-Z]{7}\b)(?=[0-9A-Z]*\d)(?=[0-9A-Z]*[A-Z])[0-9A-Z]{7}\b")),
]


def mask_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for label, rx in _PII:
        if rx.search(text):
            found.append(label)
            text = rx.sub(f"[{label}]", text)
    return text, found


# ---------------------------------------------------------------- LLM client
def llm_config() -> dict:
    cfg = {}
    path = ROOT / "config.json"
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8")).get("llm", {})
        except (OSError, ValueError):
            cfg = {}
    env = {
        "provider": os.environ.get("AZTU_LLM_PROVIDER"),
        "base_url": os.environ.get("AZTU_LLM_BASE_URL"),
        "api_key": os.environ.get("AZTU_LLM_API_KEY"),
        "model": os.environ.get("AZTU_LLM_MODEL"),
    }
    cfg.update({k: v for k, v in env.items() if v})
    cfg["enabled"] = bool(cfg.get("api_key") and cfg.get("model"))
    return cfg


def engine_info() -> dict:
    c = llm_config()
    if c["enabled"]:
        return {"mode": "llm", "label": f"{c.get('provider', 'openai')} · {c['model']}"}
    return {"mode": "demo", "label": S_("Demo AI mühərriki (oflayn)")}  # translated in responses


def llm_chat(system: str, messages: list[dict], max_tokens: int = 900) -> str:
    c = llm_config()
    if not c["enabled"]:
        raise RuntimeError("LLM konfiqurasiya edilməyib")
    provider = c.get("provider", "openai")
    timeout = float(c.get("timeout", 40))
    if provider == "anthropic":
        url = (c.get("base_url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        body = {"model": c["model"], "max_tokens": max_tokens, "system": system, "messages": messages}
        headers = {"x-api-key": c["api_key"], "anthropic-version": "2023-06-01"}
    elif provider == "azure":
        ver = c.get("api_version", "2024-10-21")
        url = f"{c['base_url'].rstrip('/')}/openai/deployments/{c['model']}/chat/completions?api-version={ver}"
        body = {"messages": [{"role": "system", "content": system}] + messages, "max_tokens": max_tokens, "temperature": 0.3}
        headers = {"api-key": c["api_key"]}
    else:
        url = (c.get("base_url") or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        body = {"model": c["model"], "messages": [{"role": "system", "content": system}] + messages,
                "max_tokens": max_tokens, "temperature": 0.3}
        headers = {"Authorization": f"Bearer {c['api_key']}"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if provider == "anthropic":
        return "".join(p.get("text", "") for p in data.get("content", []))
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- answer helpers (used by tutor.py)


def _pick(options, seed):
    return options[sum(map(ord, seed)) % len(options)]


def _is_example(h) -> bool:
    return "nümunə" in h["heading"].lower()


_NUM_EXAMPLE = re.compile(r"\d\s*(?:kΩ|Ω|V|A|Vt|µF|F|s)\b")


def top_sentences(hits, query, n=3, max_other=1):
    """Pick the most relevant sentences, mostly from the best passage.

    Worked-example sentences (concrete numbers) are demoted unless the question
    itself contains numbers, so explanations stay conceptual and Socratic hints
    never leak a ready solution.
    """
    q = set(terms(query))
    has_num = bool(re.search(r"\d", query))
    cands = []
    for hi, h in enumerate(hits[:3]):
        ex = _is_example(h)
        for si, s in enumerate(split_sentences(h["text"])):
            overlap = len(set(terms(s)) & q)
            if overlap == 0 and not (hi == 0 and si == 0):
                continue
            score = overlap * 2.0 - hi * 2.2 - si * 0.05
            if " — " in s or "adlanır" in s or "deyilir" in s or "ifadə edir" in s or "bərabərdir" in s:
                score += 1.2
            if "=" in s:
                score += 0.6
            if len(s) < 25:
                score -= 2
            if ex:
                score -= 1.2
            if not has_num and _NUM_EXAMPLE.search(s):
                score -= 1.5
            cands.append((score, hi, si, s))
    cands.sort(key=lambda c: -c[0])
    picked, other = [], 0
    for cand in cands:
        if cand[1] != 0:
            if other >= max_other:
                continue
            other += 1
        picked.append(cand)
        if len(picked) >= n:
            break
    picked.sort(key=lambda c: (c[1], c[2]))
    return [(c[1], c[3]) for c in picked]


class Cites:
    def __init__(self, hits):
        self.hits, self.order = hits, []

    def ref(self, hit_index):
        cid = self.hits[hit_index]["id"]
        if cid not in self.order:
            self.order.append(cid)
        return f"[{self.order.index(cid) + 1}]"


def _socratic_level(history, topic):
    level = 0
    for m in reversed(history):
        if m["role"] != "assistant":
            continue
        meta = m.get("meta") or {}
        if meta.get("mode") == "socratic" and meta.get("topic") == topic:
            level += 1
        else:
            break
    return level


# ---------------------------------------------------------------- practice
LETTERS = "ABCD"


def parse_number(s: str):
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    return float(m.group(0).replace(",", ".")) if m else None


def grade(q: dict, value) -> tuple[bool | None, str]:
    """Return (correct, normalized display of given answer). correct None = cannot parse."""
    qt = q["qtype"]
    if qt == "mcq":
        if isinstance(value, int):
            idx = value
        else:
            s = str(value).strip()
            m = re.search(r"\b([A-Da-d])\b", s) or re.match(r"^([A-Da-d])[).]?$", s)
            idx = LETTERS.index(m.group(1).upper()) if m else None
            if idx is None:
                for i, o in enumerate(q["options"]):
                    if fold(o) == fold(s):
                        idx = i
        if idx is None or idx >= len(q["options"]):
            return None, str(value)
        return idx == int(q["answer"]), LETTERS[idx]
    if qt == "tf":
        if isinstance(value, bool):
            v = value
        else:
            f = fold(str(value))
            if re.search(r"(dogru|duz|beli|true|\bhe\b)", f):
                v = True
            elif re.search(r"(yanlis|sehv|xeyr|false|deyil)", f):
                v = False
            else:
                return None, str(value)
        return v == bool(q["answer"]), "Doğru" if v else "Yanlış"
    num = value if isinstance(value, (int, float)) else parse_number(str(value))
    if num is None:
        return None, str(value)
    ans = float(q["answer"])
    ok = abs(num - ans) <= max(0.02 * abs(ans), 0.011)
    return ok, f"{num:g}"


def answer_display(q: dict) -> str:
    if q["qtype"] == "mcq":
        return f"{LETTERS[int(q['answer'])]}) {q['options'][int(q['answer'])]}"
    if q["qtype"] == "tf":
        return "Doğru" if q["answer"] else "Yanlış"
    return f"{float(q['answer']):g}" + (f" {q['unit']}" if q.get("unit") else "")


# ---------------------------------------------------------------- quiz generation
def _first_sentence(s: str, limit: int = 150) -> str:
    s = re.split(r"(?<=[.!?])\s", s.strip())[0].rstrip(".")
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def _fmt(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _numeric_templates(rng: random.Random):
    """(trigger, builder) -> builder returns (text, answer, unit, explanation, topic)."""

    def ohm():
        R = rng.choice([2, 4, 5, 8, 10, 12, 20, 25]); I = rng.choice([0.5, 1, 1.5, 2, 2.5, 3]); U = I * R
        return (f"Müqaviməti {_fmt(R)} Ω olan rezistora {_fmt(U)} V gərginlik verilib. Dövrədən keçən cərəyan şiddətini tapın.",
                I, "A", f"Om qanununa görə I = U / R = {_fmt(U)} / {_fmt(R)} = {_fmt(I)} A.", "Om qanunu")

    def power():
        U = rng.choice([12, 24, 110, 220]); I = rng.choice([0.5, 1, 2, 5]); P = U * I
        return (f"Gərginliyi {U} V, cərəyan şiddəti {_fmt(I)} A olan qurğunun gücünü tapın.",
                P, "Vt", f"P = U · I = {U} · {_fmt(I)} = {_fmt(P)} Vt.", "Elektrik gücü")

    def series():
        a, b = rng.sample([10, 20, 30, 40, 50, 60, 80, 100], 2)
        return (f"{a} Ω və {b} Ω müqavimətli iki rezistor ardıcıl birləşdirilib. Ekvivalent müqaviməti tapın.",
                a + b, "Ω", f"Ardıcıl birləşmədə R = R₁ + R₂ = {a} + {b} = {a + b} Ω.", "Ardıcıl birləşmə")

    def parallel():
        a, b = rng.choice([(6, 3), (12, 6), (20, 30), (10, 10), (40, 60), (12, 4)])
        r = a * b / (a + b)
        return (f"{a} Ω və {b} Ω müqavimətli iki rezistor paralel birləşdirilib. Ekvivalent müqaviməti tapın.",
                r, "Ω", f"R = R₁·R₂ / (R₁ + R₂) = {a}·{b} / ({a} + {b}) = {_fmt(r)} Ω.", "Paralel birləşmə")

    def kcl():
        i1, i2 = rng.randint(2, 6), rng.randint(1, 5); i3 = rng.randint(1, i1 + i2 - 1)
        return (f"Düyünə {i1} A və {i2} A cərəyanlar daxil olur, düyündən çıxan budaqlardan birində cərəyan {i3} A-dir. "
                "İkinci çıxan budaqdakı cərəyanı tapın.",
                i1 + i2 - i3, "A", f"Kirxhofun birinci qanununa görə {i1} + {i2} = {i3} + I₄, deməli I₄ = {i1 + i2 - i3} A.",
                "Kirxhofun birinci qanunu")

    def rc():
        R = rng.choice([1, 2, 5, 10, 20]); C = rng.choice([10, 47, 100, 220]); t = R * 1e3 * C * 1e-6
        return (f"R = {R} kΩ və C = {C} µF olan RC dövrəsinin zaman sabitini (τ) saniyə ilə tapın.",
                round(t, 4), "s", f"τ = R · C = {R}·10³ Ω · {C}·10⁻⁶ F = {_fmt(round(t, 4))} s.", "RC zaman sabiti")

    def py_loop():
        a, b = rng.randint(1, 5), rng.randint(7, 12)
        return (f"Aşağıdakı kod ekrana hansı ədədi çıxarar?\n\n```python\ns = 0\nfor i in range({a}, {b}):\n    s += i\nprint(s)\n```",
                sum(range(a, b)), "", f"range({a}, {b}) {a}-dən {b - 1}-ə qədər ədədləri verir; onların cəmi {sum(range(a, b))}-dir.",
                "for dövrü və range()")

    def py_list():
        lst = rng.sample(range(2, 20), 4); idx = rng.choice([0, 1, 2, 3, -1])
        return (f"Aşağıdakı kodun nəticəsi nədir?\n\n```python\na = {lst}\nprint(len(a) + a[{idx}])\n```",
                len(lst) + lst[idx], "", f"len(a) = 4, a[{idx}] = {lst[idx]}; nəticə 4 + {lst[idx]} = {4 + lst[idx]}.",
                "Siyahılar və indekslər")

    def py_if():
        x = rng.randint(5, 21); r = x // 2 if x % 2 == 0 else 3 * x + 1
        return (f"Aşağıdakı kod ekrana nə çıxarar?\n\n```python\nx = {x}\nif x % 2 == 0:\n    print(x // 2)\nelse:\n    print(3 * x + 1)\n```",
                r, "", f"{x} {'cüt' if x % 2 == 0 else 'tək'} ədəddir, ona görə nəticə {r}-dir.", "Şərt operatoru")

    def deriv():
        a, b, cc, x0 = rng.randint(1, 4), rng.randint(1, 5), rng.randint(1, 9), rng.randint(1, 3)
        v = 3 * a * x0 ** 2 + 2 * b * x0 - cc
        return (f"f(x) = {a}x³ + {b}x² − {cc}x funksiyasının x = {x0} nöqtəsində törəməsini tapın.",
                v, "", f"f′(x) = {3 * a}x² + {2 * b}x − {cc}; f′({x0}) = {v}.", "Törəmənin hesablanması")

    def limit():
        k = rng.randint(2, 7)
        return (f"lim (x→0) sin({k}x) / x limitini hesablayın.", k, "",
                f"sin({k}x)/x = {k} · sin({k}x)/({k}x) → {k} · 1 = {k}.", "Əlamətdar limitlər")

    def rms():
        um = rng.choice([141, 170, 283, 311, 424, 566])
        u = round(um / math.sqrt(2))
        return (f"Amplitudası {um} V olan sinusoidal gərginliyin effektiv qiymətini tapın (tam ədədə qədər).",
                u, "V", f"U = Uₘ / √2 = {um} / 1,414 ≈ {u} V.", "Effektiv qiymət")

    def reactance():
        f, L = 50, rng.choice([0.05, 0.1, 0.2, 0.3])
        x = round(2 * math.pi * f * L, 1)
        return (f"İnduktivliyi {_fmt(L)} H olan sarğacın 50 Hs tezlikdə induktiv müqavimətini tapın (onda bir dəqiqliklə).",
                x, "Ω", f"X_L = 2πf · L = 2 · 3,14 · 50 · {_fmt(L)} ≈ {_fmt(x)} Ω.", "Reaktiv müqavimətlər")

    def accel():
        v0, a, t = rng.choice([0, 2, 5]), rng.choice([1, 2, 3, 4]), rng.choice([3, 4, 5, 6])
        return (f"Başlanğıc sürəti {v0} m/s olan cisim {a} m/s² təcillə {t} s hərəkət edir. Son sürəti tapın.",
                v0 + a * t, "m/s", f"v = v₀ + a · t = {v0} + {a} · {t} = {v0 + a * t} m/s.", "Bərabərtəcilli hərəkət")

    def newton():
        m, a = rng.choice([2, 4, 5, 8, 10]), rng.choice([0.5, 1.5, 2, 3])
        return (f"Kütləsi {m} kq olan cismə {_fmt(m * a)} N əvəzləyici qüvvə təsir edir. Cismin təcilini tapın.",
                a, "m/s²", f"a = F / m = {_fmt(m * a)} / {m} = {_fmt(a)} m/s².", "Nyutonun ikinci qanunu")

    def friction():
        m, mu = rng.choice([4, 5, 8, 10, 20]), rng.choice([0.1, 0.2, 0.25, 0.3, 0.5])
        return (f"Kütləsi {m} kq olan qutu üfüqi səthdə sürüşür, sürtünmə əmsalı {_fmt(mu)}-dir. Sürtünmə qüvvəsini tapın (g = 10 m/s²).",
                round(mu * m * 10, 2), "N", f"F = μ · m · g = {_fmt(mu)} · {m} · 10 = {_fmt(round(mu * m * 10, 2))} N.", "Sürtünmə qüvvəsi")

    def integral():
        k, b = rng.choice([2, 4, 6]), rng.choice([1, 2, 3])
        return (f"∫₀^{b} {k}x dx müəyyən inteqralını hesablayın.", k * b * b / 2, "",
                f"İbtidai funksiya F(x) = {_fmt(k / 2)}x²; F({b}) − F(0) = {_fmt(k * b * b / 2)}.", "Nyuton–Leybnis düsturu")

    def scale():
        m, l = rng.choice([2, 5, 10, 20, 50]), rng.choice([12, 15, 24, 40, 60])
        return (f"1:{m} miqyasında çəkilmiş çertyojda xəttin uzunluğu {l} mm-dir. Həqiqi uzunluğu millimetrlə tapın.",
                l * m, "mm", f"Həqiqi ölçü = {l} × {m} = {l * m} mm.", "Miqyas")

    def py_dict():
        keys = rng.sample(["ad", "qrup", "bal", "kurs", "fakultə"], 3)
        extra = rng.choice([keys[0], "email"])
        n = 3 + (extra not in keys)
        return (f"Aşağıdakı kod ekrana hansı ədədi çıxarar?\n\n```python\nd = {{\"{keys[0]}\": 1, \"{keys[1]}\": 2, \"{keys[2]}\": 3}}\nd[\"{extra}\"] = 9\nprint(len(d))\n```",
                n, "", "Mövcud açara mənimsətmə qiyməti dəyişir, yeni açar isə yeni cüt əlavə edir.", "Lüğətlər")

    return [("om qanun", ohm), ("elektrik gucu", power), ("ardicil birlesme", series), ("paralel birlesme", parallel), ("kirxhof", kcl),
            ("zaman sabiti", rc), ("range(", py_loop), ("siyahi", py_list), ("elif", py_if), ("diferensiallama", deriv),
            ("elametdar limit", limit), ("effektiv qiymet", rms), ("reaktiv muqavimet", reactance),
            ("tecil", accel), ("nyutonun ikinci", newton), ("surtunme", friction), ("nyuton–leybnis", integral),
            ("miqyas", scale), ("luget", py_dict)]


def generate_questions(chunks: list[dict], course_glossary: list[tuple[str, str]], count: int = 6,
                       types=("mcq", "tf", "numeric"), seed: int | None = None) -> list[dict]:
    """chunks: [{id, heading, text}] from ONE material (or a course)."""
    rng = random.Random(seed)
    pool: dict[str, list] = {"mcq": [], "tf": [], "numeric": []}
    gl = []
    for ch in chunks:
        for term, d in glossary(ch["text"]):
            gl.append((term, d, ch))
    all_terms = list({t: d for t, d in course_glossary}.items()) or [(t, d) for t, d, _ in gl]
    for term, d, ch in gl:
        others = [t for t, _ in all_terms if fold(t) != fold(term)]
        other_defs = [od for t, od in all_terms if fold(t) != fold(term)]
        topic = re.sub(r"\s*\(\d+\)$", "", ch["heading"])
        if len(others) >= 3:
            opts = rng.sample(others, 3) + [term]
            rng.shuffle(opts)
            pool["mcq"].append({"qtype": "mcq", "text": f"Aşağıdakı tərif hansı anlayışa aiddir?\n\n“{_first_sentence(d, 220)}”",
                                "options": opts, "answer": opts.index(term), "bloom": "Xatırlama", "difficulty": "Asan",
                                "explanation": f"**{term}** — {d}", "topic": topic, "chunk_id": ch["id"]})
            dopts = [_first_sentence(x, 120) for x in rng.sample(other_defs, 3)] + [_first_sentence(d, 120)]
            correct = dopts[-1]
            rng.shuffle(dopts)
            pool["mcq"].append({"qtype": "mcq", "text": f"“{term}” anlayışının düzgün tərifi hansıdır?",
                                "options": dopts, "answer": dopts.index(correct), "bloom": "Anlama", "difficulty": "Orta",
                                "explanation": f"**{term}** — {d}", "topic": topic, "chunk_id": ch["id"]})
        if other_defs:
            truth = rng.random() < 0.5
            stmt_def = d if truth else rng.choice(other_defs)
            pool["tf"].append({"qtype": "tf", "text": f"Doğrudurmu: “{term} — {_first_sentence(stmt_def, 160)}.”",
                               "options": [], "answer": truth, "bloom": "Anlama", "difficulty": "Asan",
                               "explanation": f"Düzgün tərif: **{term}** — {d}", "topic": topic, "chunk_id": ch["id"]})
    for trigger, build in _numeric_templates(rng):
        src = next((ch for ch in chunks if trigger in fold(ch["text"]) or trigger in fold(ch["heading"])), None)
        if not src:
            continue
        for _ in range(2):
            text, ans, unit, expl, topic = build()
            pool["numeric"].append({"qtype": "numeric", "text": text, "options": [], "answer": ans, "unit": unit,
                                    "bloom": "Tətbiq", "difficulty": "Orta", "explanation": expl, "topic": topic,
                                    "chunk_id": src["id"]})
    for k in pool:
        rng.shuffle(pool[k])
    out, seen = [], set()
    order = [t for t in ("numeric", "mcq", "tf") if t in types]
    while len(out) < count and any(pool[t] for t in order):
        for t in order:
            while pool[t]:
                cand = pool[t].pop()
                key = fold(cand["text"])[:80]
                if key in seen:
                    continue
                seen.add(key)
                out.append(cand)
                break
            if len(out) >= count:
                break
    return out


def similarity(a: str, b: str) -> float:
    sa, sb = set(terms(a)), set(terms(b))
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


_TR = {"ə": "a", "Ə": "A", "ş": "sh", "Ş": "Sh", "ç": "ch", "Ç": "Ch", "ğ": "gh", "Ğ": "Gh", "ı": "i", "İ": "I",
       "ö": "o", "Ö": "O", "ü": "u", "Ü": "U", "x": "kh", "X": "Kh", "c": "j", "C": "J", "q": "g", "Q": "G"}


def translit(name: str) -> str:
    """Azerbaijani -> English Latin (passport-style), e.g. 'Aysel Məmmədova' -> 'Aysel Mammadova'."""
    return "".join(_TR.get(ch, ch) for ch in name)
