# Verifiable Proof-of-Work Engineering Discovery & Hiring Platform

HR Tech / Developer Platforms & Talent Verification hackathon project.
Replacing resumes with verifiable, reviewed, ranked engineering work.

## The idea

1. **Candidate** browses challenges, builds, submits a repo + ADR, gets
   reviewed, accumulates ranking.
2. **Reviewer** scores submissions against a structured rubric.
3. **Recruiter** discovers candidates via ranking/search, reaches out.

The trust problem this whole project exists to solve: how do you know a
submission is the candidate's own unassisted work? That's what the
anti-gaming layer (Section below) is for.

## Repo layout & who owns what

This is being built by 4 AI coding agents (via OpenCode) on one shared
codebase, each with a defined scope:

| Path | Owns | Scope |
|---|---|---|
| `/app`, `/pages`, `/lib` (Next.js) | teammate TODO | Backend: REST API under `/api/*`, `lib/ranking.ts` |
| `/ml/verification`, `/ml/plagiarism`, `/docs/anti-gaming-paper.md` | this scope | Anti-gaming: live verification (gaze/lip-sync/audio), plagiarism check |
| TODO | teammate TODO | Reviewer rubric + reviewer trust scoring |
| TODO | teammate TODO | Candidate/recruiter frontend, ranking search/discovery |

> Fill in the TODOs once the other three agents' scopes are pushed — this
> table is the single place a new contributor (or a judge) should be able
> to look to understand who built what.

## Core entities (shared contract — do not rename fields)

- `Submission`: `id, candidateId, challengeId, repoUrl, status`
- `VerificationSession`: `submissionId, gazeScore(0-1), lipSyncScore(0-1),
  audioScore(0-1), result("pass"|"flagged"|"fail"), reviewedByHR(bool)`
- `RankingScore.breakdown.verificationMultiplier` reads `VerificationSession.result`
  — 1.2x pass, 1.0x unverified, 0.5x flagged-unresolved.

## Setup

**Backend (Next.js)**
```bash
npm install
npm run dev
```

**ML / anti-gaming (Python)**
```bash
pip install -r requirements.txt
uvicorn ml.verification.service:app --reload --port 8001
```
See `README-ml-anti-gaming.md` for the full verification-pipeline setup,
dataset prep, and evaluation steps.

## Demo flow (definition of done)

Candidate submits → ML curates/assigns a challenge → candidate does a live
verification session (or a scripted/simulated one if live camera capture
doesn't land in time) → session posts a real result to the backend →
ranking visibly updates → recruiter can find the candidate via
ranking/search.
