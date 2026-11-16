"""Assemble the release assets after both dictionaries are built and validated.

Usage: python .github/scripts/prepare_release.py [--dist dist] [--output release]
           [--previous previous.json] [--commits commits.json] [--repo OWNER/NAME]

Produces, in the output directory:
  <slug>-yomitan.zip               the dictionaries (unchanged)
  index-<slug>.json                each ZIP's index.json, which Yomitan's updater fetches
  <slug>-conversion-report.json    build reports
  SHA256SUMS.txt                   checksums of every asset above
  NOTES.md                         release notes
and prints ``revision=<value>``.

previous.json is ``gh release view --json tagName,body`` of the latest release; a
missing file or ``{}`` means there is none to compare with. commits.json is
GitHub's compare API reduced to ``[{"message", "parents"}]``, oldest first; a
missing file means the request failed, and the notes then leave the commits out
(which is not the same as listing none).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from medical_yomitan.dictionaries import DICTIONARIES  # noqa: E402
from medical_yomitan.release import ZipStats, check_revision, release_notes  # noqa: E402


def read_json(path: str | None, fallback):
    """The JSON in ``path``; ``fallback`` when there is no such file or it does not parse."""
    if not path or not Path(path).is_file():
        return fallback
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8") or "null")
    except ValueError:
        return fallback
    return fallback if value is None else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--output", default="release")
    parser.add_argument("--previous", help="gh release view --json tagName,body of the latest release")
    parser.add_argument("--commits", help="commits since that release, from GitHub's compare API")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="OWNER/NAME, for the compare link")
    args = parser.parse_args()
    dist, out = Path(args.dist), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    revisions: set[str] = set()
    stats: list[ZipStats] = []
    assets: list[Path] = []
    cedict_date = ""
    for dictionary in DICTIONARIES.values():
        archive = dist / dictionary.archive
        report_path = dist / dictionary.report
        if not archive.exists() or not report_path.exists():
            print(f"Missing build output for {dictionary.slug}: {archive} / {report_path}", file=sys.stderr)
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
        shutil.copy2(report_path, out / dictionary.report)
        assets += [out / dictionary.index, out / dictionary.archive, out / dictionary.report]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        cedict_date = report.get("readings", {}).get("cedict_export_date", cedict_date)
        stats.append(ZipStats.from_report(dictionary.archive, dictionary.title, report, archive.stat().st_size))

    if len(revisions) != 1:
        print(f"Dictionaries carry different revisions: {sorted(revisions)}", file=sys.stderr)
        return 1
    revision = revisions.pop()
    try:
        check_revision(revision)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    sums = out / "SHA256SUMS.txt"
    sums.write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(assets, key=lambda p: p.name)),
        encoding="utf-8", newline="\n",
    )
    previous = read_json(args.previous, None)
    commits = read_json(args.commits, None)      # [] is "no commits"; no file is "could not be listed"
    notes = release_notes(
        revision, stats,
        previous=previous if isinstance(previous, dict) else None,
        commits=commits if isinstance(commits, list) else None,
        repo=args.repo or None, cedict_date=cedict_date,
    )
    (out / "NOTES.md").write_text(notes, encoding="utf-8", newline="\n")
    print(f"revision={revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
