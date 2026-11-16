"""What a release needs besides the ZIPs: its revision and its notes.

Nothing here talks to GitHub. The workflow fetches what is needed with ``gh``
(the previous release, the commits since its tag) and hands it over as files;
``.github/scripts/choose_revision.py`` and ``prepare_release.py`` call into this
module, and the tests cover it without a network.

Revisions: Yomitan offers an update only when the revision at ``indexUrl`` is
greater than the installed one, and compares number by number only when both
are dot-separated integers with the same number of segments. So every revision
is four integers, ``YYYY.MM.DD.N``: N is 0 for a local build, the run number
for a release (or whatever the person starting the release typed).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .cedict import ATTRIBUTION as CEDICT_ATTRIBUTION

REVISION_SHAPE = re.compile(r"[0-9]+(?:\.[0-9]+){3}")
MAX_LISTED_COMMITS = 40
_MERGE_SUBJECT = re.compile(r"^Merge (branch|pull request|remote-tracking branch|tag) ")


# --- revisions -------------------------------------------------------------------

def check_revision(revision: str) -> str:
    """Exactly four dot-separated integers, or ValueError."""
    if not REVISION_SHAPE.fullmatch(revision or ""):
        raise ValueError(f"revision {revision!r} must be four dot-separated integers (e.g. 2026.11.16.3) "
                         "so Yomitan can compare it numerically")
    return revision


def revision_key(revision: str) -> tuple[int, ...]:
    return tuple(int(part) for part in check_revision(revision).split("."))


def is_newer(revision: str, than: str) -> bool:
    """Whether Yomitan would offer ``revision`` to a copy that has ``than`` installed."""
    return revision_key(revision) > revision_key(than)


def utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def local_revision(today: dt.date | None = None) -> str:
    """The revision of a build nobody asked a revision for: the UTC date and 0,
    below any release of the same day (those end in the run number, 1 or more)."""
    return (today or utc_today()).strftime("%Y.%m.%d") + ".0"


def release_revision(run_number: int, today: dt.date | None = None) -> str:
    return (today or utc_today()).strftime("%Y.%m.%d") + f".{int(run_number)}"


def refuse_revision(revision: str, latest_revisions: Iterable[str]) -> str | None:
    """Why ``revision`` cannot be released after a release whose index files carry
    ``latest_revisions``; None when it can."""
    try:
        check_revision(revision)
    except ValueError as error:
        return str(error)
    for latest in latest_revisions:
        try:
            newer = is_newer(revision, latest)
        except ValueError:
            return (f"the latest release carries the revision {latest!r}, which is not four integers; "
                    "it cannot be compared with, so nothing can be released after it automatically")
        if not newer:
            return (f"revision {revision} is not greater than the latest release's ({latest}); "
                    "nobody who has that one installed would be offered it as an update")
    return None


# --- release notes ---------------------------------------------------------------

COUNTS = ("entries", "terms", "traditional", "lookup_only", "images")
_HEADINGS = {"entries": "entries", "terms": "terms", "traditional": "traditional", "lookup_only": "lookup-only",
             "images": "images"}
# A row of the table release_notes writes: file, dictionary, then the five counts, then the size.
_ROW = re.compile(
    r"^\| `(?P<file>[^`|]+)` \|[^|]*\| (?P<entries>[\d,]+) \| (?P<terms>[\d,]+) \| (?P<traditional>[\d,]+) \| "
    r"(?P<lookup_only>[\d,]+) \| (?P<images>[\d,]+) \|", re.M)
# The table of the releases before this module (build-40600882103-1, build-40602930225-1):
# | 现代医学辞典 | 10,972 | 185 | 4.30 MB | `xiandai-yixue-cidian-yomitan.zip` |
_OLD_ROW = re.compile(
    r"^\| [^|`]+ \| (?P<terms>[\d,]+) \| (?P<images>[\d,]+) \| [\d.,]+ MB \| `(?P<file>[^`|]+)` \|", re.M)


@dataclass(frozen=True)
class ZipStats:
    file: str
    title: str
    entries: int
    terms: int
    traditional: int
    lookup_only: int
    images: int
    size: int

    @classmethod
    def from_report(cls, file: str, title: str, report: dict[str, Any], size: int) -> "ZipStats":
        rows = report["rows"]
        return cls(file, title, rows["entries"], report["output"]["terms"], rows["traditional"],
                   rows["lookup_only"], report["output"]["images"], size)


def _number(text: str) -> int:
    return int(text.replace(",", ""))


def previous_counts(body: str) -> dict[str, dict[str, int]]:
    """file -> the counts the previous release's notes state for it. The table of
    the two releases made before this module has terms and images only; the
    counts it lacks are simply missing from the result."""
    found: dict[str, dict[str, int]] = {}
    for match in _ROW.finditer(body or ""):
        found[match["file"]] = {name: _number(match[name]) for name in COUNTS}
    if not found:
        for match in _OLD_ROW.finditer(body or ""):
            found[match["file"]] = {"terms": _number(match["terms"]), "images": _number(match["images"])}
    return found


def delta(now: int, before: int | None) -> str:
    """A count next to its change: ``20,250 (+9,278)``, ``185 (same)``, ``10,949 (new)``."""
    if before is None:
        return f"{now:,} (new)"
    return f"{now:,} (same)" if now == before else f"{now:,} ({now - before:+,})"


def commit_subjects(commits: list[dict[str, Any]] | None) -> list[str] | None:
    """The subjects of the commits since the previous release, oldest first, without
    merge commits. ``commits`` is GitHub's compare API reduced to
    ``[{"message", "parents"}]``; None (the request failed) stays None."""
    if commits is None:
        return None
    subjects: list[str] = []
    for commit in commits:
        subject = str(commit.get("message") or "").split("\n")[0].strip()
        if not subject or int(commit.get("parents") or 1) > 1 or _MERGE_SUBJECT.match(subject):
            continue
        subjects.append(subject)
    return subjects


def changes_since(previous: dict[str, Any] | None, stats: list[ZipStats], commits: list[dict[str, Any]] | None,
                  repo: str | None, tag: str | None) -> list[str]:
    """Lines of the "Changes since <tag>" section, in the layout of Baidu-Baike-Yomitan:
    the counts with their change, the commits, the link to GitHub's comparison.
    A part that cannot be worked out is left out; with nothing to say, no section."""
    previous_tag = (previous or {}).get("tagName")
    if not previous_tag:
        return []
    section: list[str] = []
    before = previous_counts((previous or {}).get("body") or "")
    if before:
        section += ["| file | " + " | ".join(_HEADINGS[name] for name in COUNTS) + " |",
                    "|---|" + "---:|" * len(COUNTS)]
        for item in stats:
            old = before.get(item.file, {})
            section.append(f"| `{item.file}` | "
                           + " | ".join(delta(getattr(item, name), old.get(name)) for name in COUNTS) + " |")
        section.append("")
    subjects = commit_subjects(commits)
    if subjects:
        shown = subjects[:MAX_LISTED_COMMITS]
        section.append(f"**Code:** {len(subjects)} commit{'s' if len(subjects) != 1 else ''}.")
        section += [f"- {subject}" for subject in shown]
        if len(subjects) > len(shown):
            section.append(f"- … and {len(subjects) - len(shown)} more")
        section.append("")
    elif subjects is not None:
        section += ["**Code:** no commits; the same code as the previous release.", ""]
    if repo and tag:
        span = f"{previous_tag}...{tag}"
        section.append(f"**Full Changelog**: [{span}](https://github.com/{repo}/compare/{span})")
    while section and section[-1] == "":
        section.pop()
    return ["", f"## Changes since {previous_tag}", "", *section] if section else []


def release_notes(revision: str, stats: list[ZipStats], *, previous: dict[str, Any] | None = None,
                  commits: list[dict[str, Any]] | None = None, repo: str | None = None,
                  cedict_date: str = "") -> str:
    """``previous``: ``gh release view --json tagName,body`` of the release before
    this one (None or {} for the first). ``commits``: see commit_subjects."""
    tag = f"v{revision}"
    lines = [
        f"Dictionary revision **{revision}** (shown in Yomitan's dictionary list).",
        "",
        "| file | dictionary | entries | terms | traditional | lookup-only | images | size |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in stats:
        lines.append(f"| `{item.file}` | {item.title} | {item.entries:,} | {item.terms:,} | {item.traditional:,} | "
                     f"{item.lookup_only:,} | {item.images:,} | {item.size / 1e6:.2f} MB |")
    lines += ["",
              "Entries are what a dictionary defines; terms are the rows they are found by. Traditional: rows under "
              "the Taiwan form of a headword. Lookup-only: rows under its Hong Kong and OpenCC spelling."]
    if previous and previous.get("tagName") == tag:
        previous = None                      # the notes of a release cannot be compared with themselves
    lines += changes_since(previous, stats, commits, repo, tag)
    lines += ["",
              "Import the ZIP into Yomitan. Installed copies with update metadata can fetch this build through "
              "*Check for updates*; the `index-*.json` assets are what the updater reads.",
              "",
              CEDICT_ATTRIBUTION.replace("CC-CEDICT (https://cc-cedict.org/)", "[CC-CEDICT](https://cc-cedict.org/)")
              + (f" Export of {cedict_date[:10]}." if cedict_date else "")]
    return "\n".join(lines) + "\n"
