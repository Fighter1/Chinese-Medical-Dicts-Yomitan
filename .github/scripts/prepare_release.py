"""Assemble the release assets after both dictionaries are built and validated.

Usage: python .github/scripts/prepare_release.py --dist dist --output release

Produces, in the output directory:
  <slug>-yomitan.zip               the dictionaries (unchanged)
  index-<slug>.json                each ZIP's index.json, which Yomitan's updater fetches
  <slug>-conversion-report.json    build reports
  SHA256SUMS.txt                   checksums of every asset above
  NOTES.md                         release notes
and prints ``revision=<value>`` for the workflow to use as the release title.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from medical_yomitan.dictionaries import DICTIONARIES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--output", default="release")
    args = parser.parse_args()
    dist, out = Path(args.dist), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    revisions: set[str] = set()
    rows: list[str] = []
    assets: list[Path] = []
    for dictionary in DICTIONARIES.values():
        archive = dist / dictionary.archive
        report = dist / dictionary.report
        if not archive.exists() or not report.exists():
            print(f"Missing build output for {dictionary.slug}: {archive} / {report}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(archive) as zf:
            index_bytes = zf.read("index.json")
        index = json.loads(index_bytes)
        if index["indexUrl"] != dictionary.index_url or index["downloadUrl"] != dictionary.download_url:
            print(f"{dictionary.slug}: index update URLs do not match dictionaries.py", file=sys.stderr)
            return 1
        revisions.add(index["revision"])
        (out / dictionary.index).write_bytes(index_bytes)
        shutil.copy2(archive, out / dictionary.archive)
        shutil.copy2(report, out / dictionary.report)
        assets += [out / dictionary.index, out / dictionary.archive, out / dictionary.report]
        counts = json.loads(report.read_text(encoding="utf-8"))
        rows.append(
            f"| {dictionary.title} | {counts['output']['terms']:,} | {counts['output']['images']} "
            f"| {archive.stat().st_size / 1e6:.2f} MB | `{dictionary.archive}` |"
        )

    if len(revisions) != 1:
        print(f"Dictionaries carry different revisions: {sorted(revisions)}", file=sys.stderr)
        return 1
    revision = revisions.pop()

    sums = out / "SHA256SUMS.txt"
    sums.write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(assets, key=lambda p: p.name)),
        encoding="utf-8",
    )
    notes = out / "NOTES.md"
    notes.write_text(
        f"Dictionary revision **{revision}** (shown in Yomitan's dictionary list).\n\n"
        "| Dictionary | Terms | Images | ZIP | Asset |\n| --- | ---: | ---: | ---: | --- |\n"
        + "\n".join(rows)
        + "\n\nImport the ZIP into Yomitan. Installed copies with update metadata can fetch this build "
        "through *Check for updates*; the `index-*.json` assets are what the updater reads.\n",
        encoding="utf-8",
    )
    print(f"revision={revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
