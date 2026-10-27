from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

from . import __version__
from .content import parse_record, reference_link, render_glossary
from .dictionaries import REPO_URL, Dictionary
from .models import ConversionStats, InputSet, ParsedEntry
from .package import TermBankWriter, deterministic_zip, write_json
from .resources import ResourceCatalog
from .source import input_inventory, iter_mdx_records


REFERENCE_MAX_HOPS = 8
TERM_TAGS = [
    ["variant", "name", 0, "原始 MDX 检索词形（与显示词头不同）", 0],
]


def _term_row(expression: str, reading: str, glossary: list[Any], sequence: int, tags: str = "") -> list[Any]:
    return [unicodedata.normalize("NFC", expression), unicodedata.normalize("NFC", reading), "", "", 0, glossary, sequence, tags]


def _signature(entry: list[Any]) -> bytes:
    encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def default_revision() -> str:
    return os.environ.get("MEDICAL_YOMITAN_REVISION", dt.date.today().strftime("%Y.%m.%d") + ".1")


class ReferenceResolver:
    """Resolve whole-entry references (即…/见…) to the entries they point at."""

    def __init__(self, entries: list[ParsedEntry], stats: ConversionStats):
        self.entries = entries
        self.stats = stats
        self.by_term: dict[str, list[int]] = {}
        for index, entry in enumerate(entries):
            for term in (entry.expression, entry.key):
                self.by_term.setdefault(term, [])
                if index not in self.by_term[term]:
                    self.by_term[term].append(index)
        self.cache: dict[int, list[int] | None] = {}

    def targets(self, index: int) -> list[int] | None:
        return self._resolve(index, ())

    def _resolve(self, index: int, stack: tuple[int, ...]) -> list[int] | None:
        if index in self.cache:
            return self.cache[index]
        entry = self.entries[index]
        if not entry.reference_target:
            return None
        if index in stack or len(stack) >= REFERENCE_MAX_HOPS:
            self.cache[index] = None
            return None
        candidates = [i for i in self.by_term.get(entry.reference_target, []) if i != index]
        if not candidates:
            self.cache[index] = None
            return None
        result: list[int] = []
        for candidate in candidates:
            if self.entries[candidate].reference_target:
                deeper = self._resolve(candidate, stack + (index,))
                if deeper:
                    result.extend(i for i in deeper if i not in result)
            elif candidate not in result:
                result.append(candidate)
        self.cache[index] = result or None
        return self.cache[index]


def build_dictionary(
    dictionary: Dictionary, inputs: InputSet, output: Path, *, revision: str | None = None,
    styles: Path | None = None,
) -> tuple[dict, Path]:
    started = time.perf_counter()
    inventory = input_inventory(inputs)
    mdx_sha = inventory["files"][0]["sha256"]
    stats = ConversionStats()
    output = output.resolve()
    report_path = output.with_name(dictionary.report)
    revision = revision or default_revision()
    styles = styles or Path(__file__).parent / "data" / "styles.css"

    with tempfile.TemporaryDirectory(prefix="medical-yomitan-") as temporary:
        temp = Path(temporary)
        stage = temp / "dictionary"
        stage.mkdir()
        resources = ResourceCatalog.build(inputs.mdds, temp / "resources", stats)

        entries: list[ParsedEntry] = []
        for ordinal, headword, raw in iter_mdx_records(inputs.mdx):
            stats.counters["input_records"] += 1
            if raw.lstrip().startswith("@@@LINK="):
                stats.counters["link_records_skipped"] += 1
                continue
            entry = parse_record(ordinal, headword, raw, resources, stats)
            if entry is not None:
                entries.append(entry)
        stats.counters["parsed_entries"] = len(entries)

        resolver = ReferenceResolver(entries, stats)
        bodies: list[list[Any]] = []
        embedded: list[list[tuple[ParsedEntry, list[Any]]]] = []
        for index, entry in enumerate(entries):
            body = entry.body
            targets: list[tuple[ParsedEntry, list[Any]]] = []
            if entry.reference_target:
                stats.counters["reference_entries_detected"] += 1
                resolved = resolver.targets(index)
                if resolved:
                    body = reference_link(entry)
                    targets = [(entries[i], entries[i].body) for i in resolved]
                    stats.counters["reference_entries_expanded"] += 1
                else:
                    stats.counters["reference_entries_unresolved"] += 1
                    stats.sample(stats.unresolved_reference_samples,
                                 {"expression": entry.expression, "target": entry.reference_target})
            bodies.append(body)
            embedded.append(targets)

        bank = TermBankWriter(stage, 10_000)
        seen: set[bytes] = set()
        expressions = {entry.expression for entry in entries}

        def emit(row: list[Any]) -> None:
            signature = _signature(row)
            if signature in seen:
                stats.counters["deduplicated_terms"] += 1
                return
            seen.add(signature)
            bank.add(row)
            stats.counters["emitted_terms"] += 1

        for index, entry in enumerate(entries):
            glossary = render_glossary(entry, bodies[index], embedded[index])
            emit(_term_row(entry.expression, entry.reading, glossary, entry.ordinal))
            for alternate in entry.alternate_terms:
                if alternate in expressions:
                    continue  # the MDX key already exists as a displayed headword
                emit(_term_row(alternate, entry.reading, glossary, entry.ordinal, "variant"))
                stats.counters["variant_terms"] += 1
        bank.close()

        index = {
            "title": dictionary.title,
            "revision": revision,
            "format": 3,
            "sequenced": True,
            "isUpdatable": True,
            "indexUrl": dictionary.index_url,
            "downloadUrl": dictionary.download_url,
            "author": dictionary.author,
            "url": REPO_URL,
            "description": dictionary.description,
            "attribution": (
                "原书版权归原作者与出版社所有；本转换仅供个人学习研究使用，转换器不授予任何再分发权利。"
                f" Converter medical_yomitan {__version__}; source MDX sha256 {mdx_sha[:12]}."
            ),
            "sourceLanguage": "zh",
            "targetLanguage": "zh",
        }
        write_json(stage / "index.json", index)
        (stage / "tag_bank_1.json").write_text(
            json.dumps(TERM_TAGS, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (stage / "styles.css").write_bytes(styles.read_bytes())

        package_files: list[tuple[str, Path | bytes]] = [(file.name, file) for file in stage.iterdir()]
        for resource in sorted(resources.used_outputs):
            package_files.append((resource, resources.output_to_file[resource]))
        output_sha = deterministic_zip(output, package_files)

        report = {
            "dictionary": dictionary.slug,
            "title": dictionary.title,
            "converter_version": __version__,
            "dictionary_revision": revision,
            "input": inventory,
            "output": {
                "path": str(output), "size": output.stat().st_size, "sha256": output_sha,
                "term_banks": bank.bank_number, "terms": bank.total,
                "images": len(resources.used_outputs),
            },
            "counts": dict(sorted(stats.counters.items())),
            "unknown_tags": dict(stats.unknown_tags.most_common()),
            "resource_extensions": dict(sorted(stats.resource_extensions.items())),
            "unused_resources": sorted(set(resources.output_to_file) - resources.used_outputs),
            "private_use_characters": {
                "counts": dict(sorted(stats.private_use.items())),
                "samples": stats.private_use_samples,
            },
            "missing_reading_samples": stats.missing_reading_samples,
            "unresolved_reference_samples": stats.unresolved_reference_samples,
            "warning_samples": stats.warning_samples,
            "error_samples": stats.error_samples,
            "build_seconds": round(time.perf_counter() - started, 2),
        }
        write_json(report_path, report)
    return report, report_path
