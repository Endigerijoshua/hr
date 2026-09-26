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
import subprocess
import tempfile

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException

from .gaze import score_gaze_from_path
from .lipsync import score_lipsync
from .fusion import to_verification_session_payload
from ..plagiarism.similarity import score_similarity  # noqa: F401  (used by /plagiarism route below)

app = FastAPI(title="Anti-Gaming Verification Service")

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:3000")


def _extract_audio(video_path: str) -> str:
    wav_path = video_path + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", wav_path],
        check=True,
        capture_output=True,
    )
    return wav_path


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

        try:
            audio_path = _extract_audio(video_path)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=422, detail=f"could not extract audio: {e.stderr.decode()[:500]}")

        # Import here (not at module top) to avoid audio.py's librosa import
        # cost on every server boot if this route is rarely hit — fine to
        # move back to a top-level import if that's not a real concern.
        from .audio import score_audio

        gaze = score_gaze_from_path(video_path)
        lipsync = score_lipsync(video_path, audio_path)
        audio = score_audio(audio_path)

        payload = to_verification_session_payload(submission_id, gaze, lipsync, audio)

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
        "diagnostics": {"gaze": gaze, "lipsync": lipsync, "audio": audio},
    }


@app.get("/health")
def health():
    return {"status": "ok"}
