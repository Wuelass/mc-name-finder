"""Normalize and rank word candidates without pretending a corpus is a dictionary."""

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


@dataclass
class Candidate:
    name: str
    languages: list[str] = field(default_factory=list)
    originals: list[str] = field(default_factory=list)
    score: float = 0.0
    lookup_status: str = "UNKNOWN"
    exact_status: str = "NOT_CHECKED"
    lookup_checked_at_utc: str | None = None
    exact_checked_at_utc: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_word(word: str) -> str | None:
    word = word.strip().lower().replace("œ", "oe").replace("æ", "ae")
    word = "".join(
        char for char in unicodedata.normalize("NFKD", word) if not unicodedata.combining(char)
    )
    return word if re.fullmatch(r"[a-z]+", word) else None


def rank(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (-c.score, len(c.name), c.name))


def generate(
    languages: list[str],
    min_length: int,
    max_length: int,
    min_frequency: float,
    limit: int | None = None,
    word_file: Path | None = None,
) -> list[Candidate]:
    words: dict[str, Candidate] = {}
    if word_file:
        sources = [("custom", word_file.read_text(encoding="utf-8-sig").splitlines())]
    else:
        sources = [(lang, iter_wordlist(lang, wordlist="best")) for lang in languages]
    for lang, originals in sources:
        for original in originals:
            if lang == "custom" and (not original.strip() or original.lstrip().startswith("#")):
                continue
            name = normalize_word(original)
            if not name or not min_length <= len(name) <= max_length:
                continue
            score = zipf_frequency(original, lang) if lang != "custom" else 0.0
            if lang != "custom" and score < min_frequency:
                continue
            candidate = words.setdefault(name, Candidate(name))
            if lang not in candidate.languages:
                candidate.languages.append(lang)
            if original not in candidate.originals:
                candidate.originals.append(original)
            candidate.score = max(candidate.score, score)
            if len(name) < 3:
                candidate.lookup_status = "IMPOSSIBLE_LENGTH"
    return rank(list(words.values()))[:limit]
