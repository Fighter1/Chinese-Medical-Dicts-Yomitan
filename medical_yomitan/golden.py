"""Golden words: facts about particular words that a built ZIP has to show.

``validate`` checks schemas, images and reading hygiene, which says nothing
about whether a particular word is still there and right. Each line of
``data/golden_words.tsv`` is one such fact::

    headword <TAB> check <TAB> value <TAB> scope

``scope`` is a dictionary slug (``xiandai-yixue-cidian``,
``xinbian-shiyong-yixue-cidian``) or empty for both. Checks:

``present``                the headword is an entry of the dictionary
``absent``                 nothing is filed under this term: no entry and no spelling of one
``reading VALUE``          an entry of the headword has this reading
``indexed VALUE``          an entry of the headword is also filed under this term
                           (a traditional spelling, an alternate MDX key);
                           ``traditional`` is the same check under another name
``traditional_box S=TEXT`` found by the term S, an entry of the headword shows TEXT in
                           its traditional box; nothing after ``=`` means no box

``python -m medical_yomitan golden ARCHIVE`` runs them; ``validate`` does too.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dictionaries import DICTIONARIES

GOLDEN_PATH = Path(__file__).parent / "data" / "golden_words.tsv"
CHECKS = ("present", "absent", "reading", "indexed", "traditional", "traditional_box")
NEEDS_VALUE = {"reading", "indexed", "traditional", "traditional_box"}
_BANK = re.compile(r"term_bank_(\d+)\.json")


def load_golden(path: Path = GOLDEN_PATH) -> list[dict[str, Any]]:
    """Parsed golden lines; blank lines and ``#`` comments are ignored."""
    scopes = ("", *DICTIONARIES)
    golden: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            word, check, value, scope = ([part.strip() for part in line.split("\t")] + ["", "", ""])[:4]
            if not word or check not in CHECKS or scope not in scopes or (check in NEEDS_VALUE) != bool(value):
                raise ValueError(
                    f"{path}:{number}: expected 'headword<TAB>check[<TAB>value[<TAB>scope]]' with a check from "
                    f"{', '.join(CHECKS)} and a scope from {', '.join(DICTIONARIES)}; got {line!r}")
            if check == "traditional_box" and ("=" not in value or value.startswith("=")):
                raise ValueError(f"{path}:{number}: traditional_box needs TERM=TEXT (nothing after = for no box), "
                                 f"got {value!r}")
            golden.append({"word": word, "check": check, "value": value, "scope": scope, "line": number})
    return golden


@dataclass
class Entry:
    """One entry as the ZIP shows it: the rows that share a sequence number.
    ``boxes``: for every term the entry is filed under, the headword included,
    what its traditional box shows when it is found by that term ("" for no box)."""
    headword: str
    sequence: int
    reading: str
    boxes: dict[str, str] = field(default_factory=dict)


def _badges(glossary: list[Any]) -> dict[str, str]:
    terms = glossary[0]["content"]["content"][0]["content"][0]["content"]
    return {node["data"]["content"]: node["content"] for node in terms}


def read_entries(archive: Path) -> tuple[dict[str, Any], dict[str, list[Entry]], set[str]]:
    """(index.json, headword -> its entries, every term a row is filed under)."""
    with zipfile.ZipFile(archive) as zf:
        index = json.loads(zf.read("index.json"))
        names = sorted((name for name in zf.namelist() if _BANK.fullmatch(name)),
                       key=lambda name: int(_BANK.fullmatch(name).group(1)))  # type: ignore[union-attr]
        by_headword: dict[str, list[Entry]] = {}
        terms: set[str] = set()
        current: Entry | None = None
        for name in names:
            for term, reading, _tags, _rules, _score, glossary, sequence, _term_tags in json.loads(zf.read(name)):
                terms.add(term)
                badges = _badges(glossary)
                if current is None or sequence != current.sequence:
                    current = Entry(badges["simplified-term"], sequence, reading)
                    by_headword.setdefault(current.headword, []).append(current)
                current.boxes[term] = badges.get("traditional-term", "")
    return index, by_headword, terms


def _check(golden: dict[str, Any], entries: list[Entry], terms: set[str]) -> str | None:
    """None when the check holds, else what was found instead."""
    check, value, word = golden["check"], golden["value"], golden["word"]
    if check == "absent":
        return None if word not in terms else "a row is filed under it"
    if not entries:
        return "not an entry of the dictionary" + (" (but a row is filed under it)" if word in terms else "")
    if check == "present":
        return None
    if check == "reading":
        found = sorted({entry.reading for entry in entries})
        return None if value in found else f"reading {found}"
    if check in ("indexed", "traditional"):
        found = sorted(set().union(*(entry.boxes for entry in entries)) - {word})
        return None if value in found else f"filed under {found or 'nothing else'}"
    if check == "traditional_box":
        term, _, text = value.partition("=")
        shown = [entry.boxes[term] for entry in entries if term in entry.boxes]
        if not shown:
            return f"not filed under {term}; filed under {sorted(set().union(*(entry.boxes for entry in entries)))}"
        other = [box for box in shown if box != text]
        return None if not other else f"found by {term} it shows " + (repr(other[0]) if other[0] else "no traditional box")
    raise ValueError(check)


def scope_of(index: dict[str, Any]) -> str:
    for slug, dictionary in DICTIONARIES.items():
        if dictionary.title == index.get("title"):
            return slug
    return ""


def check_archive(archive: Path, golden: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """{"scope", "checks", "failures": [printable lines]} for one built ZIP."""
    golden = load_golden() if golden is None else golden
    index, by_headword, terms = read_entries(archive)
    scope = scope_of(index)
    failures: list[str] = []
    checks = 0
    for item in golden:
        if item["scope"] not in ("", scope):
            continue
        checks += 1
        problem = _check(item, by_headword.get(item["word"], []), terms)
        if problem:
            failures.append(f"{item['word']}  {item['check']}" + (f"  {item['value']}" if item["value"] else "")
                            + f"  (line {item['line']}): {problem}")
    return {"scope": scope, "checks": checks, "failures": failures}
