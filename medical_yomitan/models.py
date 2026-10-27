from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InputSet:
    mdx: Path
    mdds: tuple[Path, ...]


@dataclass
class ParsedEntry:
    ordinal: int
    expression: str
    reading: str
    key: str
    header: list[Any] = field(default_factory=list)
    body: list[Any] = field(default_factory=list)
    source: str = ""
    reference_prefix: str = ""
    reference_target: str = ""
    reference_suffix: str = ""
    alternate_terms: list[str] = field(default_factory=list)


@dataclass
class ConversionStats:
    counters: Counter[str] = field(default_factory=Counter)
    unknown_tags: Counter[str] = field(default_factory=Counter)
    resource_extensions: Counter[str] = field(default_factory=Counter)
    private_use: Counter[str] = field(default_factory=Counter)
    private_use_samples: dict[str, list[str]] = field(default_factory=dict)
    missing_reading_samples: list[str] = field(default_factory=list)
    unresolved_reference_samples: list[dict[str, str]] = field(default_factory=list)
    warning_samples: list[str] = field(default_factory=list)
    error_samples: list[str] = field(default_factory=list)

    def sample(self, target: list, value: Any, limit: int = 50) -> None:
        if value not in target and len(target) < limit:
            target.append(value)

    def warning(self, value: str) -> None:
        self.counters["warnings"] += 1
        self.sample(self.warning_samples, value)

    def error(self, value: str) -> None:
        self.counters["errors"] += 1
        self.sample(self.error_samples, value)

    def record_private_use(self, codepoint: str, context: str) -> None:
        self.private_use[codepoint] += 1
        self.sample(self.private_use_samples.setdefault(codepoint, []), context, 10)
