"""
Score every resume in a folder against a job description, rank them, and
cut the top N% (15-20% per the target) as "shortlisted" -- the core
workload-reduction deliverable: HR gets a short list instead of reading
every application.

Run:
    python -m resume_screening.shortlist \\
        --resumes-dir path/to/resumes \\
        --job-description path/to/jd.txt \\
        --skills "Python,AWS,Kubernetes" \\
        --shortlist-percent 15 \\
        --out shortlist.json

--skills works the same for any domain -- pass whatever the JD actually
needs: --skills "Salesforce,cold outreach,quota attainment" for a sales
role, --skills "Adobe Creative Suite,portfolio curation,color theory" for
an arts role, --skills "financial modeling,GAAP,Excel" for finance, etc.
Nothing in this script is engineering-specific.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extract_text import extract_text
from .score import score_resume

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def run(resumes_dir: Path, job_description_path: Path, skills: list[str], shortlist_percent: float) -> dict:
    job_description = job_description_path.read_text(encoding="utf-8", errors="ignore")

    resume_files = sorted(p for p in resumes_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    if not resume_files:
        raise ValueError(f"No supported resume files found in {resumes_dir} (looked for {SUPPORTED_EXTENSIONS})")

    scores = []
    errors = []
    for path in resume_files:
        try:
            text = extract_text(str(path))
            result = score_resume(candidate_id=path.stem, resume_text=text, job_description=job_description, required_skills=skills)
            scores.append(result)
        except Exception as e:  # noqa: BLE001 -- one bad resume shouldn't kill the whole batch
            errors.append({"file": str(path), "error": str(e)})

    scores.sort(key=lambda r: r.overall_score, reverse=True)

    cutoff_index = max(1, round(len(scores) * shortlist_percent / 100))
    shortlisted = scores[:cutoff_index]
    rest = scores[cutoff_index:]

    report = {
        "job_description_file": str(job_description_path),
        "required_skills": skills,
        "total_candidates": len(scores),
        "shortlist_percent_requested": shortlist_percent,
        "shortlisted_count": len(shortlisted),
        "shortlisted": [vars(r) for r in shortlisted],
        "not_shortlisted": [vars(r) for r in rest],
        "errors": errors,
    }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resumes-dir", required=True, type=Path)
    parser.add_argument("--job-description", required=True, type=Path)
    parser.add_argument("--skills", default="", help="comma-separated list of required/preferred skills for this job")
    parser.add_argument("--shortlist-percent", type=float, default=17.5, help="target %% to shortlist, e.g. 15-20")
    parser.add_argument("--out", type=Path, default=Path("shortlist.json"))
    args = parser.parse_args()

    skills_list = [s.strip() for s in args.skills.split(",") if s.strip()]
    report = run(args.resumes_dir, args.job_description, skills_list, args.shortlist_percent)

    args.out.write_text(json.dumps(report, indent=2))
    print(f"Scored {report['total_candidates']} candidates.")
    print(f"Shortlisted {report['shortlisted_count']} ({args.shortlist_percent}% target) -> {args.out}")
    if report["errors"]:
        print(f"WARNING: {len(report['errors'])} files failed to parse -- see 'errors' in {args.out}")
