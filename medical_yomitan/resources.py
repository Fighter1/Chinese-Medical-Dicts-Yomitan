from __future__ import annotations

import hashlib
import io
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from .models import ConversionStats
from .source import iter_mdd_records


SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
RASTERIZE = {".bmp", ".tif", ".tiff"}
GLYPH_MAX_SIZE = 48
FIGURE_MAX_WIDTH = 480


def _is_glyph(suffix: str, size: tuple[int, int]) -> bool:
    width, height = size
    return suffix == ".bmp" or (width <= GLYPH_MAX_SIZE and height <= GLYPH_MAX_SIZE)


def normalize_resource_path(value: str) -> str:
    value = unquote(value.strip()).replace("\\", "/")
    if "://" in value:
        value = urlsplit(value).path
    value = posixpath.normpath("/" + value).lstrip("/")
    if value.startswith("../") or value == "..":
        raise ValueError(f"Unsafe resource path: {value}")
    return value.casefold()


@dataclass(frozen=True)
class Resource:
    path: str
    width: int
    height: int
    glyph: bool
    monochrome: bool  # has an alpha channel suitable for Yomitan's mask-based monochrome rendering

    @property
    def display_size(self) -> tuple[int, int]:
        if self.width <= FIGURE_MAX_WIDTH:
            return self.width, self.height
        scale = FIGURE_MAX_WIDTH / self.width
        return FIGURE_MAX_WIDTH, max(1, round(self.height * scale))


@dataclass
class ResourceCatalog:
    staging: Path
    stats: ConversionStats
    source_to_resource: dict[str, Resource] = field(default_factory=dict)
    output_to_file: dict[str, Path] = field(default_factory=dict)
    used_outputs: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, mdds: tuple[Path, ...], staging: Path, stats: ConversionStats) -> "ResourceCatalog":
        catalog = cls(staging=staging, stats=stats)
        staging.mkdir(parents=True, exist_ok=True)
        for mdd in mdds:
            for source_name, raw in iter_mdd_records(mdd):
                catalog._add(source_name, raw)
        return catalog

    def _add(self, source_name: str, raw: bytes) -> None:
        normalized = normalize_resource_path(source_name)
        suffix = Path(normalized).suffix.lower()
        self.stats.resource_extensions[suffix or "<none>"] += 1
        self.stats.counters["mdd_resources"] += 1
        if suffix not in SUPPORTED | RASTERIZE:
            self.stats.counters["discarded_non_image_resources"] += 1
            return
        try:
            converted, out_suffix, size, monochrome = self._normalize_image(raw, suffix)
        except Exception as exc:  # noqa: BLE001 - report and continue
            self.stats.warning(f"Unreadable image {source_name}: {exc}")
            return
        digest = hashlib.sha256(converted).hexdigest()
        output = f"media/{digest[:24]}{out_suffix}"
        target = self.staging / f"{digest}{out_suffix}"
        if output not in self.output_to_file:
            target.write_bytes(converted)
            self.output_to_file[output] = target
        else:
            self.stats.counters["deduplicated_resources"] += 1
        width, height = size
        glyph = _is_glyph(suffix, size)
        self.source_to_resource[normalized] = Resource(output, width, height, glyph, monochrome)
        self.stats.counters["image_resources"] += 1
        self.stats.counters["glyph_images" if glyph else "figure_images"] += 1
        if monochrome:
            self.stats.counters["monochrome_images"] += 1

    @staticmethod
    def _normalize_image(raw: bytes, suffix: str) -> tuple[bytes, str, tuple[int, int], bool]:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            size = image.size
            if _is_glyph(suffix, size) or suffix == ".gif":
                # Glyph bitmaps and formula GIFs are black line art on white. Yomitan's
                # monochrome appearance masks the current text colour with the image's
                # alpha, so give them an alpha channel derived from luminance.
                flattened = Image.new("RGBA", size, (255, 255, 255, 255))
                flattened.alpha_composite(image.convert("RGBA"))  # honour existing transparency
                luminance = flattened.convert("L")
                alpha = luminance.point(lambda value: 255 - value)
                rgba = Image.new("RGBA", size, (0, 0, 0, 255))
                rgba.putalpha(alpha)
                out = io.BytesIO()
                rgba.save(out, format="PNG", optimize=True)
                return out.getvalue(), ".png", size, True
            if suffix in SUPPORTED:
                return raw, ".jpg" if suffix == ".jpeg" else suffix, size, False
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue(), ".png", size, False

    def resolve(self, source: str) -> Resource:
        normalized = normalize_resource_path(source)
        resource = self.source_to_resource.get(normalized)
        if resource is None:
            self.stats.counters["missing_resources"] += 1
            raise FileNotFoundError(f"Definition references missing image: {source}")
        self.used_outputs.add(resource.path)
        return resource
