import pytest

from app.chunking import split_text


def test_empty_and_whitespace_give_no_chunks():
    assert split_text("") == []
    assert split_text("   \n\n  ") == []
    assert split_text("-----") == []  # no word characters -> nothing worth indexing


def test_short_text_is_one_chunk():
    assert split_text("hello world", size=100, overlap=10) == ["hello world"]


def test_long_text_is_split_with_overlap_and_loses_nothing():
    words = [f"word{i}" for i in range(400)]
    text = " ".join(words)
    chunks = split_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # every word appears in at least one chunk
    joined = " ".join(chunks)
    assert all(w in joined for w in words)
    # consecutive chunks share some text (overlap)
    assert set(chunks[0].split()) & set(chunks[1].split())


def test_prefers_paragraph_boundaries():
    para1 = "First paragraph. " * 20
    para2 = "Second paragraph. " * 20
    chunks = split_text(para1.strip() + "\n\n" + para2.strip(), size=400, overlap=20)
    assert chunks[0].endswith("paragraph.")


def test_terminates_on_unbroken_text():
    chunks = split_text("x" * 5000, size=100, overlap=20)
    assert len(chunks) > 1


def test_rejects_bad_overlap():
    with pytest.raises(ValueError):
        split_text("abc", size=10, overlap=10)
