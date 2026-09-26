"""
FastAPI service: run the verification pipeline on an uploaded/recorded clip
and POST the result to the Next.js backend's /api/verification-sessions.

Run: uvicorn ml.verification.service:app --reload --port 8001

For hackathon speed this accepts a single video file that has both video
and audio muxed together (e.g. an .mp4 from a webcam recording). Audio is
extracted to a temp .wav via ffmpeg before scoring — swap this for a live
WebRTC stream later if time allows; the scoring functions don't care where
the file came from.
"""

from __future__ import annotations

import os
import tempfile

import requests
from fastapi import FastAPI, UploadFile, File, Form

from .gaze import score_gaze_from_path
from .lipsync import score_lipsync
from .liveness import score_liveness_from_path
from .fusion import to_verification_session_payload
from ..plagiarism.similarity import score_similarity  # noqa: F401  (used by /plagiarism route below)

app = FastAPI(title="Anti-Gaming Verification Service")

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:3000")

# A scorer that can't run (missing model weights, missing SYNCNET_REPO_DIR, an
# OpenCV/torch version skew) must NOT take the whole request down. Fusion treats
# 0.5 as "no information" and routes the submission to human review, which is
# the correct outcome for an incomplete signal -- much better than a 500 that
# leaves the candidate with no verdict at all.
NEUTRAL = 0.5


def _safe(name: str, fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - deliberately broad; see note above
        return {
            "score": NEUTRAL,
            "error": f"{type(e).__name__}: {e}",
            "note": f"{name} scorer unavailable; defaulted to neutral {NEUTRAL} for human review",
        }


@app.post("/verify")
async def verify_submission(submission_id: str = Form(...), clip: UploadFile = File(...)):
    """
    Score a candidate's live-defense recording and forward the result to
    the backend. Returns the same payload that was POSTed, plus the
    backend's response, so the caller (frontend or orchestrator) can see
    both in one round trip.
    """
    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, clip.filename or "clip.mp4")
        with open(video_path, "wb") as f:
            f.write(await clip.read())

        # Import here (not at module top) to avoid audio.py's librosa import
        # cost on every server boot if this route is rarely hit — fine to
        # move back to a top-level import if that's not a real concern.
        from .audio import score_audio

        gaze = _safe("gaze", score_gaze_from_path, video_path)
        lipsync = _safe("lipsync", score_lipsync, video_path)
        audio = _safe("audio", score_audio, video_path)
        liveness = _safe("liveness", score_liveness_from_path, video_path)

        payload = to_verification_session_payload(submission_id, gaze, lipsync, audio, liveness)

    try:
        backend_resp = requests.post(
            f"{BACKEND_BASE_URL}/api/verification-sessions",
            json={k: v for k, v in payload.items() if not k.startswith("_")},
            timeout=10,
        )
        backend_status = backend_resp.status_code
        backend_body = backend_resp.json() if backend_resp.content else None
    except requests.RequestException as e:
        backend_status = None
        backend_body = {"error": str(e)}

    return {
        "sent_to_backend": payload,
        "backend_status": backend_status,
        "backend_response": backend_body,
        "diagnostics": {"gaze": gaze, "lipsync": lipsync, "audio": audio, "liveness": liveness},
    }


@app.get("/health")
def health():
    return {"status": "ok"}
