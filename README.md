# Chinese Medical Dictionaries → Yomitan

Converter for two CNKI reference-work (CRFD) medical dictionaries distributed as
MDict `.mdx`/`.mdd` files, producing Yomitan format-3 structured-content
dictionaries in the style of
[caocaochan/hydcd-yomitan](https://github.com/caocaochan/hydcd-yomitan):
headword badge row (traditional and simplified), header block, `data-sc-content`
kinds styled by a packaged `styles.css`, `lang="zh-Hans"` glossaries,
deterministic ZIPs, JSON conversion reports and update metadata
(`isUpdatable` / `indexUrl` / `downloadUrl`).

| Dictionary | Source | Entries | Terms | Traditional | Lookup-only | Images | ZIP |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 现代医学辞典 | 刘福岭 主编，山东科学技术出版社，1990 | 10,949 | 20,225 | 8,845 | 408 | 185 | `xiandai-yixue-cidian-yomitan.zip` |
| 新编实用医学词典 | 张俊武 主编，北京医科大学中国协和医科大学联合出版社，1994 | 16,622 | 30,484 | 13,180 | 609 | 32 | `xinbian-shiyong-yixue-cidian-yomitan.zip` |

Entries are what a dictionary defines. Terms are the rows they are found by: the
simplified headword, 23 and 73 alternate MDX keys, the Taiwan form of a headword
(*traditional*) and its Hong Kong and OpenCC spellings (*lookup-only*).

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

Without the files, `python .github/scripts/fetch_inputs.py --repo OWNER/NAME`
downloads the pinned copies from the repository's source-inputs pre-release and
verifies them (under their ASCII asset names, which the build accepts as well).

## Commands

```powershell
python -m pip install -r requirements.txt
python -m medical_yomitan inspect  --input input\xiandai-yixue-cidian
python -m medical_yomitan build    --input input\xiandai-yixue-cidian
python -m medical_yomitan build    --input input\xinbian-shiyong-yixue-cidian
python -m medical_yomitan validate dist\xiandai-yixue-cidian-yomitan.zip
python -m medical_yomitan validate dist\xinbian-shiyong-yixue-cidian-yomitan.zip
python -m medical_yomitan golden   dist\xiandai-yixue-cidian-yomitan.zip dist\xinbian-shiyong-yixue-cidian-yomitan.zip
python -m medical_yomitan cedict-refresh
python -m pytest
```

`build` writes `dist/<slug>-yomitan.zip` plus `dist/<slug>-conversion-report.json`
(input hashes, row counts by kind, where the readings came from, counters,
unknown tags, private-use characters, unresolved references, samples). The
revision is four dot-separated integers, `YYYY.MM.DD.N`, which is what Yomitan's
updater compares number by number. A build nobody gives a revision gets the UTC
date and `.0`, so a local build never outranks a release of the same day; set
one with `--revision` or `MEDICAL_YOMITAN_REVISION`.

The same inputs and revision give a byte-identical ZIP, on the same machine and
across machines: a build on Windows (Python 3.12) and one on Linux (Python 3.14)
are the same bytes. Three things make that so. Members are stored in sorted
order with a fixed timestamp. Text members are written with LF whatever the
platform or the checkout's line endings. And re-encoded images are written by
the converter's own PNG encoder, which compresses with Python's `zlib`, not by
Pillow, whose wheels bundle a different zlib on Windows and on Linux. What is
left is Python's `zlib` itself, which also compresses the ZIP: a Python built
against another zlib could produce other bytes for the same content.
`tests/test_reproducibility.py` pins the encoder's output, so such a machine
fails the tests instead of quietly building a different file.

`validate` checks the index against Yomitan's schema, every term bank against the
official term-bank v3 schema (via `fastjsonschema`), that every referenced image
is packaged, that links are `?query=` lookups, that no executable tags survive,
that every reading passes the character-hygiene rule, that the revision is four
integers (`--revision R`: that it is exactly R), and the golden words
(`--no-golden` to skip).

`golden` checks a built ZIP against `medical_yomitan/data/golden_words.tsv`: one
fact per line about a particular word, so that a change which loses or misreads
it fails instead of passing unnoticed. A line says that a headword is present or
absent, has a given reading, is also filed under a given spelling or alternate
key, or that the row of a given spelling shows a given text in its traditional
box. The file covers Taiwan forms, lookup-only spellings and what their rows
show, the forms corrected after OpenCC and the wrong ones that must be gone,
alternate keys, readings that used to be wrong, headwords with Latin and
Greek, and terms that must not exist (the vocabulary swaps `s2twp` would make).

`cedict-refresh` rewrites the pinned CC-CEDICT readings table; see Readings.

## Automatic builds and releases

Two workflows; neither is triggered by the other.

**Build and check** (`.github/workflows/check.yml`) runs on every push to `main`
and on every pull request, with a read-only token. It runs the tests, downloads
the pinned source files and verifies their SHA-256 and size against
`.github/source-inputs.json`, builds both dictionaries, validates them, checks
the golden words and keeps the ZIPs as a workflow artifact for 7 days. It
publishes nothing.

**Build and release** (`.github/workflows/release.yml`) is started by hand
(*Actions → Build and release → Run workflow*, or `gh workflow run release.yml`).
Inputs: `publish` (default on; off builds the assets and keeps them as an
artifact) and `revision` (optional). It has two jobs:

- `build`, read-only: everything the check workflow does, with the release's
  revision, then the release assets and notes.
- `publish`, the only job that can write to the repository: downloads the
  artifact, verifies `SHA256SUMS.txt`, and creates the release `v<revision>`
  (tag and title), marked latest, on the commit that was built.

A release is published from the default branch only. Its revision is the
`revision` input, else the UTC date plus the run number. The run is stopped in
its first minute when that revision is not four integers, when a release or tag
`v<revision>` already exists, or when it is not greater than the revision of the
latest release. That last check reads the `index-<slug>.json` assets of the
latest release, which is what installed copies compare with, rather than its
tag: the first two releases are tagged `build-<run id>-<attempt>`. (A new
workflow file starts its run number at 1 again; this check is what makes that
safe.)

Release assets, whose names installed copies have baked into their update URLs:

- `xiandai-yixue-cidian-yomitan.zip`, `xinbian-shiyong-yixue-cidian-yomitan.zip`
- `index-xiandai-yixue-cidian.json`, `index-xinbian-shiyong-yixue-cidian.json`
  (the updater endpoints the ZIPs point at)
- both conversion reports and `SHA256SUMS.txt`

The release notes are written by `.github/scripts/prepare_release.py`: the
revision, one row per ZIP (entries, terms, traditional, lookup-only, images,
size), and a *Changes since <previous tag>* section with the same counts next to
their change (`(same)`, `(+N)`, `(-N)`, `(new)`), the subjects of the commits
since the previous release (oldest first, no merge commits, at most 40) and a
link to GitHub's comparison of the two tags. The previous counts are read back
from the table in the previous release's notes; the table of the two `build-…`
releases is read too, for the terms and images it has. The commits come from
GitHub's compare API. A part that cannot be worked out is left out: a failed
request means no commit list, not "no commits".

Dependabot (`.github/dependabot.yml`) checks weekly. `requirements.txt` pins
exact versions, which is what CI installs; minor and patch updates of an
ecosystem arrive as one pull request, each major as its own.

### One-time setup: the source-inputs release

The workflows cannot build without the MDX/MDD files, which are not in git. Upload
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
repository's contents). Both workflows use them automatically. (A pull request
from a fork cannot read the secret and would then fail at the download.)

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

## Traditional lookup

Both sources are in simplified characters only, and nothing in an entry says
which traditional character a simplified one stands for. The conversion is
therefore OpenCC's, with
[opencc-python-reimplemented](https://github.com/yichen0831/opencc-python), the
package Baidu-Baike-Yomitan uses.

- **Shown form: Taiwan's (`s2tw`).** An entry whose Taiwan form differs from its
  headword shows it in a `traditional-term` box (`lang="zh-TW"`) to the left of
  the simplified one, and has a row under it with the same reading, glossary,
  sequence and score: 里急后重 is also found as 裡急後重. Never `s2twp`, which
  also swaps vocabulary (循环 → 迴圈, 信息 → 資訊, 酰 → 醯) and would turn a
  headword into another term.
- **Lookup-only spellings: Hong Kong's (`s2hk`) and OpenCC's own (`s2t`).** Where
  they differ from the headword and the Taiwan form, they get a row too: 裏急後重.
  On such a row, and only there, the box shows the Taiwan form, then `、`, then
  the row's own spelling (`裡急後重、裏急後重`); with no Taiwan form to add to,
  the row's spelling alone (便秘 found as 便祕 shows `便祕`). The glossary is
  copied with the box replaced; nothing below the badge row is rendered again.
  A lookup-only spelling that is itself a displayed headword gets no row.
- **Alternate MDX keys** (rows tagged `variant`) get rows for their own converted
  spellings, with the same tag. The box only ever shows forms of the displayed
  headword.
- Latin, Greek and digits pass through. So do characters restored from the
  source's private-use placeholders: OpenCC would write 噁 for 𫫇, and
  磺胺异𫫇唑 is kept as 磺胺異𫫇唑.
- Row order per entry: headword, Taiwan form, lookup-only spellings, then each
  alternate key followed by its converted spellings.

**Corrections.** OpenCC converts phrase by phrase and reads some medical terms
as another word: 低氧血症 as 低氧血癥 (血癥 is a 中医 term), 范可尼综合征 as
範可尼綜合徵, 巨细胞 as 鉅細胞, 粗面内质网 as 粗麵內質網, 阿托品 as 阿託品.
`data/traditional_corrections.tsv` lists such phrases with the form that is
right (57 lines), and they are corrected after the conversion:

- A line is `simplified phrase<TAB>its traditional form`. Wherever the phrase
  occurs in a headword or an alternate key, the characters in which that form
  differs from what OpenCC writes for the phrase replace OpenCC's. The
  correction is positional, which works because OpenCC never changes the number
  of characters of a headword here.
- It holds in all three standards, so the wrong form is not filed at all, also
  not as a lookup-only spelling. The other characters of the phrase keep each
  standard's own form: 卫生发展管理程序 is 衛生發展管理程序 and, looked up the
  Hong Kong way, 衞生發展管理程序.
- A corrected form that equals the headword means no Taiwan form, no box and no
  extra row (低氧血症). 238 entries have a corrected form (91 and 147).
- The table is for words read as another word, not for a character two
  standards write differently. A line OpenCC already converts as stated is
  refused when the table is loaded, so a stale line cannot linger.

Not corrected: 谷 in 谷氨酸 (穀氨酸) against 谷氨酰胺 and 谷胱甘肽 (谷), where
usage itself is split, and 岩, which OpenCC writes 巖 in every standard.

## Readings

The sources contain no pronunciations. A reading is assembled per headword
(`medical_yomitan/readings.py`), from the first of these that applies:

1. **`data/pinyin_overrides.tsv`**, hand-checked `term<TAB>reading` lines (124).
   A line applies to the headword it names and to every longer headword that
   contains the term: 重吸收 `chóng xī shōu` also fixes 肾小管重吸收作用. A
   one-character line is weaker: it reads that character only where no word
   covers it (椎 `zhuī`, 咽 `yān`, 长 `cháng`).
2. **[CC-CEDICT](https://cc-cedict.org/)**, when it lists the headword. Its
   numbered pinyin is converted to this project's format. Of several readings,
   the one pypinyin's own guess points at, else the first lower-case one.
3. For the other headwords, each run of Han characters is read on its own: the
   run itself when CC-CEDICT lists it, else the **CC-CEDICT words found inside
   it** (the non-overlapping choice that covers the most characters, then has
   the fewest words, then starts leftmost), and
   [pypinyin](https://github.com/mozillazg/python-pinyin) for the characters
   left over. A character CC-CEDICT gives exactly one reading for takes that
   reading instead of pypinyin's (脊 `jǐ`, 肋 `lèi`).

Format: lower-case syllables with tone marks and `ü`, separated by spaces; a
neutral tone has no mark (CC-CEDICT's 困难 `kùn nan`, 部分 `bù fen`). Runs of
digits, Latin, Greek and roman numerals stay verbatim in place
(`17-α- qiǎng huà méi …`). Quotation marks, brackets and middle dots are
dropped. Headwords with no Han characters get an empty reading.

Before this, pypinyin alone read 子宫 as `zi gōng`, 脊髓 as `jí suǐ`, 椎 as
`chuí` and 肋 as `lē`. About 7% of the entries changed (696 and 1,295). What
remains uncertain: roughly one headword in nine is still read by pypinyin
alone, and where a 多音字 is not inside any CC-CEDICT word, nothing confirms
its reading. Readings are for lookup and tone colouring, not authoritative
pronunciation.

**The pinned CC-CEDICT table.** The build downloads nothing. It reads
`medical_yomitan/data/cedict_readings.tsv`, a table *derived* from the MDBG
export of CC-CEDICT: for every simplified headword with a Han character, its
numbered-pinyin readings in the order of the export (glosses and traditional
forms are not kept). Its header records the date of the export it was made from,
currently 2026-11-10. `python -m medical_yomitan cedict-refresh` downloads the
current export and rewrites the table (`--source FILE` derives it from a local
copy); rebuild and run `golden` afterwards, since a new export can change
readings.

CC-CEDICT is published by MDBG under the
[Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/).
The derived table is distributed under the same licence, and each dictionary's
`index.json` and the release notes carry the attribution.

## Conversion policy

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
  `sans-serif` font; the ZIP is byte-for-byte reproducible for the same inputs
  (see Commands).

## Layout

```
medical_yomitan/
  builder.py       orchestration, reference expansion, term rows, index.json, report
  content.py       HTML → structured content, badge row, PUA restoration, reference detection
  traditional.py   OpenCC forms of a headword and their corrections, the traditional box, lookup-only rows
  readings.py      overrides, CC-CEDICT, words inside a headword, pypinyin; reading hygiene
  cedict.py        the pinned CC-CEDICT readings table and its refresh
  golden.py        golden-word checks on a built ZIP
  release.py       revisions and release notes
  resources.py     MDD image catalog, the PNG encoder, glyph/figure classification
  package.py       term-bank writer, deterministic ZIP
  validation.py    archive checks and schema validation
  dictionaries.py  per-dictionary identity, titles, update URLs
  data/styles.css             packaged stylesheet
  data/cedict_readings.tsv    readings derived from CC-CEDICT (CC BY-SA 4.0)
  data/pinyin_overrides.tsv   hand-checked readings
  data/traditional_corrections.tsv  traditional forms OpenCC gets wrong
  data/golden_words.tsv       facts a build has to show
  schemas/         Yomitan index and term-bank v3 schemas
.github/
  workflows/check.yml, release.yml
  scripts/fetch_inputs.py     download and verify the pinned source inputs
  scripts/upload_sources.py   publish them as a pre-release (once)
  scripts/choose_revision.py  the revision of a release, and the checks that refuse one
  scripts/prepare_release.py  release assets, SHA256SUMS.txt and notes
  source-inputs.json, dependabot.yml
tests/             unit tests + checks of the built ZIPs (skipped when dist/ is empty)
```

Source data and generated dictionaries are not licensed or distributed by this
converter; the original books remain the property of their authors and
publishers. Readings are partly from CC-CEDICT (https://cc-cedict.org/),
CC BY-SA 4.0.
