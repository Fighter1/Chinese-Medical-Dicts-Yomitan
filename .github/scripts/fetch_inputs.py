"""Download the pinned source dictionaries from a GitHub release and verify them.

Usage: python .github/scripts/fetch_inputs.py [--repo OWNER/NAME] [--manifest PATH] [--output input]

Requires the ``gh`` CLI with a token in ``GH_TOKEN`` (GitHub Actions provides one).
Every asset must match the size and SHA-256 recorded in the manifest; a mismatch
fails the build so a silently changed source can never be released.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("SOURCE_REPO") or os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--manifest", default=".github/source-inputs.json")
    parser.add_argument("--output", default="input")
    args = parser.parse_args()
    if not args.repo:
        print("Pass --repo OWNER/NAME or set SOURCE_REPO / GITHUB_REPOSITORY", file=sys.stderr)
        return 2

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    tag = manifest["release_tag"]
    failures = 0
    for item in manifest["files"]:
        target_dir = Path(args.output) / item["dictionary"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / item["asset"]
        if not target.exists():
            print(f"Downloading {item['asset']} from {args.repo}@{tag}")
            subprocess.run(
                ["gh", "release", "download", tag, "--repo", args.repo, "--pattern", item["asset"],
                 "--dir", str(target_dir), "--clobber"],
                check=True,
            )
        size = target.stat().st_size
        digest = sha256_file(target)
        if size != item["size"] or digest != item["sha256"]:
            failures += 1
            print(f"MISMATCH {item['asset']}: size {size} (expected {item['size']}), sha256 {digest} (expected {item['sha256']})",
                  file=sys.stderr)
        else:
            print(f"OK {item['asset']} ({size} bytes, sha256 {digest[:12]}) <- {item['original_name']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
