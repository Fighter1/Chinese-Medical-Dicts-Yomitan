"""Stable identities for each supported source dictionary."""
from __future__ import annotations

from dataclasses import dataclass


REPO_URL = "https://github.com/Fighter1/Chinese-Medical-Dicts-Yomitan"
UPDATE_BASE = REPO_URL + "/releases/latest/download/"


@dataclass(frozen=True)
class Dictionary:
    slug: str
    title: str
    short_title: str
    archive: str
    index: str
    report: str
    record_prefix: str
    author: str
    description: str

    @property
    def index_url(self) -> str:
        return UPDATE_BASE + self.index

    @property
    def download_url(self) -> str:
        return UPDATE_BASE + self.archive


DICTIONARIES: dict[str, Dictionary] = {
    "xiandai-yixue-cidian": Dictionary(
        slug="xiandai-yixue-cidian",
        title="现代医学辞典",
        short_title="现代医学辞典（1990）",
        archive="xiandai-yixue-cidian-yomitan.zip",
        index="index-xiandai-yixue-cidian.json",
        report="xiandai-yixue-cidian-conversion-report.json",
        record_prefix="R200901019",
        author="刘福岭 主编；栾铭箴、戚仁铎、王均乐 等副主编（山东科学技术出版社，1990）",
        description=(
            "《现代医学辞典》（刘福岭主编，山东科学技术出版社，1990）的结构化 Yomitan 转换。"
            "保留词头、英文对照、释义、公式与插图、表格、交叉引用和知识来源页码；"
            "拼音读音由 pypinyin 自动生成。"
        ),
    ),
    "xinbian-shiyong-yixue-cidian": Dictionary(
        slug="xinbian-shiyong-yixue-cidian",
        title="新编实用医学词典",
        short_title="新编实用医学词典（1994）",
        archive="xinbian-shiyong-yixue-cidian-yomitan.zip",
        index="index-xinbian-shiyong-yixue-cidian.json",
        report="xinbian-shiyong-yixue-cidian-conversion-report.json",
        record_prefix="R200908051",
        author="张俊武 主编；刘莉、张雪莲、戴巍 等副主编（北京医科大学中国协和医科大学联合出版社，1994）",
        description=(
            "《新编实用医学词典》（张俊武主编，北京医科大学中国协和医科大学联合出版社，1994）"
            "的结构化 Yomitan 转换。保留词头、英文对照、释义、公式与插图、交叉引用和知识来源；"
            "拼音读音由 pypinyin 自动生成。"
        ),
    ),
}


def get_dictionary(slug: str) -> Dictionary:
    if slug not in DICTIONARIES:
        raise ValueError(f"Unknown dictionary {slug!r}; expected one of {', '.join(DICTIONARIES)}")
    return DICTIONARIES[slug]


def detect_dictionary(sample_records: list[str]) -> Dictionary | None:
    """Identify the dictionary from the record-id comment each entry carries."""
    for raw in sample_records:
        for dictionary in DICTIONARIES.values():
            if f"<!--{dictionary.record_prefix}" in raw:
                return dictionary
    return None
