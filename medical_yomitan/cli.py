from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from . import __version__
from .dictionaries import DICTIONARIES, detect_dictionary, get_dictionary
from .models import InputSet
from .source import discover_input, iter_mdx_records, mdx_header


def _inputs(args: argparse.Namespace) -> InputSet:
    if args.input:
        return discover_input(Path(args.input))
    if not args.mdx:
        raise SystemExit("Pass --input DIR or --mdx FILE [--mdd FILE ...]")
    return InputSet(mdx=Path(args.mdx).resolve(), mdds=tuple(Path(p).resolve() for p in args.mdd or ()))


def _dictionary(args: argparse.Namespace, inputs: InputSet):
    if args.dictionary:
        return get_dictionary(args.dictionary)
    sample = []
    for _, _, raw in iter_mdx_records(inputs.mdx):
        sample.append(raw[:200])
        if len(sample) >= 20:
            break
    dictionary = detect_dictionary(sample)
    if dictionary is None:
        raise SystemExit("Could not detect the dictionary; pass --dictionary " + "|".join(DICTIONARIES))
    return dictionary


def cmd_inspect(args: argparse.Namespace) -> int:
    inputs = _inputs(args)
    print(json.dumps(mdx_header(inputs.mdx), ensure_ascii=False, indent=2))
    tags: collections.Counter[str] = collections.Counter()
    classes: collections.Counter[str] = collections.Counter()
    total = links = 0
    for _, _, raw in iter_mdx_records(inputs.mdx):
        total += 1
        if raw.startswith("@@@LINK="):
            links += 1
        tags.update(t.lower() for t in re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)", raw))
        classes.update(re.findall(r'class="([^"]*)"', raw))
    print(json.dumps({"records": total, "link_records": links, "tags": tags.most_common(),
                      "classes": classes.most_common(30)}, ensure_ascii=False, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .builder import build_dictionary

    inputs = _inputs(args)
    dictionary = _dictionary(args, inputs)
    output = Path(args.output) if args.output else Path("dist") / dictionary.archive
    report, report_path = build_dictionary(dictionary, inputs, output, revision=args.revision)
    print(json.dumps({
        "dictionary": dictionary.slug, "title": dictionary.title, "revision": report["dictionary_revision"],
        "output": report["output"], "counts": report["counts"], "unknown_tags": report["unknown_tags"],
        "warnings": report["warning_samples"][:5], "errors": report["error_samples"][:5],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 1 if report["error_samples"] else 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .validation import validate_archive

    result = validate_archive(Path(args.archive), schema=not args.no_schema)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="medical_yomitan", description="Convert CRFD-style medical MDX dictionaries to Yomitan.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_inputs(p: argparse.ArgumentParser) -> None:
        p.add_argument("--input", help="Directory holding exactly one .mdx and its .mdd files")
        p.add_argument("--mdx", help="Path to the .mdx file (alternative to --input)")
        p.add_argument("--mdd", action="append", help="Path to a .mdd file (repeatable)")

    p = sub.add_parser("inspect", help="Print MDX header and tag statistics")
    add_inputs(p)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("build", help="Build a Yomitan ZIP")
    add_inputs(p)
    p.add_argument("--dictionary", choices=sorted(DICTIONARIES), help="Which dictionary identity to use (auto-detected if omitted)")
    p.add_argument("--output", help="Output ZIP path (default: dist/<archive name>)")
    p.add_argument("--revision", help="Dictionary revision (default: today's date + .1, or $MEDICAL_YOMITAN_REVISION)")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="Validate a built ZIP")
    p.add_argument("archive")
    p.add_argument("--no-schema", action="store_true", help="Skip JSON-schema validation of term banks")
    p.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)
