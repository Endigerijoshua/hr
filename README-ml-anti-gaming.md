# ML / Anti-Gaming — Setup & Notes

Your scope: `/ml/verification`, `/ml/plagiarism`, `/docs/anti-gaming-paper.md`.

## Install

```bash
pip install -r requirements.txt
# ffmpeg must be on PATH (used to pull audio out of the recorded clip)
```

## Run the verification service

```bash
uvicorn ml.verification.service:app --reload --port 8001
```

Then from the frontend/orchestrator, `POST` a `multipart/form-data` request
to `http://localhost:8001/verify` with fields:
- `submission_id`: string
- `clip`: the recorded video file (webcam + mic, muxed)

It scores gaze / lip-sync / audio, fuses them, and forwards the exact
`VerificationSession` payload to `${BACKEND_BASE_URL}/api/verification-sessions`
(set `BACKEND_BASE_URL` env var; defaults to `http://localhost:3000`).

## Files

| File | What it does |
|---|---|
| `ml/verification/gaze.py` | MediaPipe iris tracking → off-screen-gaze ratio → score |
| `ml/verification/lipsync.py` | Mouth-aspect-ratio vs audio-envelope correlation → score |
| `ml/verification/audio.py` | Pitch-track deviation → second-voice detection → score |
| `ml/verification/fusion.py` | Combines the three scores → `pass`/`flagged`/`fail` + `reviewedByHR` |
| `ml/verification/service.py` | FastAPI endpoint tying it together, posts to backend |
| `ml/verification/evaluate.py` | Runs the pipeline over a labeled clip set, prints confusion matrix + P/R/F1 |
| `ml/plagiarism/similarity.py` | Shingled-Jaccard + sequence-match corpus comparison |
| `docs/anti-gaming-paper.md` | The required paper (has TODOs for what you need from the backend teammate) |

## Before the demo, you need to:

1. **Record a handful of test clips** (~20–30 per `evaluate.py`'s docstring):
   some honest, some deliberately gamed (second person answering off-camera,
   reading from another screen, etc). Put them + `labels.json` next to
   `evaluate.py` and run `python -m ml.verification.evaluate` — this is
   the confusion matrix you report in the paper.
2. **Get the ranking formula weights** from whoever owns `lib/ranking.ts`
   and drop them into the paper — don't guess at them.
3. **Sanity-check the fusion thresholds** (`fusion.py`) against your actual
   labeled clips instead of trusting the placeholder numbers — they're a
   starting point, not tuned values.
4. If live webcam capture doesn't land in time, a scripted/simulated demo
   (pre-recorded "honest" and "gamed" clips run through `/verify` live on
   stage) satisfies the definition of done.
