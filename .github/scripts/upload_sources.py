"""Publish the source MDX/MDD files as a pre-release so CI can fetch them.

Usage: python .github/scripts/upload_sources.py [--input input] [--repo OWNER/NAME] [--dry-run]

Reads .github/source-inputs.json, finds each original file under input/<dictionary>/,
verifies its size and SHA-256, copies it to a temporary directory under the ASCII
asset name, and runs ``gh release create <tag> --prerelease`` with those copies.
Run it once from the repository root with ``gh`` signed in to the account that owns
the repository. Re-run after changing the manifest (new tag) when a source changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(root / "input"))
    parser.add_argument("--manifest", default=str(root / ".github" / "source-inputs.json"))
    parser.add_argument("--repo", default="", help="OWNER/NAME; defaults to the current repository's origin")
    parser.add_argument("--dry-run", action="store_true", help="Verify and stage the files, but do not create the release")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    tag = manifest["release_tag"]
    staged: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="source-inputs-") as temporary:
        stage = Path(temporary)
        for item in manifest["files"]:
            source = Path(args.input) / item["dictionary"] / item["original_name"]
            if not source.is_file():
                print(f"Missing source file: {source}", file=sys.stderr)
                return 1
            size, digest = source.stat().st_size, sha256_file(source)
            if size != item["size"] or digest != item["sha256"]:
                print(f"{source.name}: size {size} / sha256 {digest} do not match the manifest; "
                      "update .github/source-inputs.json first", file=sys.stderr)
                return 1
            target = stage / item["asset"]
            shutil.copyfile(source, target)
            staged.append(target)
            print(f"staged {item['asset']} <- {source.name} ({size} bytes, sha256 {digest[:12]})")

        command = [
            "gh", "release", "create", tag, "--prerelease",
            "--title", f"Source inputs {tag.removeprefix('source-inputs-')}",
            "--notes", "Pinned MDX/MDD inputs for CI builds. Checksums: .github/source-inputs.json. "
                       "Pre-release so it never becomes the 'latest' release.",
        ]
        if args.repo:
            command += ["--repo", args.repo]
        command += [str(p) for p in staged]
        print("$", " ".join(command[:6]), "...", ", ".join(p.name for p in staged))
        if args.dry_run:
            print("dry run: release not created")
            return 0
        return subprocess.run(command, cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
