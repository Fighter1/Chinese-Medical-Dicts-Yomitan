import json
import zipfile
from pathlib import Path

import pytest

from medical_yomitan.builder import ReferenceResolver
from medical_yomitan.dictionaries import DICTIONARIES
from medical_yomitan.models import ConversionStats, ParsedEntry
from medical_yomitan.validation import validate_archive


def entry(ordinal: int, expression: str, target: str = "") -> ParsedEntry:
    return ParsedEntry(ordinal, expression, "", expression, body=["x"], reference_target=target)


def test_reference_resolver_follows_chains_and_breaks_cycles():
    entries = [entry(1, "a", "b"), entry(2, "b", "c"), entry(3, "c"), entry(4, "d", "e"), entry(5, "e", "d"), entry(6, "f", "zz")]
    resolver = ReferenceResolver(entries, ConversionStats())
    assert resolver.targets(0) == [2]
    assert resolver.targets(1) == [2]
    assert resolver.targets(3) is None
    assert resolver.targets(5) is None


@pytest.mark.parametrize("slug", sorted(DICTIONARIES))
def test_built_archive_validates(slug: str):
    archive = Path(__file__).resolve().parents[1] / "dist" / DICTIONARIES[slug].archive
    if not archive.exists():
        pytest.skip("dictionary not built")
    result = validate_archive(archive, schema=False)
    assert result["ok"], result["problems"][:5]
    with zipfile.ZipFile(archive) as zf:
        index = json.loads(zf.read("index.json"))
    assert index["title"] == DICTIONARIES[slug].title
    assert index["format"] == 3 and index["sequenced"] is True
