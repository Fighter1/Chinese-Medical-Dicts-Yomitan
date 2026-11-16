import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from medical_yomitan.dictionaries import DICTIONARIES
from medical_yomitan.release import (
    ZipStats, changes_since, check_revision, commit_subjects, delta, is_newer, local_revision, previous_counts,
    refuse_revision, release_notes, release_revision,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- revisions --------------------------------------------------------------------

@pytest.mark.parametrize("revision", ["2026.11.16.3", "2026.10.27.2", "1.2.3.4", "2026.11.16.0"])
def test_four_integers_are_a_revision(revision):
    assert check_revision(revision) == revision


@pytest.mark.parametrize("revision", ["", "2026.11.16", "2026.11.16.3.1", "v2026.11.16.3", "2026.11.16.x", "2026-11-16-3",
                                      "2026.11.16.3\n", " 2026.11.16.3"])
def test_anything_else_is_refused(revision):
    with pytest.raises(ValueError):
        check_revision(revision)


def test_revisions_compare_number_by_number():
    assert is_newer("2026.11.16.10", "2026.11.16.9")         # as text "10" < "9"
    assert is_newer("2026.11.16.1", "2026.10.27.2")
    assert not is_newer("2026.10.27.2", "2026.10.27.2")
    assert not is_newer("2026.10.27.1", "2026.10.27.2")


def test_a_local_build_never_outranks_a_release_of_the_same_day():
    day = dt.date(2026, 11, 16)
    assert local_revision(day) == "2026.11.16.0"
    assert release_revision(1, day) == "2026.11.16.1"
    assert is_newer(release_revision(1, day), local_revision(day))


def test_refuse_revision():
    assert refuse_revision("2026.11.16.1", []) is None                       # the first release
    assert refuse_revision("2026.11.16.1", ["2026.10.27.2", "2026.10.27.2"]) is None
    assert "not greater" in refuse_revision("2026.10.27.2", ["2026.10.27.2"])
    assert "not greater" in refuse_revision("2026.11.16.1", ["2026.10.27.2", "2026.11.16.1"])
    assert "four dot-separated integers" in refuse_revision("2026.11.16", ["2026.10.27.2"])
    assert "cannot be compared" in refuse_revision("2026.11.16.1", ["2025.12.13-qiding"])


def test_choose_revision_guards(monkeypatch):
    script = load_script("choose_revision")
    answers = {
        "repos/o/r/releases/tags/v2026.11.16.1": None,
        "repos/o/r/git/ref/tags/v2026.11.16.1": None,
        "repos/o/r/releases/latest": None,
    }
    monkeypatch.setattr(script, "gh_api", lambda path: answers[path])
    monkeypatch.setattr(script, "release_revision", lambda run_number: f"2026.11.16.{run_number}")
    assert script.choose("", 1, "o/r") == "2026.11.16.1"
    assert script.choose(" 2026.11.16.1 ", 99, "o/r") == "2026.11.16.1"       # the input wins over the run number
    with pytest.raises(script.Refused, match="four dot-separated integers"):
        script.choose("2026.11.16", 1, "o/r")
    answers["repos/o/r/git/ref/tags/v2026.11.16.1"] = {"ref": "refs/tags/v2026.11.16.1"}
    with pytest.raises(script.Refused, match="tag v2026.11.16.1 already exists"):
        script.choose("", 1, "o/r")
    answers["repos/o/r/releases/tags/v2026.11.16.1"] = {"tag_name": "v2026.11.16.1"}
    with pytest.raises(script.Refused, match="release v2026.11.16.1 already exists"):
        script.choose("", 1, "o/r")


def test_choose_revision_reads_the_latest_release_from_its_index_assets(monkeypatch):
    script = load_script("choose_revision")
    monkeypatch.setattr(script, "gh_api", lambda path: None if "tags" in path else {"tag_name": "x", "assets": []})
    monkeypatch.setattr(script, "latest_revisions", lambda repo: ["2026.10.27.2", "2026.10.27.2"])
    assert script.choose("2026.10.27.3", 1, "o/r") == "2026.10.27.3"
    with pytest.raises(script.Refused, match="not greater"):
        script.choose("2026.10.27.2", 1, "o/r")


def test_latest_release_without_index_assets_stops_the_release(monkeypatch):
    script = load_script("choose_revision")
    monkeypatch.setattr(script, "gh_api", lambda path: {"tag_name": "build-1-1", "assets": [{"name": "a.zip"}]})
    with pytest.raises(script.Refused, match="its revision cannot be read"):
        script.latest_revisions("o/r")
    monkeypatch.setattr(script, "gh_api", lambda path: None)
    assert script.latest_revisions("o/r") == []


# --- release notes ----------------------------------------------------------------

STATS = [
    ZipStats("xiandai-yixue-cidian-yomitan.zip", "现代医学辞典", 10949, 20250, 8861, 417, 185, 4_680_000),
    ZipStats("xinbian-shiyong-yixue-cidian-yomitan.zip", "新编实用医学词典", 16622, 30531, 13225, 611, 32, 5_650_000),
]
OLD_BODY = """Dictionary revision **2026.10.27.2** (shown in Yomitan's dictionary list).

| Dictionary | Terms | Images | ZIP | Asset |
| --- | ---: | ---: | ---: | --- |
| 现代医学辞典 | 10,972 | 185 | 4.30 MB | `xiandai-yixue-cidian-yomitan.zip` |
| 新编实用医学词典 | 16,695 | 32 | 5.04 MB | `xinbian-shiyong-yixue-cidian-yomitan.zip` |
"""
COMMITS = [
    {"message": "Add traditional lookup\n\nbody", "parents": 1},
    {"message": "Merge pull request #3 from x/y", "parents": 2},
    {"message": "Merge branch 'main' into topic", "parents": 1},
    {"message": "Read 多音字 from CC-CEDICT", "parents": 1},
]


def test_delta():
    assert delta(20250, 10972) == "20,250 (+9,278)"
    assert delta(185, 185) == "185 (same)"
    assert delta(10949, None) == "10,949 (new)"
    assert delta(900, 1000) == "900 (-100)"


def test_counts_are_read_back_from_the_notes_this_module_writes():
    body = release_notes("2026.11.16.1", STATS)
    assert previous_counts(body) == {
        STATS[0].file: {"entries": 10949, "terms": 20250, "traditional": 8861, "lookup_only": 417, "images": 185},
        STATS[1].file: {"entries": 16622, "terms": 30531, "traditional": 13225, "lookup_only": 611, "images": 32},
    }


def test_the_table_of_the_releases_before_is_read_for_what_it_has():
    assert previous_counts(OLD_BODY) == {STATS[0].file: {"terms": 10972, "images": 185},
                                         STATS[1].file: {"terms": 16695, "images": 32}}
    assert previous_counts("written by hand") == {}


def test_commit_subjects_drop_merges_and_keep_the_order():
    assert commit_subjects(COMMITS) == ["Add traditional lookup", "Read 多音字 from CC-CEDICT"]
    assert commit_subjects([]) == []
    assert commit_subjects(None) is None


def test_changes_since_the_old_format():
    lines = changes_since({"tagName": "build-40602930225-1", "body": OLD_BODY}, STATS, COMMITS, "o/r", "v2026.11.16.1")
    text = "\n".join(lines)
    assert lines[1] == "## Changes since build-40602930225-1"
    assert "| `xiandai-yixue-cidian-yomitan.zip` | 10,949 (new) | 20,250 (+9,278) | 8,861 (new) | 417 (new) | 185 (same) |" in text
    assert "**Code:** 2 commits.\n- Add traditional lookup\n- Read 多音字 from CC-CEDICT" in text
    assert lines[-1] == ("**Full Changelog**: [build-40602930225-1...v2026.11.16.1]"
                         "(https://github.com/o/r/compare/build-40602930225-1...v2026.11.16.1)")


def test_changes_since_a_release_with_the_new_table():
    previous = {"tagName": "v2026.11.16.1", "body": release_notes("2026.11.16.1", STATS)}
    now = [ZipStats(STATS[0].file, STATS[0].title, 10949, 20260, 8870, 418, 185, 1), STATS[1]]
    text = "\n".join(changes_since(previous, now, [COMMITS[0]], "o/r", "v2026.11.17.2"))
    assert "| 10,949 (same) | 20,260 (+10) | 8,870 (+9) | 418 (+1) | 185 (same) |" in text
    assert "| 16,622 (same) | 30,531 (same) | 13,225 (same) | 611 (same) | 32 (same) |" in text
    assert "**Code:** 1 commit.\n" in text


def test_commits_that_could_not_be_listed_are_left_out_not_reported_as_none():
    previous = {"tagName": "build-1-1", "body": OLD_BODY}
    failed = "\n".join(changes_since(previous, STATS, None, "o/r", "v2026.11.16.1"))
    assert "**Code:**" not in failed and "Full Changelog" in failed and "(+9,278)" in failed
    none = "\n".join(changes_since(previous, STATS, [], "o/r", "v2026.11.16.1"))
    assert "**Code:** no commits; the same code as the previous release." in none


def test_parts_that_cannot_be_worked_out_are_left_out():
    assert changes_since(None, STATS, COMMITS, "o/r", "v1.2.3.4") == []
    assert changes_since({}, STATS, COMMITS, "o/r", "v1.2.3.4") == []
    by_hand = "\n".join(changes_since({"tagName": "v0", "body": "written by hand"}, STATS, None, None, None))
    assert by_hand == ""                                    # no table, no commits, no link: no section
    no_table = "\n".join(changes_since({"tagName": "v0", "body": "written by hand"}, STATS, COMMITS, "o/r", "v1.2.3.4"))
    assert "| file |" not in no_table and "**Code:** 2 commits." in no_table


def test_long_commit_lists_are_cut_at_forty():
    commits = [{"message": f"commit {n}", "parents": 1} for n in range(45)]
    lines = changes_since({"tagName": "v0", "body": ""}, STATS, commits, None, None)
    assert "**Code:** 45 commits." in lines
    assert lines.count("- commit 39") == 1 and "- commit 40" not in lines and "- … and 5 more" in lines


def test_release_notes_keep_the_revision_line_the_import_sentence_and_the_attribution():
    notes = release_notes("2026.11.16.1", STATS, previous={"tagName": "build-1-1", "body": OLD_BODY}, commits=COMMITS,
                          repo="o/r", cedict_date="2026-11-10T08:36:22Z")
    lines = notes.splitlines()
    assert lines[0] == "Dictionary revision **2026.11.16.1** (shown in Yomitan's dictionary list)."
    assert "| `xiandai-yixue-cidian-yomitan.zip` | 现代医学辞典 | 10,949 | 20,250 | 8,861 | 417 | 185 | 4.68 MB |" in lines
    assert any(line.startswith("Import the ZIP into Yomitan.") and "Check for updates" in line for line in lines)
    assert lines[-1] == "Readings partly from [CC-CEDICT](https://cc-cedict.org/), CC BY-SA 4.0. Export of 2026-11-10."
    assert notes.index("## Changes since") < notes.index("Import the ZIP")


def test_a_release_is_not_compared_with_itself():
    notes = release_notes("2026.11.16.1", STATS, previous={"tagName": "v2026.11.16.1", "body": OLD_BODY}, commits=[])
    assert "Changes since" not in notes


# --- the script that assembles a release -----------------------------------------

def test_prepare_release_end_to_end(tmp_path):
    dist = ROOT / "dist"
    if not all((dist / dictionary.archive).exists() and (dist / dictionary.report).exists()
               for dictionary in DICTIONARIES.values()):
        pytest.skip("dictionaries not built")
    (tmp_path / "previous.json").write_text(json.dumps({"tagName": "build-1-1", "body": OLD_BODY}), encoding="utf-8")
    command = [sys.executable, str(SCRIPTS / "prepare_release.py"), "--dist", str(dist), "--output", str(tmp_path / "out"),
               "--previous", str(tmp_path / "previous.json"), "--commits", str(tmp_path / "missing.json"), "--repo", "o/r"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    revision = result.stdout.strip().removeprefix("revision=")
    check_revision(revision)
    out = tmp_path / "out"
    names = sorted(path.name for path in out.iterdir())
    assert names == sorted(["NOTES.md", "SHA256SUMS.txt"] + [name for dictionary in DICTIONARIES.values()
                                                             for name in (dictionary.archive, dictionary.index, dictionary.report)])
    notes = (out / "NOTES.md").read_text(encoding="utf-8")
    assert f"**Full Changelog**: [build-1-1...v{revision}]" in notes
    assert "**Code:**" not in notes                         # no commits file: left out
    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert len(sums) == 6 and all(len(line.split("  ")[0]) == 64 for line in sums)
    for dictionary in DICTIONARIES.values():
        index = json.loads((out / dictionary.index).read_text(encoding="utf-8"))
        assert index["revision"] == revision and index["indexUrl"] == dictionary.index_url
    # an empty list is "no commits", which is said
    (tmp_path / "none.json").write_text("[]", encoding="utf-8")
    command[command.index("--commits") + 1] = str(tmp_path / "none.json")
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert "**Code:** no commits" in (out / "NOTES.md").read_text(encoding="utf-8")
