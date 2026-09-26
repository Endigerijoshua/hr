"""
Code-similarity / plagiarism check (secondary anti-gaming mechanism).

Hackathon-speed approach: normalize source (strip comments/whitespace/
identifier-case noise as much as is cheap), then compare against a corpus
(public repo snippets + other candidates' submissions) using shingled
MinHash for near-duplicate detection at scale, falling back to plain
difflib ratio for a small corpus where MinHash's approximation isn't worth
the complexity.

Same anti-gaming principle as verification: never auto-reject. High
similarity -> flagged for human review, exactly like a "flagged"
VerificationSession. A human decides whether it's plagiarism, a shared
boilerplate/starter template, or coincidental convergent solutions to a
common problem (this happens a lot with e.g. leetcode-style challenges —
don't let the paper claim this catches "plagiarism", it catches "high
textual similarity", which is a weaker and more honest claim).
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field

FLAG_THRESHOLD = 0.80  # similarity ratio above which a human should look

_COMMENT_PATTERNS = [
    re.compile(r"//.*?$", re.MULTILINE),
    re.compile(r"#.*?$", re.MULTILINE),
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r'""".*?"""', re.DOTALL),
]


def normalize_source(code: str) -> str:
    for pattern in _COMMENT_PATTERNS:
        code = pattern.sub("", code)
    # Collapse whitespace so formatting-only diffs don't inflate "novelty".
    code = re.sub(r"\s+", " ", code).strip()
    return code


def shingles(text: str, k: int = 8) -> set[str]:
    tokens = text.split(" ")
    return {" ".join(tokens[i:i + k]) for i in range(max(0, len(tokens) - k + 1))}


def jaccard_similarity(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def sequence_similarity(a: str, b: str) -> float:
    """Slower, more precise than Jaccard for smaller files — used as a
    tie-breaker / secondary confirmation, not the primary scan."""
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass
class SimilarityMatch:
    corpus_id: str
    corpus_label: str  # e.g. "public_repo:owner/name" or "candidate_submission:<id>"
    jaccard: float
    sequence_ratio: float | None = None


@dataclass
class SimilarityReport:
    submission_id: str
    flagged: bool
    matches: list[SimilarityMatch] = field(default_factory=list)


def score_similarity(submission_id: str, submission_code: str, corpus: dict[str, dict]) -> SimilarityReport:
    """
    corpus: {corpus_id: {"label": str, "code": str}}, e.g.
        {"gh:abc123": {"label": "public_repo:someorg/some-repo", "code": "..."}}
        {"sub:42":    {"label": "candidate_submission:42", "code": "..."}}
    """
    normalized_submission = normalize_source(submission_code)
    matches: list[SimilarityMatch] = []

    for corpus_id, entry in corpus.items():
        normalized_corpus_entry = normalize_source(entry["code"])
        j = jaccard_similarity(normalized_submission, normalized_corpus_entry)
        if j < 0.4:
            continue  # cheap first pass, skip the expensive sequence match
        seq = sequence_similarity(normalized_submission, normalized_corpus_entry)
        if max(j, seq) >= 0.5:
            matches.append(SimilarityMatch(corpus_id, entry["label"], round(j, 3), round(seq, 3)))

    matches.sort(key=lambda m: max(m.jaccard, m.sequence_ratio or 0), reverse=True)
    flagged = any(max(m.jaccard, m.sequence_ratio or 0) >= FLAG_THRESHOLD for m in matches)

    return SimilarityReport(submission_id=submission_id, flagged=flagged, matches=matches)


def content_hash(code: str) -> str:
    """Cheap exact-duplicate check to run before the expensive similarity
    scan — if this matches something in the corpus, skip straight to
    flagged=True, no need to shingle anything."""
    return hashlib.sha256(normalize_source(code).encode("utf-8")).hexdigest()
