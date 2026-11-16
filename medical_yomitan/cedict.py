"""The pinned CC-CEDICT readings table and the command that refreshes it.

The build reads ``data/cedict_readings.tsv`` and nothing else: no download
happens at build time, so the same commit always produces the same readings.
The table is *derived* from the MDBG export of CC-CEDICT
(``cedict_1_0_ts_utf-8_mdbg.txt.gz``): for every simplified headword that has a
Han character, its numbered-pinyin readings in the order of the export. The
English glosses and the traditional forms are not kept. Its header records the
date of the export it was made from.

``python -m medical_yomitan cedict-refresh`` downloads the current export and
rewrites the table; ``--source FILE`` derives it from a local copy instead.

CC-CEDICT is published by MDBG under CC BY-SA 4.0 (https://cc-cedict.org/).
The derived table is distributed under the same licence.
"""
from __future__ import annotations

import gzip
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

EXPORT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
TABLE_PATH = Path(__file__).parent / "data" / "cedict_readings.tsv"
MIN_ENTRIES = 100_000       # the export has about 125,000 lines; fewer means a cut-off or wrong file
ATTRIBUTION = "Readings partly from CC-CEDICT (https://cc-cedict.org/), CC BY-SA 4.0."

_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\]")
_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
_META = re.compile(r"^# (export-date|export-entries|headwords): (.+)$")


@dataclass(frozen=True)
class CedictTable:
    export_date: str
    export_entries: int
    readings: dict[str, tuple[str, ...]]     # simplified headword -> numbered-pinyin readings, export order


def derive_table(export: bytes) -> str:
    """The text of the table for one MDBG export (gzip or plain)."""
    data = gzip.decompress(export) if export[:2] == b"\x1f\x8b" else export
    date = ""
    entries = 0
    readings: dict[str, list[str]] = {}
    for line in data.decode("utf-8").splitlines():
        if line.startswith("#"):
            if line.startswith("#! date="):
                date = line.removeprefix("#! date=").strip()
            continue
        match = _LINE.match(line)
        if not match:
            continue
        entries += 1
        simplified, pinyin = match.group(2), " ".join(match.group(3).split())
        if not _HAN.search(simplified) or not pinyin or "\t" in simplified:
            continue
        listed = readings.setdefault(simplified, [])
        if pinyin not in listed:
            listed.append(pinyin)
    if entries < MIN_ENTRIES:
        raise ValueError(f"only {entries:,} entries: not a complete CC-CEDICT export")
    if not date:
        raise ValueError("the export has no '#! date=' line")
    lines = [
        "# CC-CEDICT readings: simplified headword<TAB>numbered pinyin, one more column per further reading.",
        "# Derived from the MDBG export cedict_1_0_ts_utf-8_mdbg.txt.gz by `python -m medical_yomitan cedict-refresh`;",
        "# do not edit by hand. Corrections belong in pinyin_overrides.tsv.",
        "# CC-CEDICT is published by MDBG (https://cc-cedict.org/) under the Creative Commons",
        "# Attribution-ShareAlike 4.0 International License; this table is distributed under the same licence.",
        f"# export-date: {date}",
        f"# export-entries: {entries}",
        f"# headwords: {len(readings)}",
    ]
    lines += [simplified + "\t" + "\t".join(readings[simplified]) for simplified in sorted(readings)]
    return "\n".join(lines) + "\n"


def refresh(source: str | None = None, path: Path = TABLE_PATH) -> CedictTable:
    """Rewrite the table from ``source`` (a local export) or, without one, from MDBG.
    The table is replaced only by a complete export."""
    if source:
        export = Path(source).read_bytes()
    else:
        with urllib.request.urlopen(EXPORT_URL, timeout=120) as response:  # noqa: S310 - fixed https URL
            export = response.read()
    text = derive_table(export)
    temporary = path.with_suffix(".tsv.part")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return load_table(path)


def load_table(path: Path = TABLE_PATH) -> CedictTable:
    meta: dict[str, str] = {}
    readings: dict[str, tuple[str, ...]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.rstrip("\n")
            if line.startswith("#"):
                if match := _META.match(line):
                    meta[match.group(1)] = match.group(2)
                continue
            if not line:
                continue
            simplified, *listed = line.split("\t")
            readings[simplified] = tuple(listed)
    if "export-date" not in meta:
        raise ValueError(f"{path} has no '# export-date:' line")
    return CedictTable(meta["export-date"], int(meta.get("export-entries", "0")), readings)
