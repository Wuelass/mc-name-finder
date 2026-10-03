import pytest

from mc_name_finder.words import generate, normalize_word


@pytest.mark.parametrize(
    "word,expected",
    [
        ("été", "ete"),
        ("ÂME", "ame"),
        ("cœur", "coeur"),
        ("ŒUF", "oeuf"),
        (" aether ", "aether"),
        ("hello-world", None),
        ("l'ami", None),
        ("foo bar", None),
        ("x_3", None),
        ("猫", None),
        ("", None),
    ],
)
def test_normalization(word, expected):
    assert normalize_word(word) == expected


def test_custom_deduplication_and_impossible_length(tmp_path):
    words = tmp_path / "words.txt"
    words.write_text("# comment\nété\nete\nâme\nox\ninvalid-name\n\n", encoding="utf-8")
    rows = generate(["fr"], 2, 6, 8, word_file=words)
    assert [c.name for c in rows] == ["ox", "ame", "ete"]
    assert rows[0].lookup_status == "IMPOSSIBLE_LENGTH"
    assert rows[-1].originals == ["été", "ete"]


def test_real_wordfreq_source_has_expected_common_word():
    rows = generate(["en"], 3, 3, 5)
    assert "the" in {c.name for c in rows}
    assert all(c.score >= 5 and len(c.name) == 3 for c in rows)


def test_limit_and_languages_merge(monkeypatch):
    monkeypatch.setattr("mc_name_finder.words.iter_wordlist", lambda *a, **k: ["chat", "été"])
    monkeypatch.setattr("mc_name_finder.words.zipf_frequency", lambda word, lang: 4.0)
    rows = generate(["en", "fr"], 3, 6, 0, limit=1)
    assert rows[0].name == "ete"
    assert rows[0].languages == ["en", "fr"]
