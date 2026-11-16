"""The same inputs give the same bytes on every machine.

Two things once differed between a Windows build and the Linux build of a
release: JSON files written with the platform's line ends, and PNG images
compressed by the zlib that Pillow's wheel bundles. The pinned hashes below
fail on a machine whose output would differ, before a build is compared.
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from medical_yomitan.dictionaries import DICTIONARIES
from medical_yomitan.package import write_json
from medical_yomitan.resources import ResourceCatalog, encode_png

CARRIAGE_RETURN = bytes([13])


def sample(mode: str) -> Image.Image:
    width, height = 24, 16
    image = Image.new(mode, (width, height))
    bands = len(image.getbands())
    image.putdata([
        tuple((x * 11 + y * 7 + band * 53) % 256 for band in range(bands)) if bands > 1 else (x * 11 + y * 7) % 256
        for y in range(height) for x in range(width)
    ])
    return image


@pytest.mark.parametrize("mode, sha256", [
    ("RGBA", "2a60d53d9133958c07ca9048a13c88195a879bfaa27c2dbdba1fa35b845105b9"),
    ("L", "2c3ff4fc2f85007ba4175f99b0fd83cc550e4ca859eb14c9199203eefe9982cd"),
    ("RGB", "a9cf40899ac2372a6234eb07c22ce83ac3047226127c6ab60fe059d75632d92b"),
    ("LA", "8d45f9e2342220e30122aca9bc22f515cb6bbd833e0c2e88af75aaa11bd09a92"),
])
def test_png_bytes_are_the_same_on_every_machine(mode, sha256):
    assert hashlib.sha256(encode_png(sample(mode))).hexdigest() == sha256


@pytest.mark.parametrize("mode", ["RGBA", "L", "RGB", "LA"])
def test_png_decodes_to_the_same_pixels(mode):
    image = sample(mode)
    decoded = Image.open(io.BytesIO(encode_png(image)))
    decoded.load()
    assert (decoded.mode, decoded.size) == (mode, image.size)
    assert decoded.tobytes() == image.tobytes()


def test_palette_images_are_written_as_colour():
    palette = sample("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
    decoded = Image.open(io.BytesIO(encode_png(palette)))
    assert decoded.mode == "RGB" and decoded.tobytes() == palette.convert("RGB").tobytes()
    palette.info["transparency"] = 0
    assert Image.open(io.BytesIO(encode_png(palette))).mode == "RGBA"


def test_a_glyph_bitmap_becomes_a_monochrome_png_with_alpha():
    glyph = Image.new("L", (4, 3), 255)
    glyph.putpixel((1, 1), 0)                       # one black pixel on white
    raw = io.BytesIO()
    glyph.save(raw, format="BMP")
    converted, suffix, size, monochrome = ResourceCatalog._normalize_image(raw.getvalue(), ".bmp")
    assert (suffix, size, monochrome) == (".png", (4, 3), True)
    decoded = Image.open(io.BytesIO(converted))
    assert decoded.mode == "RGBA"
    assert decoded.getpixel((1, 1)) == (0, 0, 0, 255) and decoded.getpixel((0, 0)) == (0, 0, 0, 0)
    # twice the same bytes
    assert ResourceCatalog._normalize_image(raw.getvalue(), ".bmp")[0] == converted


def test_figures_in_a_format_a_browser_reads_are_packaged_untouched():
    figure = io.BytesIO()
    sample("RGB").resize((240, 160)).save(figure, format="PNG")
    converted, suffix, _size, monochrome = ResourceCatalog._normalize_image(figure.getvalue(), ".png")
    assert converted == figure.getvalue() and suffix == ".png" and monochrome is False


def test_json_is_written_with_lf(tmp_path):
    path = tmp_path / "index.json"
    write_json(path, {"title": "词典", "nested": {"a": 1}})
    data = path.read_bytes()
    assert CARRIAGE_RETURN not in data and data.count(b"\n") > 3
    assert json.loads(data) == {"title": "词典", "nested": {"a": 1}}


@pytest.mark.parametrize("slug", sorted(DICTIONARIES))
def test_built_archive_has_no_platform_line_ends(slug):
    archive = Path(__file__).resolve().parents[1] / "dist" / DICTIONARIES[slug].archive
    if not archive.exists():
        pytest.skip("dictionary not built")
    with zipfile.ZipFile(archive) as zf:
        text_members = [name for name in zf.namelist() if name.endswith((".json", ".css"))]
        assert "index.json" in text_members and "tag_bank_1.json" in text_members and "styles.css" in text_members
        for name in text_members:
            assert CARRIAGE_RETURN not in zf.read(name), name
