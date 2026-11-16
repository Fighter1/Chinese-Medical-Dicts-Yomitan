"""Traditional spellings of headwords, so a lookup from traditional text finds the entries.

Both sources are in simplified characters only and say nothing about which
traditional character a simplified one stands for, so the conversion is
OpenCC's (``opencc-python-reimplemented``, the package Baidu-Baike-Yomitan
uses, so both projects convert alike).

* The form an entry **shows** is Taiwan's, ``s2tw``: 里面 → 裡面, 综合征 → 綜合徵.
  Never ``s2twp``: that one also swaps vocabulary (循环 → 迴圈, 信息 → 資訊, 酰 → 醯)
  and would turn a headword into another term.
* Two more standards are **looked up without being shown**: Hong Kong's
  (``s2hk``: 里面 → 裏面) and OpenCC's own (``s2t``: 为 → 爲, 群众 → 羣衆).

Latin, Greek and digits are not touched by any of them. Characters restored
from the source's private-use placeholders (``keep``) are passed through as
they are: they are inferences already and are not converted a second time.

OpenCC converts phrase by phrase and reads some medical terms as another word
(血症 as the 中医 term 血癥, 巨细胞 as 鉅細胞, the 里 of a transliterated name as
裡). ``data/traditional_corrections.tsv`` lists those; they are corrected after
the conversion, in all three standards.
"""
from __future__ import annotations

import unicodedata
from copy import copy
from pathlib import Path
from typing import Any

SHOWN_CONFIG = "s2tw"
LOOKUP_CONFIGS = ("s2hk", "s2t")
TRADITIONAL_LANG = "zh-TW"
SEPARATOR = "、"
CORRECTIONS_PATH = Path(__file__).parent / "data" / "traditional_corrections.tsv"


def load_corrections(path: Path | None = CORRECTIONS_PATH) -> list[tuple[str, str]]:
    """``simplified phrase<TAB>traditional form`` per line; blank lines and ``#`` comments are ignored."""
    corrections: list[tuple[str, str]] = []
    if path is None or not Path(path).exists():
        return corrections
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = [unicodedata.normalize("NFC", part.strip()) for part in line.split("\t")]
            if len(parts) != 2 or not parts[0] or len(parts[0]) != len(parts[1]):
                raise ValueError(f"{path}:{number}: expected 'simplified phrase<TAB>traditional form' of the same "
                                 f"length, got {line!r}")
            if parts[0] in seen:
                raise ValueError(f"{path}:{number}: {parts[0]!r} is listed twice")
            seen.add(parts[0])
            corrections.append((parts[0], parts[1]))
    return corrections


class Traditional:
    """Callable helpers around the three OpenCC converters; conversions are cached per (term, keep).

    ``corrections_path``: the table of forms OpenCC gets wrong (see its header).
    A correction is positional. OpenCC never changes the number of characters of
    a headword here, so the phrase found at some place in the simplified term
    is the same place in every converted form."""

    def __init__(self, corrections_path: Path | None = CORRECTIONS_PATH) -> None:
        from opencc import OpenCC

        self._shown = OpenCC(SHOWN_CONFIG)
        self._lookup = tuple(OpenCC(name) for name in LOOKUP_CONFIGS)
        self._cache: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {}
        # (phrase, {offset in the phrase: the character that belongs there}), longest phrase first
        self._corrections: list[tuple[str, dict[int, str]]] = []
        for phrase, form in load_corrections(corrections_path):
            written = self._shown.convert(phrase)
            fixes = {offset: ch for offset, (ch, was) in enumerate(zip(form, written)) if ch != was}
            if len(written) != len(phrase) or not fixes:
                raise ValueError(f"{corrections_path}: OpenCC already writes {written!r} for {phrase!r}; the line "
                                 "corrects nothing. Make the phrase long enough to contain what misleads OpenCC.")
            self._corrections.append((phrase, fixes))
        self._corrections.sort(key=lambda item: -len(item[0]))
        # phrase -> the distinct terms it corrected, for the conversion report
        self.corrected: dict[str, set[str]] = {phrase: set() for phrase, _ in self._corrections}

    def _fixes_for(self, term: str, keep: str) -> dict[int, str]:
        """position in ``term`` -> the character the corrections put there."""
        fixes: dict[int, str] = {}
        for phrase, phrase_fixes in self._corrections:
            start = term.find(phrase)
            while start >= 0:
                wanted = {start + offset: ch for offset, ch in phrase_fixes.items() if term[start + offset] not in keep}
                if wanted and not fixes.keys() & wanted.keys():      # a longer phrase got there first
                    fixes.update(wanted)
                    self.corrected[phrase].add(term)
                start = term.find(phrase, start + 1)
        return fixes

    @staticmethod
    def _apply(form: str, fixes: dict[int, str], length: int) -> str:
        if not fixes or len(form) != length:
            return form
        characters = list(form)
        for position, ch in fixes.items():
            characters[position] = ch
        return "".join(characters)

    @staticmethod
    def _convert(converter: Any, text: str, keep: str) -> str:
        if not keep or not any(ch in keep for ch in text):
            return unicodedata.normalize("NFC", converter.convert(text))
        pieces: list[str] = []
        run: list[str] = []
        for ch in text:
            if ch in keep:
                if run:
                    pieces.append(converter.convert("".join(run)))
                    run = []
                pieces.append(ch)
            else:
                run.append(ch)
        if run:
            pieces.append(converter.convert("".join(run)))
        return unicodedata.normalize("NFC", "".join(pieces))

    def spellings(self, term: str, keep: str = "") -> tuple[str, tuple[str, ...]]:
        """(the Taiwan form, ``""`` when it equals ``term``; the lookup-only spellings).

        The lookup-only spellings are what the other standards write, in the
        order of ``LOOKUP_CONFIGS``, without ``term`` itself, the Taiwan form
        and repeats."""
        key = (term, keep)
        hit = self._cache.get(key)
        if hit is None:
            fixes = self._fixes_for(term, keep) if self._corrections else {}
            taiwan = self._apply(self._convert(self._shown, term, keep), fixes, len(term))
            seen = {term, taiwan}
            others: list[str] = []
            for converter in self._lookup:
                form = self._apply(self._convert(converter, term, keep), fixes, len(term))
                if form not in seen:
                    seen.add(form)
                    others.append(form)
            hit = self._cache[key] = ("" if taiwan == term else taiwan, tuple(others))
        return hit


def traditional_box(text: str) -> dict[str, Any]:
    return {"tag": "span", "content": text, "data": {"content": "traditional-term"}, "lang": TRADITIONAL_LANG}


def with_own_spelling(glossary: list[dict[str, Any]], shown: str, term: str) -> list[dict[str, Any]]:
    """The glossary for a row that is found by a spelling the entry does not show
    (裏面 for an entry that displays 裡面): the same entry with ``term`` after the
    Taiwan form in the traditional box, 裡面、裏面, so whoever looked the spelling
    up sees it among the forms. ``shown`` is ``""`` when the entry shows no
    Taiwan form because it equals the headword; the box then holds ``term`` alone.

    Only the path down to the badge row is copied. Everything under it (header,
    definition, embedded referenced entries, source line) is the very objects of
    ``glossary``: the entry is not rendered again."""
    (definition,) = glossary
    wrapper = definition["content"]
    first_row, *rest = wrapper["content"]
    (terms,) = first_row["content"]
    simplified = terms["content"][-1]
    box = traditional_box(f"{shown}{SEPARATOR}{term}" if shown else term)
    new_terms = copy(terms)
    new_terms["content"] = [box, simplified]
    new_first_row = copy(first_row)
    new_first_row["content"] = [new_terms]
    new_wrapper = copy(wrapper)
    new_wrapper["content"] = [new_first_row, *rest]
    new_definition = copy(definition)
    new_definition["content"] = new_wrapper
    return [new_definition]
