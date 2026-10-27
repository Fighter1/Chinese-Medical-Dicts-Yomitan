"""Archive-wide checks for a built Yomitan ZIP."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import jsonschema

try:  # Compiles the recursive structured-content schema to Python; far faster than jsonschema.
    import fastjsonschema
except ImportError:  # pragma: no cover - optional dependency
    fastjsonschema = None

from .content import ENTRY_KIND
from .readings import is_clean_reading


SCHEMAS = Path(__file__).parent / "schemas"
FORBIDDEN_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "audio", "video", "canvas"}


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        yield from _walk(value.get("content"))
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def validate_archive(path: Path, *, schema: bool = True) -> dict[str, Any]:
    problems: list[str] = []
    counts = {"terms": 0, "banks": 0, "images": 0, "image_references": 0}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "index.json" not in names:
            raise ValueError("index.json missing from archive")
        index = json.loads(archive.read("index.json").decode("utf-8"))
        if schema:
            jsonschema.validate(index, _load_schema("dictionary-index-schema.json"))
        if index.get("format") != 3:
            problems.append("index.json format is not 3")
        if "styles.css" not in names:
            problems.append("styles.css missing")
        counts["images"] = sum(1 for name in names if name.startswith("media/"))
        term_schema = _load_schema("dictionary-term-bank-v3-schema.json")
        validator = None
        if schema:
            if fastjsonschema is not None:
                compiled = fastjsonschema.compile(term_schema)

                class _Fast:
                    @staticmethod
                    def iter_errors(bank: Any):
                        try:
                            compiled(bank)
                        except fastjsonschema.JsonSchemaException as exc:  # type: ignore[union-attr]
                            yield exc

                validator = _Fast()
            else:
                validator = jsonschema.Draft7Validator(term_schema)
        banks = sorted(name for name in names if re.fullmatch(r"term_bank_\d+\.json", name))
        if not banks:
            problems.append("no term banks")
        readings_seen = 0
        for name in banks:
            bank = json.loads(archive.read(name).decode("utf-8"))
            counts["banks"] += 1
            counts["terms"] += len(bank)
            if validator is not None:
                for error in validator.iter_errors(bank):
                    location = list(getattr(error, "absolute_path", []))[:6] or getattr(error, "path", "")
                    problems.append(f"{name}: schema: {str(error)[:300]} at {location}")
                    if len(problems) > 50:
                        break
            for row in bank:
                expression, reading = row[0], row[1]
                if not expression.strip():
                    problems.append(f"{name}: empty expression")
                if reading and not is_clean_reading(reading):
                    problems.append(f"{name}: unclean reading {reading!r} for {expression!r}")
                readings_seen += bool(reading)
                for glossary in row[5]:
                    if not isinstance(glossary, dict) or glossary.get("type") != "structured-content":
                        problems.append(f"{name}: non-structured glossary for {expression!r}")
                        continue
                    content = glossary["content"]
                    if content.get("lang") != "zh-Hans" or content.get("data", {}).get("content") != ENTRY_KIND:
                        problems.append(f"{name}: entry wrapper missing lang/kind for {expression!r}")
                    for node in _walk(content):
                        tag = node.get("tag")
                        if tag in FORBIDDEN_TAGS:
                            problems.append(f"{name}: forbidden tag {tag} in {expression!r}")
                        if tag == "img":
                            counts["image_references"] += 1
                            if node.get("path") not in names:
                                problems.append(f"{name}: missing image {node.get('path')} in {expression!r}")
                        if tag == "a" and not str(node.get("href", "")).startswith("?query="):
                            problems.append(f"{name}: unexpected link {node.get('href')} in {expression!r}")
                if len(problems) > 200:
                    break
        counts["terms_with_readings"] = readings_seen
    return {"archive": str(path), "title": index.get("title"), "revision": index.get("revision"),
            "counts": counts, "problems": problems[:200], "ok": not problems}
