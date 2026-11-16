"""Choose the revision of a release and refuse one that cannot be released.

Usage: python .github/scripts/choose_revision.py [--revision REV] [--run-number N] [--repo OWNER/NAME]

The revision is ``--revision`` when given, else the UTC date plus the run number.
It is refused when

* it is not four dot-separated integers (Yomitan would compare it as text);
* a release or a tag ``v<revision>`` already exists (a tag without a release
  counts: ``gh release create`` would reuse it, whatever commit it is on);
* it is not greater than the revision of the latest release. That revision is
  read from the ``index-<slug>.json`` assets of the latest release, which is what
  installed copies compare with, not from its tag: the releases before v-tags
  are named ``build-<run id>-<attempt>``. A new workflow file starts its run
  number at 1 again; this check is what makes that safe.

Prints ``revision=<value>`` and appends it to $GITHUB_OUTPUT and, as REVISION, to
$GITHUB_ENV when those are set. Needs ``gh`` with a token in GH_TOKEN. Anything
GitHub does not answer clearly stops the release: a check that could not be made
is not a check that passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from medical_yomitan.dictionaries import DICTIONARIES  # noqa: E402
from medical_yomitan.release import check_revision, refuse_revision, release_revision  # noqa: E402


class Refused(Exception):
    pass


def gh_api(path: str) -> dict | None:
    """The JSON GitHub answers for ``path``; None for 404. Any other failure is an error."""
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "HTTP 404" in result.stderr or "HTTP 404" in result.stdout:
        return None
    raise Refused(f"gh api {path} failed: {(result.stderr or result.stdout).strip()}")


def latest_revisions(repo: str) -> list[str]:
    """The revisions in the index files of the latest release; [] when there is no release."""
    latest = gh_api(f"repos/{repo}/releases/latest")
    if latest is None:
        return []
    tag = latest["tag_name"]
    wanted = {dictionary.index for dictionary in DICTIONARIES.values()}
    present = wanted & {asset["name"] for asset in latest.get("assets", [])}
    if not present:
        raise Refused(f"the latest release ({tag}) has none of {sorted(wanted)}; its revision cannot be read, "
                      "so it cannot be told whether a new release would be offered as an update")
    revisions: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        for name in sorted(present):
            subprocess.run(["gh", "release", "download", tag, "--repo", repo, "--pattern", name, "--dir", directory],
                           check=True)
            revisions.append(str(json.loads((Path(directory) / name).read_text(encoding="utf-8")).get("revision")))
    print(f"latest release {tag}: revision {', '.join(sorted(set(revisions)))}")
    return revisions


def choose(revision: str, run_number: int, repo: str) -> str:
    revision = revision.strip() or release_revision(run_number)
    try:
        check_revision(revision)
    except ValueError as error:
        raise Refused(str(error)) from error
    tag = f"v{revision}"
    if gh_api(f"repos/{repo}/releases/tags/{tag}") is not None:
        raise Refused(f"the release {tag} already exists")
    if gh_api(f"repos/{repo}/git/ref/tags/{tag}") is not None:
        raise Refused(f"the tag {tag} already exists")
    if reason := refuse_revision(revision, latest_revisions(repo)):
        raise Refused(reason)
    return revision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=os.environ.get("INPUT_REVISION", ""))
    parser.add_argument("--run-number", type=int, default=int(os.environ.get("GITHUB_RUN_NUMBER", "0") or 0))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if not args.repo:
        print("::error::pass --repo OWNER/NAME or set GITHUB_REPOSITORY", file=sys.stderr)
        return 2
    try:
        revision = choose(args.revision, args.run_number, args.repo)
    except (Refused, subprocess.CalledProcessError, ValueError, KeyError) as error:
        print(f"::error::{error}")
        return 1
    for variable, line in (("GITHUB_OUTPUT", f"revision={revision}"), ("GITHUB_ENV", f"REVISION={revision}")):
        if os.environ.get(variable):
            with open(os.environ[variable], "a", encoding="utf-8") as stream:
                stream.write(line + "\n")
    print(f"revision={revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
