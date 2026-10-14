from app.snippets import make_snippet


LONG = (
    "The quick brown fox jumps over the lazy dog. " * 12
    + "Kafka consumer groups share partitions among members. "
    + "Padding sentence to push the match deep into the chunk. " * 8
)


def test_snippet_centers_on_matched_terms():
    out = make_snippet(LONG, ["consumer", "partitions"], width=120)
    assert "consumer" in out.lower()
    assert "partitions" in out.lower()
    assert len(out) <= 120 + 6  # allow for the ellipsis markers
    assert out.startswith("…")


def test_snippet_without_terms_uses_head():
    out = make_snippet(LONG, [], width=60)
    assert out.startswith("The quick brown fox")
    assert out.endswith("…")


def test_snippet_without_match_uses_head():
    out = make_snippet(LONG, ["zzzz"], width=60)
    assert out.startswith("The quick brown fox")


def test_snippet_empty_text():
    assert make_snippet("   ", ["anything"]) == ""
