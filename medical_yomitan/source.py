from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Iterator

from mdict_utils.base.readmdict import MDD, MDX

from .models import InputSet


def discover_input(root: Path) -> InputSet:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    mdx = sorted(p for p in root.glob("*.mdx") if p.is_file())
    if len(mdx) != 1:
        raise ValueError(f"Expected exactly one MDX in {root}; found {len(mdx)}")
    mdds = tuple(sorted(p for p in root.glob("*.mdd") if p.is_file()))
    return InputSet(mdx=mdx[0], mdds=mdds)


def sha256_file(path: Path, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def mdx_header(path: Path) -> dict[str, str]:
    mdx = MDX(str(path), "", False, None)
    result: dict[str, str] = {}
    for key, value in mdx.header.items():
        name = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
        result[name] = text
    return result


def input_inventory(inputs: InputSet) -> dict:
    files = [inputs.mdx, *inputs.mdds]
    header = mdx_header(inputs.mdx)
    return {
        "files": [{"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)} for p in files],
        "mdx_header": {k: v for k, v in header.items() if k not in {"Description", "Title", "StyleSheet"}},
    }


def iter_mdx_records(path: Path) -> Iterator[tuple[int, str, str]]:
    mdx = MDX(str(path), "", False, None)
    for ordinal, (key, value) in enumerate(mdx.items(), start=1):
        headword = unicodedata.normalize("NFC", key.decode("utf-8")).replace("\x00", "")
        raw = value.decode("utf-8", "strict").replace("\x00", "")
        yield ordinal, headword, raw


def iter_mdd_records(path: Path) -> Iterator[tuple[str, bytes]]:
    mdd = MDD(str(path), None)
    for key, value in mdd.items():
        yield key.decode("utf-8"), value
