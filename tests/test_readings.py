import gzip

import pytest

from medical_yomitan import cedict
from medical_yomitan.readings import (
    CEDICT, CEDICT_WORD, OVERRIDE, PYPINYIN, Readings, assemble, cedict_syllables, default_readings,
    is_clean_reading, load_overrides, reading_for, split_runs, syllable_to_marks,
)


# --- format ---------------------------------------------------------------------

def test_numbered_syllables_become_tone_marks():
    assert [syllable_to_marks(t) for t in ("zhao2", "lu:4", "de5", "Qu1", "nu:3", "xue4", "r5", "ng2")] == [
        "zháo", "lǜ", "de", "qū", "nǚ", "xuè", "r", "ńg"]
    assert syllable_to_marks("T") is None and syllable_to_marks(",") is None and syllable_to_marks("xx5") is None
    assert cedict_syllables("T xi4 bao1") == ["xì", "bāo"]


def test_runs_and_assembly_keep_other_characters_in_place():
    assert split_runs("17-α-羟化酶") == [(False, "17-α-"), (True, "羟化酶")]
    assert assemble("17-α-羟化酶", ["qiǎng", "huà", "méi"]) == "17-α- qiǎng huà méi"
    assert assemble("“全或无”现象", ["quán", "huò", "wú", "xiàn", "xiàng"]) == "quán huò wú xiàn xiàng"


def test_han_words_get_tone_marked_pinyin():
    assert reading_for("血红蛋白") == "xuè hóng dàn bái"
    assert reading_for("疟疾") == "nüè jí"


def test_non_han_runs_are_kept_in_place():
    assert reading_for("A型人格") == "A xíng rén gé"
    assert reading_for("17-α-羟化酶缺失综合征") == "17-α- qiǎng huà méi quē shī zōng hé zhēng"


def test_quotes_and_dots_are_stripped():
    assert reading_for("“全或无”现象") == "quán huò wú xiàn xiàng"
    assert reading_for("奥斯汀 · 弗林特杂音") == "ào sī tīng fú lín tè zá yīn"


def test_no_han_means_no_reading():
    assert reading_for("APUD") == ""
    assert reading_for("Å") == ""
    assert default_readings()("APUD").source == "none"


def test_restored_rare_characters_have_readings():
    assert reading_for("𬌗与咬合") == "hé yǔ yǎo hé"


def test_clean_reading_rules():
    assert is_clean_reading("")
    assert is_clean_reading("Ⅰ xíng táng niào bìng")
    assert is_clean_reading("X̄ zhí")
    assert not is_clean_reading("血 xuè")
    assert not is_clean_reading("hé")


# --- sources, on a small table of their own ---------------------------------------

EXPORT = """# CC-CEDICT
#! date=2026-01-02T03:04:05Z
子宮 子宫 [zi3 gong1] /uterus/
心率 心率 [xin1 lu:4] /heart rate/
生長 生长 [sheng1 zhang3] /to grow/
分子 分子 [fen1 zi3] /molecule/
分子 分子 [fen4 zi3] /member of a group/
單 单 [Shan4] /surname Shan/
單 单 [dan1] /single/
脊 脊 [ji3] /spine/
咽 咽 [yan1] /pharynx/
咽 咽 [yan4] /to swallow/
X光 X光 [X guang1] /X-ray/
一點兒 一点儿 [yi1 dian3 r5] /a bit/
帕金森 帕金森 [Pa4 jin1 sen1] /Parkinson/
ＡＢＣ ABC [A B C] /letters/
"""


@pytest.fixture()
def readings(tmp_path, monkeypatch):
    monkeypatch.setattr(cedict, "MIN_ENTRIES", 5)
    table = tmp_path / "cedict.tsv"
    table.write_text(cedict.derive_table(EXPORT.encode("utf-8")), encoding="utf-8", newline="\n")
    overrides = tmp_path / "overrides.tsv"
    overrides.write_text(
        "# comment\n\n重吸收\tchóng xī shōu\n咽\tyān\n柏—查综合征\tbó chá zōng hé zhēng\n", encoding="utf-8")
    return Readings(table, overrides)


def test_derived_table(tmp_path, monkeypatch):
    monkeypatch.setattr(cedict, "MIN_ENTRIES", 5)
    text = cedict.derive_table(gzip.compress(EXPORT.encode("utf-8")))
    assert "# export-date: 2026-01-02T03:04:05Z" in text
    assert "分子\tfen1 zi3\tfen4 zi3\n" in text
    assert "单\tShan4\tdan1\n" in text
    assert "ABC" not in text                                   # no Han character: not kept
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    assert lines == sorted(lines)
    path = tmp_path / "t.tsv"
    path.write_text(text, encoding="utf-8", newline="\n")
    table = cedict.load_table(path)
    assert table.export_date == "2026-01-02T03:04:05Z" and table.export_entries == 14
    assert table.readings["心率"] == ("xin1 lu:4",)


def test_an_incomplete_export_is_refused():
    with pytest.raises(ValueError, match="not a complete"):
        cedict.derive_table(EXPORT.encode("utf-8"))


def test_headword_listed_by_cedict(readings):
    read = readings("子宫")
    assert (read.reading, read.source) == ("zǐ gōng", CEDICT)
    assert readings("心率").reading == "xīn lǜ"
    # a proper noun's capitals are not carried into the reading
    assert readings("帕金森").reading == "pà jīn sēn"


def test_listed_headword_with_latin_keeps_its_own_run(readings):
    assert (readings("X光").reading, readings("X光").source) == ("X guāng", CEDICT)


def test_lower_case_reading_comes_before_the_surname(readings):
    assert readings.listed["单"] == [["dān"], ["shàn"]]


def test_erhua_entries_are_not_used(readings):
    assert "一点儿" not in readings.listed


def test_cedict_words_inside_a_longer_headword(readings):
    read = readings("子宫生长")
    assert read.reading == "zǐ gōng shēng zhǎng"
    assert read.source == "cedict-words"
    assert [how for _, _, how in read.characters] == [CEDICT_WORD] * 4


def test_run_between_other_characters_is_looked_up_on_its_own(readings):
    assert readings("β-子宫").reading == "β- zǐ gōng"


def test_character_with_one_cedict_reading_replaces_pypinyin(readings):
    # pypinyin alone reads 脊 as jí
    assert readings("脊突").reading.split()[0] == "jǐ"


def test_override_names_a_headword_and_applies_inside_longer_ones(readings):
    assert (readings("重吸收").reading, readings("重吸收").source) == ("chóng xī shōu", OVERRIDE)
    read = readings("肾重吸收")
    assert read.reading == "shèn chóng xī shōu"
    assert [how for _, _, how in read.characters] == [PYPINYIN, OVERRIDE, OVERRIDE, OVERRIDE]


def test_one_character_override_only_where_no_word_covers_it(readings):
    assert readings("咽").reading == "yān"                      # the headword itself
    assert readings("咽囊").reading.split()[0] == "yān"         # pypinyin alone says yàn
    assert readings("吞咽").reading == "tūn yàn"                # pypinyin's own phrase keeps its reading


def test_override_of_a_headword_with_punctuation(readings):
    assert readings("柏—查综合征").reading == "bó — chá zōng hé zhēng"


def test_longest_leftmost_words_win(tmp_path, monkeypatch):
    monkeypatch.setattr(cedict, "MIN_ENTRIES", 1)
    export = "#! date=2026-01-02T03:04:05Z\n系帶 系带 [xi4 dai4] /frenulum/\n帶過 带过 [dai4 guo4] /to pass over/\n"
    table = tmp_path / "cedict.tsv"
    table.write_text(cedict.derive_table(export.encode("utf-8")), encoding="utf-8", newline="\n")
    readings = Readings(table, None)
    assert [how for _, _, how in readings("舌系带过短").characters][1:3] == [CEDICT_WORD, CEDICT_WORD]
    assert readings("舌系带过短").reading == "shé xì dài guò duǎn"


@pytest.mark.parametrize("line", ["重吸收 chóng xī shōu", "重吸收\tchóng xī", "重吸收\t重 xī shōu", "a\tb\tc"])
def test_malformed_override_lines_are_refused(tmp_path, line):
    path = tmp_path / "o.tsv"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_overrides(path)


def test_duplicate_override_is_refused(tmp_path):
    path = tmp_path / "o.tsv"
    path.write_text("咽\tyān\n咽\tyàn\n", encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        load_overrides(path)


# --- the pinned table and the shipped overrides -----------------------------------

def test_pinned_table_is_complete_and_dated():
    table = cedict.load_table()
    assert table.export_date.startswith("20") and table.export_entries >= cedict.MIN_ENTRIES
    assert table.readings["子宫"] == ("zi3 gong1",)


def test_shipped_overrides_load_and_are_used():
    overrides = load_overrides()
    assert overrides["重吸收"] == "chóng xī shōu"
    assert reading_for("肾小管重吸收作用") == "shèn xiǎo guǎn chóng xī shōu zuò yòng"


@pytest.mark.parametrize("headword, reading", [
    ("子宫", "zǐ gōng"),                    # pypinyin alone: zi gōng
    ("脊髓损伤", "jǐ suǐ sǔn shāng"),          # jí
    ("肋间神经", "lèi jiān shén jīng"),        # lē
    ("拇长屈肌", "mǔ cháng qū jī"),           # zhǎng
    ("生长激素", "shēng zhǎng jī sù"),
    ("咽后脓肿", "yān hòu nóng zhǒng"),        # yàn
    ("寰椎", "huán zhuī"),                  # chuí
    ("变应原", "biàn yìng yuán"),            # yīng
    ("分子毒理学", "fēn zǐ dú lǐ xué"),        # fèn zǐ
    ("大汗腺", "dà hàn xiàn"),               # dà hán
    ("舌系带过短", "shé xì dài guò duǎn"),      # jì
    ("恶寒战栗", "wù hán zhàn lì"),
    ("心率", "xīn lǜ"),
    ("粘膜", "nián mó"),
    ("肠粘连", "cháng zhān lián"),
    ("脑干性眼震颤", "nǎo gàn xìng yǎn zhèn chàn"),
    ("干性啰音", "gān xìng luō yīn"),
])
def test_medical_readings(headword, reading):
    assert reading_for(headword) == reading
