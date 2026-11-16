import json
import zipfile
from pathlib import Path

import pytest

from medical_yomitan.content import parse_record, render_glossary
from medical_yomitan.dictionaries import DICTIONARIES
from medical_yomitan.golden import check_archive, load_golden, read_entries
from medical_yomitan.models import ConversionStats
from medical_yomitan.traditional import with_own_spelling

from test_content import record


def _row(term, reading, glossary, sequence, tags=""):
    return [term, reading, "", "", 0, glossary, sequence, tags]


@pytest.fixture()
def archive(tmp_path) -> Path:
    stats = ConversionStats()
    first = parse_record(1, "里急后重", record("里急后重", "tenesmus", "释义。"), None, stats)
    first_glossary = render_glossary(first, first.body, [], "裡急後重")
    second = parse_record(2, "B细胞", record("B<sub>1</sub>细胞", "B1 cell", "释义。"), None, stats)
    second_glossary = render_glossary(second, second.body, [], "B1細胞")
    plain = parse_record(3, "心率", record("心率", "heart rate", "释义。"), None, stats)
    plain_glossary = render_glossary(plain, plain.body, [])
    bank_1 = [
        _row("里急后重", first.reading, first_glossary, 1),
        _row("裡急後重", first.reading, first_glossary, 1),
    ]
    bank_2 = [                                    # an entry may straddle two term banks
        _row("裏急後重", first.reading, with_own_spelling(first_glossary, "裡急後重", "裏急後重"), 1),
        _row("B1细胞", second.reading, second_glossary, 2),
        _row("B1細胞", second.reading, second_glossary, 2),
        _row("B细胞", second.reading, second_glossary, 2, "variant"),
        _row("心率", plain.reading, plain_glossary, 3),
    ]
    path = tmp_path / "golden.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("index.json", json.dumps({"title": DICTIONARIES["xinbian-shiyong-yixue-cidian"].title,
                                              "revision": "2026.1.1.1", "format": 3}))
        zf.writestr("term_bank_1.json", json.dumps(bank_1, ensure_ascii=False))
        zf.writestr("term_bank_2.json", json.dumps(bank_2, ensure_ascii=False))
    return path


def _golden(tmp_path, *lines: str):
    path = tmp_path / "golden.tsv"
    path.write_text("# comment\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return load_golden(path)


def test_entries_are_read_across_term_banks(archive):
    index, by_headword, terms = read_entries(archive)
    (entry,) = by_headword["里急后重"]
    assert entry.boxes == {"里急后重": "裡急後重", "裡急後重": "裡急後重", "裏急後重": "裡急後重、裏急後重"}
    assert by_headword["B1细胞"][0].boxes["B细胞"] == "B1細胞"
    assert by_headword["心率"][0].boxes == {"心率": ""}
    assert "B细胞" in terms and "B细胞" not in by_headword


def test_checks_that_hold(archive, tmp_path):
    golden = _golden(
        tmp_path,
        "里急后重\tpresent",
        "里急后重\treading\tlǐ jí hòu zhòng",
        "里急后重\ttraditional\t裡急後重",
        "里急后重\ttraditional\t裏急後重",
        "里急后重\ttraditional_box\t裏急後重=裡急後重、裏急後重",
        "里急后重\ttraditional_box\t里急后重=裡急後重",
        "B1细胞\tindexed\tB细胞",
        "B1细胞\ttraditional_box\tB细胞=B1細胞",
        "心率\ttraditional_box\t心率=",
        "裡急后重\tabsent",
        "心率\treading\txīn lǜ\txinbian-shiyong-yixue-cidian",
        "心率\tabsent\t\txiandai-yixue-cidian",      # another dictionary's line is not checked here
    )
    result = check_archive(archive, golden)
    assert result == {"scope": "xinbian-shiyong-yixue-cidian", "checks": 11, "failures": []}


@pytest.mark.parametrize("line, found", [
    ("子宫\tpresent", "not an entry"),
    ("B细胞\tpresent", "not an entry of the dictionary (but a row is filed under it)"),
    ("裏急後重\tabsent", "a row is filed under it"),
    ("里急后重\treading\tlǐ jí hòu chóng", "reading ['lǐ jí hòu zhòng']"),
    ("里急后重\ttraditional\t裡急后重", "filed under"),
    ("心率\ttraditional\t心率", "filed under nothing else"),
    ("里急后重\ttraditional_box\t裏急後重=裡急後重", "it shows '裡急後重、裏急後重'"),
    ("里急后重\ttraditional_box\t里急後重=裡急後重", "not filed under 里急後重"),
    ("心率\ttraditional_box\t心率=心率", "no traditional box"),
])
def test_checks_that_fail(archive, tmp_path, line, found):
    result = check_archive(archive, _golden(tmp_path, line))
    assert len(result["failures"]) == 1 and found in result["failures"][0]
    assert "(line 3)" in result["failures"][0]


@pytest.mark.parametrize("line", [
    "子宫", "子宫\tspelled\t子宮", "子宫\treading", "子宫\tpresent\tx", "子宫\tpresent\t\tsomewhere",
    "子宫\ttraditional_box\t子宮", "子宫\ttraditional_box\t=子宮",
])
def test_malformed_lines_are_refused(tmp_path, line):
    with pytest.raises(ValueError):
        _golden(tmp_path, line)


def test_shipped_golden_words_cover_what_they_should():
    golden = load_golden()
    checks = {item["check"] for item in golden}
    assert checks == {"present", "absent", "reading", "indexed", "traditional", "traditional_box"}
    assert any("、" in item["value"] for item in golden if item["check"] == "traditional_box")
    assert any(item["value"].endswith("=") for item in golden if item["check"] == "traditional_box")
    assert any("α" in item["word"] for item in golden)


@pytest.mark.parametrize("slug", sorted(DICTIONARIES))
def test_built_archive_passes_the_golden_words(slug):
    built = Path(__file__).resolve().parents[1] / "dist" / DICTIONARIES[slug].archive
    if not built.exists():
        pytest.skip("dictionary not built")
    result = check_archive(built)
    assert result["scope"] == slug and result["checks"] > 40
    assert result["failures"] == []
