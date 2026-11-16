"""Hanyu Pinyin lookup readings for headwords, from the best source available.

The source dictionaries carry no pronunciation data, so a reading is assembled
per headword, in this order of preference:

1. ``data/pinyin_overrides.tsv``: hand-checked ``term<TAB>reading`` lines. A
   line applies to the headword it names and to every longer headword that
   contains the term. A one-character line is weaker: it reads that character
   only where no word (an override, a CC-CEDICT word or one of pypinyin's own
   phrases) covers it.
2. CC-CEDICT, when it lists the headword (``data/cedict_readings.tsv``, a
   pinned table; see cedict.py). Of several readings, the one pypinyin's own
   guess points at, else the first one CC-CEDICT writes in lower case.
3. For the other headwords, each run of Han characters is read on its own:
   the run itself when CC-CEDICT lists it, else the CC-CEDICT words found
   inside it (the choice of non-overlapping words that covers the most
   characters), and pypinyin for whatever is left. A character CC-CEDICT gives
   exactly one reading for takes that reading instead of pypinyin's.

Format: lower-case syllables with tone marks and ``ü``, separated by spaces;
a neutral tone has no mark. Runs of other characters (digits, Latin, Greek,
roman numerals, punctuation) are kept verbatim in place, so a reading lines up
with its headword; quotation marks, brackets and middle dots are dropped.
A headword without Han characters has no reading.
"""
from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pypinyin import Style, lazy_pinyin, load_single_dict
from pypinyin.seg.simpleseg import seg as pypinyin_segments

from .cedict import TABLE_PATH, load_table

HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
OVERRIDES_PATH = Path(__file__).parent / "data" / "pinyin_overrides.tsv"
# Rare characters restored from private-use placeholders (see content.PUA_MAP).
load_single_dict({0x2C317: "hé", 0x2BAC7: "è"})

# Quotation marks and brackets around a headword part carry no pronunciation.
STRIPPED = frozenset("“”‘’\"'〔〕[]【】《》〈〉「」『』()（）·•")
MAX_WORD = 16                      # longest CC-CEDICT word looked for inside a headword

_MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
_TONE_COMBINING = {"̄", "́", "̌", "̀"}  # macron, acute, caron, grave
_NUMBERED = re.compile(r"^([A-Za-zü:]+)([1-5])$")

# How a Han character of a headword got its reading, strongest first.
OVERRIDE, CEDICT, CEDICT_WORD, CEDICT_CHAR, PYPINYIN_PHRASE, PYPINYIN = (
    "override", "cedict", "cedict-word", "cedict-char", "pypinyin-phrase", "pypinyin")
CONFIRMED = frozenset({OVERRIDE, CEDICT, CEDICT_WORD})


def normalize_pinyin(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\x00", ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Co" and ch not in STRIPPED)
    return re.sub(r"\s+", " ", value).strip()


def is_clean_reading(value: str) -> bool:
    """Character hygiene only: Latin letters present, no Han, control or private-use characters."""
    if not value:
        return True
    if value != normalize_pinyin(value):
        return False
    decomposed = unicodedata.normalize("NFD", value)
    return (
        any(ch in string.ascii_letters for ch in decomposed)
        and not HAN.search(value)
        and all(unicodedata.category(ch) not in {"Co", "Cc", "Cf", "Zl", "Zp"} for ch in decomposed)
    )


def strip_tones(value: str) -> str:
    """``zháo`` -> ``zhao``; the diaeresis of ü is kept."""
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize("NFC", "".join(ch for ch in decomposed if ch not in _TONE_COMBINING))


def syllable_to_marks(token: str) -> str | None:
    """A CC-CEDICT numbered syllable with tone marks, lower-case: ``zhao2`` ->
    ``zháo``, ``lu:4`` -> ``lǜ``, ``Qu1`` -> ``qū``, ``de5`` -> ``de``. ``None``
    for anything that is not a numbered syllable (a Latin letter, a comma, the
    ``xx5`` CC-CEDICT writes for an unknown reading)."""
    match = _NUMBERED.match(token)
    if not match:
        return None
    body = match.group(1).lower().replace("u:", "ü").replace("v", "ü")
    tone = int(match.group(2))
    if body == "xx" or ":" in body:
        return None
    if tone == 5:
        return body
    position = body.find("a")
    if position < 0:
        position = body.find("e")
    if position < 0:
        position = body.find("ou")
    if position < 0:
        vowels = [index for index, ch in enumerate(body) if ch in "iouü"]
        position = vowels[-1] if vowels else -1
    if position < 0:  # syllabic m / n / ng
        return unicodedata.normalize("NFC", body[0] + "̄́̌̀"[tone - 1] + body[1:])
    return body[:position] + _MARKS[body[position]][tone - 1] + body[position + 1:]


def cedict_syllables(pinyin: str) -> list[str]:
    """The syllables of one CC-CEDICT reading, tone-marked; other tokens (the
    letters of ``T xi4 bao1``, commas, middle dots) are left out."""
    return [marked for marked in map(syllable_to_marks, pinyin.split()) if marked is not None]


def split_runs(text: str) -> list[tuple[bool, str]]:
    """``17-α-羟化酶`` -> [(False, "17-α-"), (True, "羟化酶")]."""
    runs: list[tuple[bool, str]] = []
    for ch in text:
        is_han = bool(HAN.match(ch))
        if runs and runs[-1][0] == is_han:
            runs[-1] = (is_han, runs[-1][1] + ch)
        else:
            runs.append((is_han, ch))
    return runs


def han_characters(text: str) -> list[str]:
    return [ch for ch in text if HAN.match(ch)]


def assemble(headword: str, syllables: list[str]) -> str:
    """One syllable per Han character of ``headword``, its other runs verbatim in place."""
    remaining = iter(syllables)
    tokens: list[str] = []
    for is_han, run in split_runs(headword):
        tokens += [next(remaining) for _ in run] if is_han else [run]
    return normalize_pinyin(" ".join(token for token in map(normalize_pinyin, tokens) if token))


def load_overrides(path: Path | None = OVERRIDES_PATH) -> dict[str, str]:
    """``term<TAB>reading`` per line; blank lines and ``#`` comments are ignored."""
    overrides: dict[str, str] = {}
    if path is None or not Path(path).exists():
        return overrides
    with Path(path).open(encoding="utf-8-sig") as stream:  # tolerate the BOM some editors add
        for number, line in enumerate(stream, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(f"{path}:{number}: expected 'term<TAB>reading', got {line!r}")
            term, reading = unicodedata.normalize("NFC", parts[0].strip()), normalize_pinyin(" ".join(parts[1].split()))
            if not is_clean_reading(reading) or len(reading.split()) != len(han_characters(term)):
                raise ValueError(f"{path}:{number}: {reading!r} is not one tone-marked syllable per Han character of {term!r}")
            if term in overrides:
                raise ValueError(f"{path}:{number}: {term!r} is listed twice")
            overrides[term] = reading
    return overrides


@dataclass(frozen=True)
class Reading:
    reading: str
    source: str                                   # override | cedict | cedict-words | pypinyin | none
    # (character, syllable, how it was read) for every Han character of the headword
    characters: tuple[tuple[str, str, str], ...] = field(default=(), compare=False)


class Readings:
    """Callable: headword -> Reading."""

    def __init__(self, cedict_path: Path | None = TABLE_PATH, overrides_path: Path | None = OVERRIDES_PATH):
        self.overrides = load_overrides(overrides_path)
        table = load_table(cedict_path) if cedict_path else None
        self.cedict_date = table.export_date if table else ""
        # headword -> candidate readings as syllable lists, lower-case ones first:
        # the capitalised ones are proper nouns and surnames (单 [Shan4])
        self.listed: dict[str, list[list[str]]] = {}
        # Han-only words of two or more characters -> their candidates, for words inside a headword
        self.words: dict[str, list[list[str]]] = {}
        # characters CC-CEDICT gives exactly one reading for
        self.characters: dict[str, str] = {}
        for headword, numbered in (table.readings.items() if table else ()):
            han = han_characters(headword)
            lower: list[list[str]] = []
            upper: list[list[str]] = []
            for pinyin in numbered:
                syllables = cedict_syllables(pinyin)
                # one syllable per character; an erhua 儿 written as a bare r does not qualify
                if len(syllables) != len(han) or "r" in syllables:
                    continue
                bucket = upper if pinyin[:1].isupper() else lower
                if syllables not in lower and syllables not in upper:
                    bucket.append(syllables)
            candidates = lower + upper
            if not candidates:
                continue
            self.listed[headword] = candidates
            if len(han) == len(headword):
                if len(headword) >= 2:
                    self.words[headword] = candidates
                elif len({strip_case for (strip_case,) in candidates}) == 1:
                    self.characters[headword] = candidates[0][0]
        self._override_words = {term: reading.split() for term, reading in self.overrides.items()
                                if len(term) >= 2 and len(han_characters(term)) == len(term)}
        # a one-character line: the reading of that character wherever no word covers it
        self._override_characters = {term: reading for term, reading in self.overrides.items()
                                     if len(term) == 1 and HAN.match(term)}
        self._cache: dict[str, Reading] = {}

    # --- pypinyin ---------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=200_000)
    def _pypinyin(run: str) -> tuple[tuple[str, ...], tuple[bool, ...]]:
        """(pypinyin's syllables for a run of Han characters; per character,
        whether one of pypinyin's own phrases covered it)."""
        syllables = tuple(normalize_pinyin(s) for s in lazy_pinyin(run, style=Style.TONE, v_to_u=True))
        if len(syllables) != len(run):
            raise ValueError(f"pypinyin returned {len(syllables)} syllables for {run!r}")
        in_phrase: list[bool] = []
        for segment in pypinyin_segments(run):
            in_phrase += [len(segment) > 1] * len(segment)
        if len(in_phrase) != len(run):
            in_phrase = [False] * len(run)
        return syllables, tuple(in_phrase)

    @staticmethod
    def _closest(candidates: list[list[str]], guess: tuple[str, ...]) -> list[str]:
        """The candidate a guess points at: the same reading, else the same
        syllables with other tones, else the first candidate."""
        if len(candidates) == 1:
            return candidates[0]
        wanted = list(guess)
        if wanted in candidates:
            return wanted
        bare = [strip_tones(s) for s in wanted]
        for candidate in candidates:
            if [strip_tones(s) for s in candidate] == bare:
                return candidate
        return candidates[0]

    # --- one run of Han characters ------------------------------------------------

    def _words_in(self, run: str, lexicon: dict[str, list], taken: list[bool]) -> list[tuple[int, int]]:
        """Non-overlapping lexicon words inside ``run`` as (start, end), chosen to
        cover the most free characters, then to be the fewest, then leftmost-longest."""
        size = len(run)
        # best[i]: (characters covered, -words, choice) for run[i:]
        best: list[tuple[int, int]] = [(0, 0)] * (size + 1)
        choice: list[int] = [0] * (size + 1)          # 0: skip the character; n: take a word of n characters
        for start in range(size - 1, -1, -1):
            chosen: tuple[int, int] | None = None
            if not taken[start]:
                for length in range(min(MAX_WORD, size - start), 1, -1):
                    if any(taken[start:start + length]) or run[start:start + length] not in lexicon:
                        continue
                    covered, words = best[start + length]
                    candidate = (covered + length, words - 1)
                    if chosen is None or candidate > chosen:   # strict: on a tie the longer word, tried first, stays
                        chosen, choice[start] = candidate, length
            # a word that starts here wins a tie against skipping the character: leftmost first
            if chosen is None or best[start + 1] > chosen:
                chosen, choice[start] = best[start + 1], 0
            best[start] = chosen
        found: list[tuple[int, int]] = []
        position = 0
        while position < size:
            if choice[position]:
                found.append((position, position + choice[position]))
                position += choice[position]
            else:
                position += 1
        return found

    def _read_run(self, run: str) -> list[tuple[str, str, str]]:
        guess, in_phrase = self._pypinyin(run)
        if run in self._override_words:
            return [(ch, s, OVERRIDE) for ch, s in zip(run, self._override_words[run])]
        if run in self.words:
            return [(ch, s, CEDICT) for ch, s in zip(run, self._closest(self.words[run], guess))]
        result: list[tuple[str, str, str] | None] = [None] * len(run)
        taken = [False] * len(run)
        for start, end in self._words_in(run, self._override_words, taken):
            for offset, syllable in enumerate(self._override_words[run[start:end]]):
                result[start + offset], taken[start + offset] = (run[start + offset], syllable, OVERRIDE), True
        for start, end in self._words_in(run, self.words, taken):
            word = run[start:end]
            chosen = self._closest(self.words[word], self._pypinyin(word)[0])
            for offset, syllable in enumerate(chosen):
                result[start + offset], taken[start + offset] = (run[start + offset], syllable, CEDICT_WORD), True
        for index, ch in enumerate(run):
            if result[index] is None:
                if in_phrase[index]:
                    result[index] = (ch, guess[index], PYPINYIN_PHRASE)
                elif ch in self._override_characters:
                    result[index] = (ch, self._override_characters[ch], OVERRIDE)
                elif ch in self.characters and self.characters[ch] != guess[index]:
                    result[index] = (ch, self.characters[ch], CEDICT_CHAR)
                else:
                    result[index] = (ch, guess[index], PYPINYIN)
        return result  # type: ignore[return-value]

    # --- a headword -----------------------------------------------------------------

    def __call__(self, headword: str) -> Reading:
        hit = self._cache.get(headword)
        if hit is None:
            hit = self._cache[headword] = self._read(headword)
        return hit

    def _read(self, headword: str) -> Reading:
        han = han_characters(headword)
        if not han:
            return Reading("", "none")
        if headword in self.overrides:
            syllables = self.overrides[headword].split()
            return Reading(assemble(headword, syllables), OVERRIDE,
                           tuple((ch, s, OVERRIDE) for ch, s in zip(han, syllables)))
        runs = [run for is_han, run in split_runs(headword) if is_han]
        if headword in self.listed:
            guess = tuple(s for run in runs for s in self._pypinyin(run)[0])
            syllables = self._closest(self.listed[headword], guess)
            return Reading(assemble(headword, syllables), CEDICT,
                           tuple((ch, s, CEDICT) for ch, s in zip(han, syllables)))
        characters = tuple(item for run in runs for item in self._read_run(run))
        sources = {how for _, _, how in characters}
        if sources <= {OVERRIDE}:
            source = OVERRIDE
        elif sources <= {CEDICT}:
            source = CEDICT
        elif sources & {OVERRIDE, CEDICT, CEDICT_WORD, CEDICT_CHAR}:
            source = "cedict-words"
        else:
            source = "pypinyin"
        return Reading(assemble(headword, [s for _, s, _ in characters]), source, characters)


@lru_cache(maxsize=1)
def default_readings() -> Readings:
    return Readings()


def reading_for(expression: str) -> str:
    """The pinyin reading, or ``""`` when the headword has no Han characters."""
    return default_readings()(expression).reading
