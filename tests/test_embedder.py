import math

from app.embedder import HashEmbedder


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_deterministic_and_normalized():
    e = HashEmbedder()
    v1 = e.embed(["Kafka consumer groups"])[0]
    v2 = e.embed(["Kafka consumer groups"])[0]
    assert v1 == v2
    assert len(v1) == e.dim
    assert math.isclose(sum(x * x for x in v1), 1.0, rel_tol=1e-9)


def test_related_text_scores_higher_than_unrelated():
    e = HashEmbedder()
    q, related, unrelated = e.embed([
        "how do consumer groups share partitions",
        "consumer groups split the partitions between consumers",
        "baking sourdough bread requires a mature starter",
    ])
    assert cosine(q, related) > cosine(q, unrelated)


def test_no_tokens_gives_zero_vector():
    assert not any(HashEmbedder().embed(["!!! ???"])[0])
