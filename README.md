# Chinese Medical Dictionaries → Yomitan

Converter for two CNKI reference-work (CRFD) medical dictionaries distributed as
MDict `.mdx`/`.mdd` files, producing Yomitan format-3 structured-content
dictionaries in the style of
[caocaochan/hydcd-yomitan](https://github.com/caocaochan/hydcd-yomitan):
headword badge row, header block, `data-sc-content` kinds styled by a packaged
`styles.css`, `lang="zh-Hans"` glossaries, deterministic ZIPs, JSON conversion
reports and update metadata (`isUpdatable` / `indexUrl` / `downloadUrl`).

| Dictionary | Source | Terms | Images | ZIP |
| --- | --- | ---: | ---: | --- |
| 现代医学辞典 | 刘福岭 主编，山东科学技术出版社，1990 | 10,972 | 185 | `xiandai-yixue-cidian-yomitan.zip` |
| 新编实用医学词典 | 张俊武 主编，北京医科大学中国协和医科大学联合出版社，1994 | 16,695 | 32 | `xinbian-shiyong-yixue-cidian-yomitan.zip` |

Update endpoints embedded in each ZIP point at this repository's
`releases/latest/download/` (`index-<slug>.json`, `<slug>-yomitan.zip`), so a
GitHub release carrying those assets lets Yomitan check for and apply updates.

## Input

Put one `.mdx` and its `.mdd` in a directory (the `input/` tree is
git-ignored). The dictionary identity is detected from the record-id comment
inside each entry (`R200901019…` / `R200908051…`), or pass `--dictionary`.

```
input/xiandai-yixue-cidian/现代医学辞典[1990][刘福岭][山东科学技术出版社].mdx
input/xiandai-yixue-cidian/现代医学辞典[1990][刘福岭][山东科学技术出版社].mdd
input/xinbian-shiyong-yixue-cidian/新编实用医学词典[1994][张俊武][…].mdx
input/xinbian-shiyong-yixue-cidian/新编实用医学词典[1994][张俊武][…].mdd
```

## Commands

```powershell
python -m pip install -r requirements.txt
python -m medical_yomitan inspect  --input input\xiandai-yixue-cidian
python -m medical_yomitan build    --input input\xiandai-yixue-cidian --revision 2026.10.27.1
python -m medical_yomitan build    --input input\xinbian-shiyong-yixue-cidian --revision 2026.10.27.1
python -m medical_yomitan validate dist\xiandai-yixue-cidian-yomitan.zip
python -m medical_yomitan validate dist\xinbian-shiyong-yixue-cidian-yomitan.zip
python -m pytest
```

`build` writes `dist/<slug>-yomitan.zip` plus `dist/<slug>-conversion-report.json`
(input hashes, counters, unknown tags, private-use characters, unresolved
references, samples). The revision defaults to today's date plus `.1`
(`YYYY.MM.DD.N`, numerically comparable by Yomitan's updater) and can be set with
`--revision` or `MEDICAL_YOMITAN_REVISION`.

`validate` checks the index against Yomitan's schema, every term bank against the
official term-bank v3 schema (via `fastjsonschema`), that every referenced image
is packaged, that links are `?query=` lookups, that no executable tags survive,
and that every reading passes the character-hygiene rule.

## Automatic builds and releases

`.github/workflows/build.yml` runs on every push and on manual dispatch. It
installs the converter, runs the tests, downloads the pinned source files from a
GitHub release, verifies their SHA-256 and size against
`.github/source-inputs.json`, builds and validates both dictionaries, and
uploads everything as a workflow artifact (kept 7 days). On `main` it also
publishes a GitHub Release tagged `build-<run id>-<attempt>` containing:

- `xiandai-yixue-cidian-yomitan.zip`, `xinbian-shiyong-yixue-cidian-yomitan.zip`
- `index-xiandai-yixue-cidian.json`, `index-xinbian-shiyong-yixue-cidian.json`
  (the updater endpoints the ZIPs point at)
- both conversion reports and `SHA256SUMS.txt`

Each release is marked latest, so `releases/latest/download/…` always serves the
newest build and Yomitan's *Check for updates* sees it. CI revisions are
`YYYY.MM.DD.<run number>`, numerically newer than any earlier build.

### One-time setup: the source-inputs release

The workflow cannot build without the MDX/MDD files, which are not in git. Upload
them once to a **pre-release** (pre-releases are never `latest`, so they cannot
shadow a build) under the ASCII asset names in `.github/source-inputs.json`.
With the files in `input/<slug>/` and `gh` signed in to the repository owner's
account, run from the repository root:

```powershell
python .github\scripts\upload_sources.py --dry-run
python .github\scripts\upload_sources.py
```

The script verifies each file against the manifest, stages copies under the
asset names in a temporary directory, and runs `gh release create
source-inputs-2026.10.27 --prerelease` with them. (Copying the files by hand is
error-prone: the `[…]` in their names are wildcard characters to PowerShell.)

This repository is public, so those assets are publicly downloadable. To keep
the sources private instead, create the same pre-release in a private
repository, set the repository variable `SOURCE_REPO` to `owner/name`, and add a
secret `SOURCE_INPUTS_TOKEN` (a fine-grained token with read access to that
repository's contents). The workflow uses them automatically.

To update a source file later: replace the asset in a new pre-release, update
`release_tag`, `size` and `sha256` in `.github/source-inputs.json`, and push.

## Source structure and what is kept

Every record is a scraped CNKI page:

```
<h3><span class="navi-search">词头</span> … <span>English equivalent</span></h3>
<p class="image_box">释义 … (<a href="entry://…">, <img>, <sub>/<sup>, <table>, nested <p align=center>)</p>
<div class="descBox">字数 … 知识来源：… 第N页</div>
<div class="chartBox">echarts canvas</div>   <div class="pageBox">上一条/下一条</div>
```

Kept: headword, English equivalent (`lang="en"`), the full definition with
formatting, inline formula/glyph images, figures, tables, `entry://` links as
Yomitan `?query=` links, and the `知识来源` line (book and page). Dropped:
word counts, the related-term chart, prev/next navigation, the external
stylesheet link, and `data-v-*`/inline style attributes.

## Conversion policy

- **Readings** — the sources contain no pronunciations, so readings are generated
  with [pypinyin](https://github.com/mozillazg/python-pinyin) (phrase-aware, tone
  marks, `ü`). Han characters become space-separated syllables; runs of digits,
  Latin, Greek and roman numerals stay verbatim in place (`17-α- qiǎng huà méi …`).
  Quotation marks, brackets and middle dots are dropped. Headwords with no Han
  characters get an empty reading. Automatic pinyin can mis-read 多音字; readings
  are for lookup and tone colouring, not authoritative pronunciation.
- **Expression** — the displayed headword without `<sup>` text (`5P⁻综合征` →
  `5P综合征`), matching caocao's `_text_without_sup`. When the MDX search key
  differs (e.g. `GM神经节苷脂病` for `GM1神经节苷脂病`), the key is emitted as an
  extra row tagged `variant` so MDict-style lookups still hit.
- **Whole-entry references** — bodies of the form `即X。` / `见X。` / `同X。` whose
  target is another headword become a clickable link and the target's header,
  definition and source are embedded beneath (chains followed up to 8 hops,
  cycles and unknown targets left as plain text and counted in the report).
- **Empty section markers** — the sources include letter, digit and pinyin
  syllable headers with no definition; these are excluded (783 and 105 records).
- **Images** — all MDD images are referenced and packaged under `media/` with
  content-hash names. Small glyph bitmaps (≤48 px or BMP) and formula GIFs are
  black line art on white; they are re-encoded as PNG with an alpha channel
  derived from luminance and rendered inline with Yomitan's `monochrome`
  appearance, so they take the current text colour in light and dark themes.
  Larger PNG/JPEG figures keep a white background and are scaled to at most
  480 px wide.
- **Private-use characters** — the sources replace characters missing from
  their font with PUA code points. Those with unambiguous context are restored
  and marked (`data-sc-content="pua-inferred"`, dotted underline, tooltip):

  | PUA | Restored | Evidence |
  | --- | --- | --- |
  | U+E550 | 𬌗 (hé) | 错𬌗、𬌗与咬合、咬𬌗关系 |
  | U+E83C, U+E0C8 | 𫫇 (è) | 磺胺甲基异𫫇唑、磺胺异𫫇唑、异𫫇唑酰肼 |
  | U+E7EE | X̄ | 两样本均数 X̄₁ 与 X̄₂ |
  | U+E634 | 疖 | 多发性疖肿、疮疡疖肿 |
  | U+EE49 | 茯 | 远志、柏子仁、茯神、硃砂 |
  | U+E0D1 / U+E0D2 | ²⁺ / ³⁺ | Ca²⁺、2价铁(Fe²⁺)、3价铁(Fe³⁺) |

  Two codes (U+E242 in 异食症, U+E477 in 真菌感染) could not be identified and
  render as `□` with a tooltip naming the code point.
- Unicode is NFC-normalised; glossaries use `lang="zh-Hans"` and the generic
  `sans-serif` font; the ZIP is byte-for-byte reproducible for the same inputs.

## Layout

```
medical_yomitan/
  builder.py       orchestration, reference expansion, term rows, index.json, report
  content.py       HTML → structured content, PUA restoration, reference detection
  readings.py      pypinyin readings and the reading hygiene rule
  resources.py     MDD image catalog, BMP→PNG, glyph/figure classification
  package.py       term-bank writer, deterministic ZIP
  validation.py    archive checks and schema validation
  dictionaries.py  per-dictionary identity, titles, update URLs
  data/styles.css  packaged stylesheet
  schemas/         Yomitan index and term-bank v3 schemas
tests/             converter unit tests + archive checks (skipped when dist/ is empty)
```

Source data and generated dictionaries are not licensed or distributed by this
converter; the original books remain the property of their authors and
publishers.
