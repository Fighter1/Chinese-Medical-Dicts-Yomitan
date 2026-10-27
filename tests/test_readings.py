from medical_yomitan.readings import is_clean_reading, reading_for


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


def test_restored_rare_characters_have_readings():
    assert reading_for("𬌗与咬合") == "hé yǔ yǎo hé"


def test_clean_reading_rules():
    assert is_clean_reading("")
    assert is_clean_reading("Ⅰ xíng táng niào bìng")
    assert is_clean_reading("X̄ zhí")
    assert not is_clean_reading("血 xuè")
    assert not is_clean_reading("hé")
