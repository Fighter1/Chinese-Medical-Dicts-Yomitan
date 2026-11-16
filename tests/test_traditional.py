import json
import zipfile

import pytest

from medical_yomitan.content import form_row, parse_record, render_glossary
from medical_yomitan.models import ConversionStats
from medical_yomitan.traditional import (
    LOOKUP_CONFIGS, SHOWN_CONFIG, Traditional, load_corrections, with_own_spelling,
)

from test_content import record


@pytest.fixture(scope="module")
def traditional() -> Traditional:
    return Traditional()


def test_standards():
    assert SHOWN_CONFIG == "s2tw"
    assert LOOKUP_CONFIGS == ("s2hk", "s2t")


def test_taiwan_form_and_lookup_only_spellings(traditional):
    assert traditional.spellings("里急后重") == ("裡急後重", ("裏急後重",))
    assert traditional.spellings("腭") == ("顎", ("齶",))
    # the three standards agree: one Taiwan form, nothing to look up besides
    assert traditional.spellings("综合征") == ("綜合徵", ())


def test_no_form_when_nothing_changes(traditional):
    assert traditional.spellings("APUD") == ("", ())
    assert traditional.spellings("甲亢") == ("", ())


def test_lookup_only_without_a_taiwan_form(traditional):
    # 群 is the Taiwan character already; Hong Kong and OpenCC write 羣
    assert traditional.spellings("群") == ("", ("羣",))


def test_vocabulary_is_never_swapped(traditional):
    # s2twp would write 迴圈, 資訊 and 醯
    assert traditional.spellings("三羧酸循环")[0] == "三羧酸循環"
    assert traditional.spellings("信息偏倚") == ("", ())
    assert traditional.spellings("医学信息处理")[0] == "醫學信息處理"
    assert traditional.spellings("乙酰乙酸")[0] == ""


def test_latin_greek_and_digits_pass_through(traditional):
    assert traditional.spellings("17-α-羟化酶缺失综合征")[0] == "17-α-羥化酶缺失綜合徵"
    assert traditional.spellings("A型人格") == ("", ())


def test_restored_characters_pass_through(traditional):
    # OpenCC maps 𫫇 to 噁; a character restored from a private-use placeholder is kept as restored
    assert traditional.spellings("磺胺异𫫇唑")[0] == "磺胺異噁唑"
    assert traditional.spellings("磺胺异𫫇唑", keep="𫫇")[0] == "磺胺異𫫇唑"
    assert traditional.spellings("开𬌗", keep="𬌗")[0] == "開𬌗"


# --- corrections applied after OpenCC ---------------------------------------------

def _table(tmp_path, *lines: str):
    path = tmp_path / "corrections.tsv"
    path.write_text("# comment" + chr(10) + chr(10) + chr(10).join(lines) + chr(10), encoding="utf-8")
    return path


def test_without_the_table_the_forms_are_opencc_s():
    plain = Traditional(None)
    assert plain.spellings("低氧血症") == ("低氧血癥", ())
    assert plain.spellings("范可尼综合征")[0] == "範可尼綜合徵"


def test_a_corrected_form_that_equals_the_headword_is_no_form(traditional):
    assert traditional.spellings("低氧血症") == ("", ())
    assert traditional.spellings("阿托品") == ("", ())


def test_corrections_hold_in_all_three_standards_and_leave_the_other_characters(traditional):
    # 發 is corrected everywhere; 衛 / 衞 stays each standard's own
    assert traditional.spellings("卫生发展管理程序") == ("衛生發展管理程序", ("衞生發展管理程序",))
    # the lookup-only spelling is corrected too, and keeps Hong Kong's 着
    assert traditional.spellings("着色性干皮病") == ("著色性乾皮病", ("着色性乾皮病",))
    assert traditional.spellings("范可尼综合征") == ("范可尼綜合徵", ())


def test_what_opencc_has_right_is_left_alone(traditional):
    assert traditional.spellings("里急后重") == ("裡急後重", ("裏急後重",))      # not a transliterated 里
    assert traditional.spellings("揉面感")[0] == "揉麵感"                        # flour
    assert traditional.spellings("钟情妄想")[0] == "鍾情妄想"
    assert traditional.spellings("吞咽")[0] == "吞嚥"
    assert traditional.spellings("脑干损伤")[0] == "腦幹損傷"                    # a stem, not dry


def test_a_correction_applies_wherever_the_phrase_occurs(tmp_path):
    table = _table(tmp_path, "血症	血症", "后角	後角")
    corrected = Traditional(table)
    assert corrected.spellings("高脂蛋白血症Ⅱa型") == ("", ())                   # now its own Taiwan form
    assert corrected.spellings("脊髓后根（后角）性感觉障碍")[0] == "脊髓後根（後角）性感覺障礙"
    assert corrected.spellings("低钾血症与高钾血症")[0] == "低鉀血症與高鉀血症"   # both occurrences
    assert corrected.corrected["血症"] == {"高脂蛋白血症Ⅱa型", "低钾血症与高钾血症"}


def test_the_longer_phrase_wins(tmp_path):
    corrected = Traditional(_table(tmp_path, "干皮	干皮", "色性干皮病	色性乾皮病"))
    assert corrected.spellings("着色性干皮病")[0] == "著色性乾皮病"
    assert corrected.corrected["干皮"] == set()


@pytest.mark.parametrize("line", ["血症 血症", "血症	血", "	血症", "血症	血症	血症"])
def test_malformed_correction_lines_are_refused(tmp_path, line):
    with pytest.raises(ValueError):
        load_corrections(_table(tmp_path, line))


def test_a_correction_listed_twice_is_refused(tmp_path):
    with pytest.raises(ValueError, match="twice"):
        load_corrections(_table(tmp_path, "血症	血症", "血症	血癥"))


def test_a_line_that_corrects_nothing_is_refused(tmp_path):
    # OpenCC writes 綜合徵 already
    with pytest.raises(ValueError, match="corrects nothing"):
        Traditional(_table(tmp_path, "综合征	綜合徵"))


def test_shipped_corrections_use_characters_all_three_standards_write_alike():
    from opencc import OpenCC

    to_hong_kong, to_taiwan, shown = OpenCC("t2hk"), OpenCC("t2tw"), OpenCC(SHOWN_CONFIG)
    corrections = load_corrections()
    assert len(corrections) > 40
    for phrase, form in corrections:
        for right, was in zip(form, shown.convert(phrase)):
            if right != was:
                assert to_hong_kong.convert(right) == right and to_taiwan.convert(right) == right, (phrase, right)


def test_badge_row_has_the_traditional_box_on_the_left():
    terms = form_row("里急后重", "裡急後重")["content"][0]["content"]
    assert [node["data"]["content"] for node in terms] == ["traditional-term", "simplified-term"]
    assert terms[0] == {"tag": "span", "content": "裡急後重", "data": {"content": "traditional-term"}, "lang": "zh-TW"}
    assert "lang" not in terms[1]


def test_no_traditional_box_when_the_form_equals_the_headword():
    for traditional_form in ("", "甲亢"):
        terms = form_row("甲亢", traditional_form)["content"][0]["content"]
        assert [node["data"]["content"] for node in terms] == ["simplified-term"]


def _glossary(taiwan: str):
    entry = parse_record(1, "里急后重", record("里急后重", "tenesmus", "释义。"), None, ConversionStats())
    return render_glossary(entry, entry.body, [], taiwan)


def _box(glossary):
    terms = glossary[0]["content"]["content"][0]["content"][0]["content"]
    return [node["content"] for node in terms if node["data"]["content"] == "traditional-term"]


def test_with_own_spelling_replaces_only_the_box():
    glossary = _glossary("裡急後重")
    before = json.dumps(glossary, ensure_ascii=False)
    own = with_own_spelling(glossary, "裡急後重", "裏急後重")
    assert _box(own) == ["裡急後重、裏急後重"]
    # the entry itself is untouched, and everything under the badge row is shared, not rendered again
    assert json.dumps(glossary, ensure_ascii=False) == before
    assert _box(glossary) == ["裡急後重"]
    for mine, theirs in zip(own[0]["content"]["content"][1:], glossary[0]["content"]["content"][1:], strict=True):
        assert mine is theirs
    assert own[0]["content"]["lang"] == "zh-Hans"


def test_with_own_spelling_when_the_entry_shows_no_taiwan_form():
    glossary = _glossary("")
    assert _box(glossary) == []
    assert _box(with_own_spelling(glossary, "", "羣")) == ["羣"]


def test_parse_record_remembers_restored_characters():
    stats = ConversionStats()
    raw = record('磺胺异<span class="PUC03_e0"></span>唑', "sulfafurazole", "一种磺胺药。")
    entry = parse_record(1, "磺胺异", raw, None, stats)
    assert entry.expression == "磺胺异𫫇唑"
    assert entry.restored == "𫫇"
    plain = parse_record(2, "疖", record("疖", "furuncle", "皮肤病。"), None, stats)
    assert plain.restored == ""


# --- the built archives --------------------------------------------------------

def _rows(archive):
    with zipfile.ZipFile(archive) as zf:
        names = sorted((n for n in zf.namelist() if n.startswith("term_bank_")),
                       key=lambda n: int(n.removeprefix("term_bank_").removesuffix(".json")))
        return [row for name in names for row in json.loads(zf.read(name))]


def _built(slug: str):
    from pathlib import Path

    from medical_yomitan.dictionaries import DICTIONARIES

    archive = Path(__file__).resolve().parents[1] / "dist" / DICTIONARIES[slug].archive
    if not archive.exists():
        pytest.skip("dictionary not built")
    return _rows(archive)


@pytest.mark.parametrize("slug", ["xiandai-yixue-cidian", "xinbian-shiyong-yixue-cidian"])
def test_built_rows_of_an_entry_share_reading_and_everything_below_the_badges(slug):
    rows = _built(slug)
    by_sequence: dict[int, list] = {}
    for row in rows:
        by_sequence.setdefault(row[6], []).append(row)
    lookup_rows = 0
    for group in by_sequence.values():
        first = group[0]
        simplified = first[5][0]["content"]["content"][0]["content"][0]["content"][-1]["content"]
        assert first[0] == simplified and first[7] == ""
        shown = _box(first[5])
        for row in group[1:]:
            assert row[1] == first[1] and row[2:5] == first[2:5]
            assert row[5][0]["content"]["content"][1:] == first[5][0]["content"]["content"][1:]
            box = _box(row[5])
            if box != shown:
                lookup_rows += 1
                assert row[7] == ""            # an alternate key's rows only ever show the headword's forms
                assert box == [f"{shown[0]}、{row[0]}" if shown else row[0]]
        assert len({row[0] for row in group}) == len(group)
    assert lookup_rows > 100


def test_built_lookup_spelling_row(traditional):
    rows = [row for row in _built("xinbian-shiyong-yixue-cidian") if row[0] in ("里急后重", "裡急後重", "裏急後重")]
    assert [(row[0], _box(row[5])) for row in rows] == [
        ("里急后重", ["裡急後重"]), ("裡急後重", ["裡急後重"]), ("裏急後重", ["裡急後重、裏急後重"])]
    assert len({row[6] for row in rows}) == 1 and len({row[1] for row in rows}) == 1
