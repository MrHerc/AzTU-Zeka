"""Cuts the NICE test sample from the file NIST published (tasks/todo.md, Task 24). Nothing in it is written by hand:
every element and relationship is copied verbatim from content/frameworks/nice-components-2.2.0.json
(tests/integration/test_frameworks.py checks it). Run: python tests/fixtures/make_nice_sample.py

nice_sample.json   the work roles below with their category, OPM code, sort element and every task, knowledge and skill
                   statement they link to, one competency area with its statements, and every relationship among the
                   copied elements. Its document entry carries the version "0.0.0-sample": the importer knows the hash of
                   version 2.2.0 and refuses a cut-down copy of it, so the sample is an unknown version that imports with
                   its own hash.

OG-WRL-015 has the fewest statements, IO-WRL-003 is in another category, DD-WRL-009 has no OPM code and no sort
element; NF-COM-002 links to statements no copied work role links to.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "content" / "frameworks" / "nice-components-2.2.0.json"
OUT = HERE / "nice_sample.json"
ROLES = ("OG-WRL-015", "IO-WRL-003", "DD-WRL-009")
AREAS = ("NF-COM-002",)
VERSION = "0.0.0-sample"


def cut(src: dict) -> dict:
    rels = [(r["source_element_identifier"], r["dest_element_identifier"]) for r in src["relationships"]]
    keep = set(ROLES) | set(AREAS)
    keep |= {t for s, t in rels if s in ROLES or s in AREAS}         # their statements, OPM codes and sort elements
    keep |= {s for s, t in rels if t in ROLES}                         # the roles' categories
    return {"documents": [{**src["documents"][0], "version": VERSION}], "relationship_types": src["relationship_types"],
            "elements": [e for e in src["elements"] if e["element_identifier"] in keep],
            "relationships": [r for r in src["relationships"]
                              if r["source_element_identifier"] in keep and r["dest_element_identifier"] in keep]}


def main() -> None:
    sample = cut(json.loads(SOURCE.read_text(encoding="utf-8")))
    OUT.write_text(json.dumps(sample, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for e in sample["elements"]:
        kinds[e["element_type"]] = kinds.get(e["element_type"], 0) + 1
    print(f"{OUT.name}: {kinds}, {len(sample['relationships'])} relationships")


if __name__ == "__main__":
    main()
