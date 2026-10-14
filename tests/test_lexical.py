from app.lexical import BM25, correct_terms, stem, terms, tokenize


def test_tokenize_and_terms():
    assert tokenize("Hello, World! 42") == ["hello", "world", "42"]
    assert terms("Hello, World!") == [stem("hello"), stem("world")]


def test_stem_merges_inflections():
    assert stem("consumer") == stem("consumers") == stem("consuming")
    assert stem("partition") == stem("partitions") == stem("partitioned")


def test_stem_leaves_short_words():
    assert stem("cat") == "cat"
    assert stem("the") == "the"


def test_correct_terms_fixes_typos_against_vocab():
    vocab = {"consum", "partit", "kafka"}
    fixed = correct_terms(["consumm", "partit", "kafka"], vocab)
    assert fixed == ["consum", "partit", "kafka"]


def test_correct_terms_ignores_short_and_known_words():
    vocab = {"consum", "partit"}
    assert correct_terms(["cat", "consum"], vocab) == ["cat", "consum"]
    assert correct_terms(["anything"], set()) == ["anything"]


def test_bm25_prefers_more_frequent_terms():
    index = BM25([["cat", "dog"], ["cat", "cat", "bird"]])
    scores = index.scores(["cat"])
    assert scores[1] > scores[0] > 0


def test_bm25_ignores_unknown_terms():
    index = BM25([["cat", "dog"], ["cat", "bird"]])
    assert index.scores(["zebra"]) == [0.0, 0.0]
