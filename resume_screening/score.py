"""
Score a resume against a job description. Deliberately domain-agnostic:
nothing here assumes "engineering" — the same TF-IDF + keyword-overlap
approach works for a sales resume against a sales JD, an artist's portfolio
description against an arts JD, a finance resume against a finance JD, etc.,
because it's just text similarity plus explicit skill matching, not a
model trained on any one domain's resume structure.

Two components, combined:
1. Content similarity: TF-IDF cosine similarity between the full resume
   text and the full job description text. Captures overall relevance/
   phrasing overlap without needing a heavy embedding model download --
   fast enough to run on hundreds of resumes on a laptop, no GPU, no
   pretrained weights to fetch. (If you have time later, swap this for
   sentence-transformers embeddings for better semantic matching across
   phrasing differences -- same interface, better quality, slower/heavier.)
2. Skill-keyword overlap: an explicit, HR-provided list of required/
   preferred skills for THIS job (works the same whether the list is
   ["Salesforce", "cold outreach", "quota attainment"] for a sales role or
   ["Python", "AWS", "Kubernetes"] for an engineering role) matched against
   the resume text. This is what gives HR an interpretable "hit 6/9 required
   skills" number rather than only an opaque similarity score.

Final score = weighted blend of the two. Returned score is 0-100 so it
reads naturally to a non-technical HR user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

CONTENT_WEIGHT = 0.55
SKILL_WEIGHT = 0.45


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _content_similarity(resume_text: str, job_description: str) -> float:
    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    try:
        matrix = vectorizer.fit_transform([_normalize(resume_text), _normalize(job_description)])
    except ValueError:
        # One or both texts had nothing but stopwords after cleaning
        return 0.0
    sim = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
    return float(sim)


def _skill_overlap(resume_text: str, required_skills: list[str]) -> tuple[float, list[str], list[str]]:
    if not required_skills:
        return 0.0, [], []

    normalized_resume = _normalize(resume_text)
    matched, missing = [], []
    for skill in required_skills:
        # Word-boundary match so "R" doesn't match inside "Marketing", etc.
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, normalized_resume):
            matched.append(skill)
        else:
            missing.append(skill)

    ratio = len(matched) / len(required_skills)
    return ratio, matched, missing


@dataclass
class ResumeScore:
    candidate_id: str
    overall_score: float  # 0-100
    content_similarity: float  # 0-1, raw
    skill_match_ratio: float  # 0-1, raw
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)


def score_resume(candidate_id: str, resume_text: str, job_description: str, required_skills: list[str]) -> ResumeScore:
    content_sim = _content_similarity(resume_text, job_description)
    skill_ratio, matched, missing = _skill_overlap(resume_text, required_skills)

    overall = 100 * (CONTENT_WEIGHT * content_sim + SKILL_WEIGHT * skill_ratio)

    return ResumeScore(
        candidate_id=candidate_id,
        overall_score=round(overall, 1),
        content_similarity=round(content_sim, 3),
        skill_match_ratio=round(skill_ratio, 3),
        matched_skills=matched,
        missing_skills=missing,
    )
