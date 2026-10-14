"""Dependency-free lexical search helpers: stemming, typo correction and BM25.

The vector store handles meaning; this handles the exact-words side so results
don't depend only on embedding quality. It is intentionally lightweight (no
model download) and deterministic, which also makes it easy to unit test.
"""
import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")

# Suffix rules, longest/most specific first. Applied at most twice per token so
# that e.g. "partitioned" -> "partition" -> "partit" lines up with "partitions".
_SUFFIXES = [
    ("ational", "ate"),
    ("ization", "ize"),
    ("fulness", "ful"),
    ("ousness", "ous"),
    ("iveness", "ive"),
    ("tional", "tion"),
    ("tions", "t"),
    ("sions", "s"),
    ("ments", ""),
    ("nesses", ""),
    ("ingly", ""),
    ("edly", ""),
    ("ance", ""),
    ("ence", ""),
    ("tion", "t"),
    ("sion", "s"),
    ("ment", ""),
    ("ness", ""),
    ("iers", "y"),
    ("ier", "y"),
    ("ies", "y"),
    ("ied", "y"),
    ("ing", ""),
    ("ers", ""),
    ("est", ""),
    ("ive", ""),
    ("ful", ""),
    ("ous", ""),
    ("ly", ""),
    ("er", ""),
    ("ed", ""),
    ("s", ""),
]


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def stem(word: str) -> str:
    if len(word) <= 3:
        return word
    for _ in range(2):
        for suffix, repl in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: len(word) - len(suffix)] + repl
                break
        else:
            break
    return word


def terms(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


def _levenshtein(a: str, b: str, max_dist: int) -> int:
    """Edit distance, bailing out early once it exceeds ``max_dist``."""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            best = min(best, cur[j])
        if best > max_dist:
            return max_dist + 1
        prev = cur
    return prev[len(b)]


def correct_terms(qterms: list[str], vocab: set[str]) -> list[str]:
    """Fix likely typos in query terms against the corpus vocabulary.

    Only stems longer than a few characters are corrected, and only if a close
    neighbour exists within edit distance 1 (short words) or 2 (longer words).
    """
    if not vocab:
        return list(qterms)
    fixed: list[str] = []
    for term in qterms:
        if term in vocab or len(term) < 5:
            fixed.append(term)
            continue
        max_dist = 2 if len(term) >= 8 else 1
        best, best_dist = term, max_dist + 1
        for cand in vocab:
            if abs(len(cand) - len(term)) > max_dist:
                continue
            d = _levenshtein(term, cand, max_dist)
            if d < best_dist:
                best, best_dist = cand, d
                if d == 1:
                    break
        fixed.append(best)
    return fixed


class BM25:
    """Okapi BM25 over a fixed corpus of token lists."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n = len(docs)
        self.tf = [Counter(d) for d in docs]
        self.length = [len(d) for d in docs]
        self.avg_len = (sum(self.length) / self.n) if self.n else 0.0
        self.df: Counter[str] = Counter()
        for doc in docs:
            self.df.update(set(doc))
        self.vocab = set(self.df)

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, qterms: list[str]) -> list[float]:
        out = [0.0] * self.n
        for term in set(qterms):
            idf = self.idf(term)
            if idf <= 0:
                continue
            for i, tf in enumerate(self.tf):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                norm = self.k1 * (1 - self.b + self.b * self.length[i] / (self.avg_len or 1))
                out[i] += idf * freq * (self.k1 + 1) / (freq + norm)
        return out
