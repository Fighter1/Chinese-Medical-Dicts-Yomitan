"""Convert one CRFD-style MDX record into Yomitan structured content.

Every record has the same skeleton (a CNKI reference-work page scraped into
MDict):

    <link rel="stylesheet" ...><!--R2009010190011714-->
    <div class="detailDesc">
      <h3><span class="navi-search">HEADWORD</span><span></span><span></span><span>ENGLISH</span></h3>
      <p class="image_box">DEFINITION ...</p>          (may be split by nested <p>/<table>)
      <div class="descBox"><div class="descDiv">字数：…</div><div class="descDiv">知识来源：…</div></div>
      <div><div class="chartBox">…echarts canvas…</div></div>
      <div class="pageBox">上一条 / 下一条 links</div>
    </div>

The headword badge, English equivalent, definition and 知识来源 line are kept.
The word count, the related-term chart and the prev/next navigation are dropped.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any
from urllib.parse import quote as urlquote

from lxml import etree, html

from .models import ConversionStats, ParsedEntry
from .readings import reading_for
from .resources import ResourceCatalog


ENTRY_KIND = "crfd-entry"
FORBIDDEN = {
    "script", "style", "link", "iframe", "object", "embed", "form", "input", "button",
    "audio", "video", "canvas", "meta", "head", "title",
}
PASSTHROUGH = {"table", "thead", "tbody", "tfoot", "tr", "ol", "ul", "li", "ruby", "rt", "rp"}
KNOWN = PASSTHROUGH | {
    "a", "br", "img", "td", "th", "span", "div", "p", "sub", "sup", "small", "em", "b", "strong",
    "i", "u", "font", "center", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
}
# Private-use placeholders used by the source for characters missing from its
# font. Mappings were inferred from every context in which each code appears;
# see README "Private-use characters".
PUA_MAP = {
    0xE550: "\U0002C317",  # 𬌗 hé — 错𬌗, 𬌗与咬合, 咬𬌗关系
    0xE83C: "\U0002BAC7",  # 𫫇 è — 磺胺甲基异𫫇唑
    0xE0C8: "\U0002BAC7",  # 𫫇 è — 磺胺异𫫇唑, 异𫫇唑酰肼
    0xE7EE: "X̄",     # X̄ — 两样本均数 X̄1 与 X̄2
    0xE634: "痖",      # 疖 jiē — 多发性疖肿, 疮疡疖肿
    0xEE49: "茯",      # 茯 fú — 茯神
    0xE0D1: "²⁺",  # ²⁺ — Ca²⁺, Fe²⁺ (2价铁)
    0xE0D2: "³⁺",  # ³⁺ — Fe³⁺ (3价铁)
}
REFERENCE_RE = re.compile(r"^\s*(即|见|参见|详见|同)\s*([“「『\"]?)(.+?)([”」』\"]?)\s*([。．.]?)\s*$", re.S)
REFERENCE_MAX_LENGTH = 40


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value.replace("\x00", ""))).strip()


def restore_private_use(value: str) -> str:
    return value.translate(PUA_MAP)


def plain_key(headword: str) -> str:
    """MDX keys occasionally carry markup; keep only their text."""
    return normalize_text(restore_private_use(re.sub(r"<[^>]+>", "", headword)))


def _append(target: list[Any], value: Any) -> None:
    if value is None or value == "":
        return
    if isinstance(value, list):
        for item in value:
            _append(target, item)
    elif isinstance(value, str) and target and isinstance(target[-1], str):
        target[-1] += value
    else:
        target.append(value)


def _container(tag: str, content: Any, kind: str | None = None, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"tag": tag}
    if content not in (None, [], ""):
        node["content"] = content
    if kind:
        node["data"] = {"content": kind}
    node.update(extra)
    return node


def has_usable_content(value: Any) -> bool:
    if isinstance(value, str):
        return any(not ch.isspace() and ch != "　" for ch in value)
    if isinstance(value, list):
        return any(has_usable_content(item) for item in value)
    if isinstance(value, dict):
        if value.get("tag") == "img":
            return True
        return has_usable_content(value.get("content"))
    return False


def plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain_text(item) for item in value)
    if isinstance(value, dict):
        return plain_text(value.get("content"))
    return ""


def _classes(el: etree._Element) -> set[str]:
    return set((el.get("class") or "").split())


def _text_without_sup(el: etree._Element | None) -> str:
    if el is None:
        return ""
    clone = deepcopy(el)
    for sup in clone.xpath(".//sup"):
        sup.drop_tree()
    return normalize_text("".join(clone.itertext()))


def form_row(expression: str) -> dict[str, Any]:
    badge = _container("span", expression, "simplified-term")
    return _container("span", [_container("span", [badge], "terms-parent")], "first-row-parent")


class StructuredConverter:
    def __init__(self, resources: ResourceCatalog | None, stats: ConversionStats, headword: str):
        self.resources = resources
        self.stats = stats
        self.headword = headword

    def content(self, el: etree._Element) -> list[Any]:
        result: list[Any] = []
        if el.text:
            _append(result, self.text(el.text))
        for child in el:
            _append(result, self.convert(child))
            if child.tail:
                _append(result, self.text(child.tail))
        return result

    def text(self, value: str) -> str:
        value = unicodedata.normalize("NFC", value.replace("\x00", ""))
        for ch in value:
            if unicodedata.category(ch) == "Co":
                self.stats.record_private_use(f"U+{ord(ch):04X}", self.headword)
        return value

    def convert(self, el: etree._Element) -> Any:
        if not isinstance(el.tag, str):
            return ""  # comments and processing instructions
        tag = el.tag.casefold()
        if tag in FORBIDDEN:
            self.stats.counters[f"dropped_{tag}"] += 1
            return ""
        if tag == "br":
            return {"tag": "br"}
        if tag == "hr":
            return {"tag": "div", "style": {"borderStyle": "solid", "borderWidth": "0 0 1px 0", "margin": ".4em 0"}}
        if tag == "img":
            return self.image(el)
        content = self.content(el)
        if tag not in KNOWN:
            self.stats.unknown_tags[tag] += 1
            return content
        if tag == "a":
            href = el.get("href", "")
            if href.startswith("entry://"):
                target = normalize_text(restore_private_use(href.removeprefix("entry://")))
                target = target.split("#", 1)[0]
                if target:
                    self.stats.counters["cross_reference_links"] += 1
                    return {"tag": "a", "href": f"?query={urlquote(target)}", "content": content or target}
            return content
        if tag == "span":
            classes = _classes(el)
            if any(cls.upper().startswith("PUC") for cls in classes):
                return self.private_use_span(content)
            style = el.get("style", "").replace(" ", "")
            if "margin-left:2em" in style and not has_usable_content(content):
                return "　"
            return content
        if tag in {"sub", "sup"}:
            return _container(
                "span", content, tag,
                style={"verticalAlign": "super" if tag == "sup" else "sub", "fontSize": ".78em"},
            )
        if tag == "small":
            return _container("span", content, "small", style={"fontSize": ".85em"})
        if tag in {"em", "b", "strong"}:
            return _container("span", content, "emphasis", style={"fontWeight": "bold"})
        if tag == "i":
            return _container("span", content, "emphasis", style={"fontStyle": "italic"})
        if tag == "u":
            return _container("span", content, "underline", style={"textDecorationLine": "underline"})
        if tag == "font":
            return content
        if tag in {"p", "center", "div", "h1", "h2", "h3", "h4", "h5", "h6"}:
            if not has_usable_content(content):
                return ""
            if tag == "center" or (el.get("align") or "").casefold() == "center":
                return _container("div", content, "figure", style={"textAlign": "center"})
            return _container("div", content, "paragraph")
        if tag in {"td", "th"}:
            extra: dict[str, Any] = {}
            if (value := el.get("colspan")) and value.isdigit():
                extra["colSpan"] = int(value)
            if (value := el.get("rowspan")) and value.isdigit():
                extra["rowSpan"] = int(value)
            return _container(tag, content, **extra)
        if tag in PASSTHROUGH:
            return _container(tag, content)
        return content

    def private_use_span(self, content: list[Any]) -> Any:
        text = plain_text(content)
        if not text:
            return ""
        if all(unicodedata.category(ch) != "Co" for ch in text):
            # Already restored by PUA_MAP; mark it so readers know it was inferred.
            return _container("span", content, "pua-inferred", title="原文为缺字占位符，按上下文推定")
        codes = ", ".join(f"U+{ord(ch):04X}" for ch in text if unicodedata.category(ch) == "Co")
        self.stats.counters["unresolved_private_use_spans"] += 1
        return _container("span", "□", "private-use", title=f"原文缺字（私用区字符 {codes}），无法识别")

    def image(self, el: etree._Element) -> Any:
        src = el.get("src", "")
        if not src or ("://" in src and not src.startswith(("bres://", "file://"))):
            self.stats.counters["discarded_remote_images"] += 1
            return el.get("alt", "")
        if self.resources is None:
            raise FileNotFoundError(f"No resource catalog available for image {src}")
        resource = self.resources.resolve(src)
        node: dict[str, Any] = {"tag": "img", "path": resource.path, "alt": el.get("alt", "")}
        if resource.glyph:
            node.update({
                "width": resource.width, "height": resource.height, "sizeUnits": "px",
                "verticalAlign": "middle", "appearance": "monochrome", "collapsible": False,
                "data": {"content": "glyph-image"},
            })
            self.stats.counters["glyph_image_uses"] += 1
            return node
        width, height = resource.display_size
        inline = (el.get("align") or "").casefold() == "absmiddle" and resource.height <= 120
        node.update({
            "width": width, "height": height, "sizeUnits": "px", "background": True,
            "collapsible": True, "collapsed": False,
            "verticalAlign": "middle" if inline else "baseline",
            "data": {"content": "inline-image" if inline else "entry-image"},
        })
        if resource.monochrome:
            node["appearance"] = "monochrome"
            node["background"] = False
        self.stats.counters["figure_image_uses"] += 1
        return node


def _detect_reference(body: list[Any]) -> tuple[str, str, str] | None:
    """Recognize a whole-entry cross reference such as 即猫叫综合征。 or 见狭窄性腱鞘炎。"""
    if any(isinstance(node, dict) and node.get("tag") in {"img", "table", "a"} for node in _walk(body)):
        return None
    text = normalize_text(plain_text(body))
    if not text or len(text) > REFERENCE_MAX_LENGTH:
        return None
    match = REFERENCE_RE.match(text)
    if not match:
        return None
    keyword, open_quote, target, close_quote, period = match.groups()
    target = target.strip()
    if not target or "，" in target or "、" in target or "。" in target:
        return None
    return keyword + open_quote, target, close_quote + period


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        yield from _walk(value.get("content"))
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def parse_record(
    ordinal: int, headword: str, raw: str, resources: ResourceCatalog | None, stats: ConversionStats,
) -> ParsedEntry | None:
    """Parse one MDX record; ``None`` means the record is an empty section marker."""
    raw = restore_private_use(raw.replace("\x00", ""))
    key = plain_key(headword)
    converter = StructuredConverter(resources, stats, key)
    try:
        root = html.fragment_fromstring(raw, create_parent="div")
    except (etree.ParserError, ValueError) as exc:
        stats.warning(f"Malformed HTML for {headword}: {exc}")
        text = normalize_text(re.sub(r"<[^>]+>", "", raw))
        return ParsedEntry(ordinal, key, reading_for(key), key, body=[_container("div", text, "paragraph")])

    detail = root.find(".//div[@class='detailDesc']")
    if detail is None:
        stats.counters["generic_records"] += 1
        content = converter.content(root)
        if not has_usable_content(content):
            content = [normalize_text("".join(root.itertext())) or "（无可显示释义）"]
        return ParsedEntry(ordinal, key, reading_for(key), key, body=[_container("div", content, "paragraph")])

    heading = detail.find("h3")
    headword_span = heading.find(".//span[@class='navi-search']") if heading is not None else None
    expression = _text_without_sup(headword_span) or key
    header: list[Any] = []
    if headword_span is not None and headword_span.xpath(".//sub | .//sup"):
        header.append(_container("span", converter.content(headword_span), "headword-full"))
    if heading is not None:
        for span in heading.findall("span"):
            if span is headword_span:
                continue
            english = converter.content(span)
            if has_usable_content(english):
                header.append(_container("span", english, "english", lang="en"))
                stats.counters["english_equivalents"] += 1

    body: list[Any] = []
    source = ""
    started = heading is None
    for child in detail:
        if not started:
            if child is heading:
                started = True
                if child.tail:
                    _append(body, converter.text(child.tail))
            continue
        if isinstance(child.tag, str) and child.tag.casefold() == "div" and "descBox" in _classes(child):
            for desc in child.findall(".//div[@class='descDiv']"):
                label = normalize_text(desc.text or "")
                value = normalize_text("".join(desc.itertext()).replace(desc.text or "", "", 1))
                if label.startswith("知识来源") and value:
                    source = value
            break
        _append(body, converter.convert(child))
        if child.tail:
            _append(body, converter.text(child.tail))
    body = _trim(body)
    if not has_usable_content(body):
        if not header:
            # Section markers of the source (single letters, digits, pinyin
            # syllables) carry neither a definition nor an English equivalent.
            stats.counters["excluded_empty_records"] += 1
            return None
        body = ["（无可显示释义）"]
        stats.counters["empty_glossaries"] += 1

    entry = ParsedEntry(ordinal, expression, reading_for(expression), key, header=header, body=body, source=source)
    if key and key != expression:
        entry.alternate_terms.append(key)
    if reference := _detect_reference(body):
        entry.reference_prefix, entry.reference_target, entry.reference_suffix = reference
    if not entry.reading:
        stats.counters["missing_readings"] += 1
        stats.sample(stats.missing_reading_samples, expression)
    return entry


def _trim(body: list[Any]) -> list[Any]:
    """Drop whitespace-only text at the edges and unwrap a lone paragraph."""
    while body and isinstance(body[0], str) and not body[0].strip():
        body.pop(0)
    while body and isinstance(body[-1], str) and not body[-1].strip():
        body.pop()
    if body and isinstance(body[0], str):
        body[0] = body[0].lstrip()
    if body and isinstance(body[-1], str):
        body[-1] = body[-1].rstrip()
    if len(body) == 1 and isinstance(body[0], dict) and body[0].get("data", {}).get("content") == "paragraph":
        inner = body[0].get("content", [])
        return inner if isinstance(inner, list) else [inner]
    return body


def reference_link(entry: ParsedEntry) -> list[Any]:
    link = {"tag": "a", "href": f"?query={urlquote(entry.reference_target)}", "content": entry.reference_target}
    result: list[Any] = []
    for part in (entry.reference_prefix, link, entry.reference_suffix):
        _append(result, part)
    return result


def render_glossary(entry: ParsedEntry, body: list[Any], embedded: list[tuple[ParsedEntry, list[Any]]]) -> list[dict[str, Any]]:
    content: list[Any] = [form_row(entry.expression)]
    if entry.header:
        content.append(_container("div", deepcopy(entry.header), "header"))
    content.append(_container("div", deepcopy(body), "definition"))
    for target, target_body in embedded:
        block: list[Any] = [_container("div", ["→ ", target.expression], "referenced-label")]
        if target.header:
            block.append(_container("div", deepcopy(target.header), "header"))
        block.append(_container("div", deepcopy(target_body), "definition"))
        if target.source:
            block.append(_container("div", "知识来源：" + target.source, "source"))
        content.append(_container("div", block, "referenced-definition"))
    if entry.source:
        content.append(_container("div", "知识来源：" + entry.source, "source"))
    return [{"type": "structured-content", "content": _container("div", content, ENTRY_KIND, lang="zh-Hans")}]
