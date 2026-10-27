from medical_yomitan.content import parse_record, plain_key, plain_text, reference_link, render_glossary
from medical_yomitan.models import ConversionStats


def record(headword: str, english: str, body: str, source: str = "某书.第3页") -> str:
    return (
        '<link rel="stylesheet" href="TongYong.css"/><!--R2009010190000001-->'
        '<div class="detailDesc"><h3>'
        f'<span class="navi-search">{headword}</span><span></span><span></span><span>{english}</span>'
        f'</h3><p class="image_box">{body}</p>'
        '<div class="descBox"><div class="descDiv"> 字数： <span>9</span></div>'
        f'<div class="descDiv"> 知识来源： <span>{source}</span></div></div>'
        '<div><div class="chartBox"><canvas></canvas></div></div>'
        '<div class="pageBox"><a class="prevBtn">上一条：<a href="entry://x"><em>x</em></a></a></div></div>'
    )


def test_basic_entry_keeps_headword_english_body_and_source():
    stats = ConversionStats()
    entry = parse_record(1, "菌素", record("菌素", "bacterin", "亦称菌苗。"), None, stats)
    assert entry is not None
    assert entry.expression == "菌素"
    assert entry.reading == "jūn sù"
    assert plain_text(entry.header) == "bacterin"
    assert entry.body == ["亦称菌苗。"]
    assert entry.source == "某书.第3页"
    glossary = render_glossary(entry, entry.body, [])
    text = plain_text(glossary[0]["content"])
    assert "上一条" not in text and "字数" not in text
    assert "知识来源：某书.第3页" in text
    assert glossary[0]["content"]["lang"] == "zh-Hans"


def test_sup_is_dropped_from_expression_but_kept_in_header():
    stats = ConversionStats()
    entry = parse_record(2, "5P综合征", record("5P<sup>-</sup>综合征", "5 P<sup>-</sup> syndrome", "即猫叫综合征"), None, stats)
    assert entry.expression == "5P综合征"
    assert entry.header[0]["data"]["content"] == "headword-full"
    assert entry.reference_target == "猫叫综合征"
    assert entry.reference_prefix == "即" and entry.reference_suffix == ""
    assert reference_link(entry) == ["即", {"tag": "a", "href": "?query=%E7%8C%AB%E5%8F%AB%E7%BB%BC%E5%90%88%E5%BE%81", "content": "猫叫综合征"}]


def test_sub_in_headword_creates_variant_for_mdx_key():
    stats = ConversionStats()
    entry = parse_record(3, "GM神经节苷脂病", record("GM<sub>1</sub>神经节苷脂病", "", "释义。"), None, stats)
    assert entry.expression == "GM1神经节苷脂病"
    assert entry.alternate_terms == ["GM神经节苷脂病"]


def test_links_tables_and_nested_paragraphs():
    body = (
        '见“<a href="entry://生长发育">生长发育</a>”：<p align="center"></p>'
        '<table class="viewtb"><tbody><tr><td class="viewtd">a</td><td colspan="2">b</td></tr></tbody></table>'
        "<p></p>尾注。"
    )
    stats = ConversionStats()
    entry = parse_record(4, "x", record("x", "", body), None, stats)
    nodes = entry.body
    assert any(isinstance(n, dict) and n.get("tag") == "table" for n in nodes)
    link = next(n for n in nodes[0]["content"] if isinstance(n, dict) and n.get("tag") == "a")
    assert link["href"].startswith("?query=")
    assert entry.reference_target == ""  # tables disqualify whole-entry references
    assert plain_text(nodes).endswith("尾注。")
    td = nodes[1]["content"][0]["content"][0]["content"][1]
    assert td["colSpan"] == 2


def test_private_use_characters():
    stats = ConversionStats()
    raw = record("错<span class=\"PUC01_E5\"></span>", "", "咬<span class=\"PUC01_E5\"></span>与<span class=\"PUC09_ff\"></span>")
    entry = parse_record(5, '错<span class="PUC01_E5"></span>', raw, None, stats)
    assert entry.expression == "错𬌗"
    assert entry.key == "错𬌗"
    assert entry.reading == "cuò hé"
    kinds = [n["data"]["content"] for n in entry.body if isinstance(n, dict)]
    assert kinds == ["pua-inferred", "private-use"]
    assert stats.counters["unresolved_private_use_spans"] == 1
    assert "U+F8FF" in stats.private_use


def test_empty_section_marker_is_excluded():
    stats = ConversionStats()
    assert parse_record(6, "biàn", record("biàn", "", ""), None, stats) is None
    assert stats.counters["excluded_empty_records"] == 1


def test_plain_key_strips_markup():
    assert plain_key('<span class="PUC01_E5"></span>与咬合') == "𬌗与咬合"
