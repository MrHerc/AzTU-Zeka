"""Reading an old system's export file (tasks/todo.md, Task 38): a CSV of any size (UTF-8, the delimiter of its header
line), or an XLSX through the import's own reader. Returns the header and the numbered rows."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from zeka.modules.integration import tables  # noqa: E402


class AdapterError(ValueError):
    """The file cannot be read."""


def read(path: Path) -> tuple[list[str], list[tuple[int, list[str]]]]:
    data = path.read_bytes()
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        rows = tables.table_rows(path.name, data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AdapterError(f"{path.name}: not UTF-8") from None
        first = text.split("\n", 1)[0]
        delimiter = max(",;\t", key=first.count)
        rows = [(n + 1, r) for n, r in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)) if any(x.strip() for x in r)]
    if not rows:
        raise AdapterError(f"{path.name}: empty")
    return rows[0][1], rows[1:]


def to_csv(header: list[str], rows: list[dict]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    w.writerows([[x.get(k, "") for k in header] for x in rows])
    return out.getvalue().encode("utf-8")
