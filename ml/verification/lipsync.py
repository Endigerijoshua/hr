"""
Lip-sync consistency check.

Proxy approach (fast enough to build in a hackathon, no pretrained
lip-sync-specific model required): track the candidate's mouth-aspect-ratio
(MAR) over time from face-mesh landmarks, extract the speech amplitude
envelope from the audio track, resample both to a common frame rate, and
compute their cross-correlation. If someone off-camera is answering while
the candidate mouths along loosely (or says nothing at all), mouth movement
and detected speech energy decouple and correlation drops.

Same convention as gaze.py: score in [0, 1], 1.0 = consistent/honest.
"""

from __future__ import annotations

import numpy as np
import cv2
import mediapipe as mp
import librosa

# Mouth landmark indices (MediaPipe FaceMesh, outer lip ring)
MOUTH_TOP = 13
MOUTH_BOTTOM = 14
MOUTH_LEFT = 61
MOUTH_RIGHT = 291

MIN_CORRELATION_FOR_FULL_SCORE = 0.55
MIN_CORRELATION_FOR_ZERO_SCORE = 0.05


def _mouth_aspect_ratio(landmarks) -> float:
    top = np.array([landmarks[MOUTH_TOP].x, landmarks[MOUTH_TOP].y])
    bottom = np.array([landmarks[MOUTH_BOTTOM].x, landmarks[MOUTH_BOTTOM].y])
    left = np.array([landmarks[MOUTH_LEFT].x, landmarks[MOUTH_LEFT].y])
    right = np.array([landmarks[MOUTH_RIGHT].x, landmarks[MOUTH_RIGHT].y])
    width = np.linalg.norm(right - left)
    if width < 1e-6:
        return 0.0
    return float(np.linalg.norm(top - bottom) / width)


def _extract_mouth_series(video_path: str, fps_target: float = 10.0) -> tuple[np.ndarray, float]:
    cap = cv2.VideoCapture(video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps_target))

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5
    )

    mar_series = []
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = face_mesh.process(rgb)
                if result.multi_face_landmarks:
                    mar_series.append(_mouth_aspect_ratio(result.multi_face_landmarks[0].landmark))
                else:
                    mar_series.append(np.nan)
            i += 1
    finally:
        cap.release()
        face_mesh.close()

    return np.array(mar_series, dtype=float), src_fps / step


def _extract_audio_envelope(audio_path: str, fps_target: float = 10.0) -> np.ndarray:
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    hop_length = max(1, round(sr / fps_target))
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    return rms


def score_lipsync(video_path: str, audio_path: str) -> dict:
    """
    video_path: video-only or combined file readable by cv2 for frames.
    audio_path: audio track (can be the same file if it has an audio stream
        and you extract it upstream with ffmpeg before calling this).
    """
    mar_series, mouth_fps = _extract_mouth_series(video_path)
    audio_env = _extract_audio_envelope(audio_path, fps_target=mouth_fps)

    # Align lengths
    n = min(len(mar_series), len(audio_env))
    if n < 5:
        return {"score": 0.5, "correlation": None, "note": "insufficient signal to score"}

    mar = mar_series[:n]
    env = audio_env[:n]

    valid = ~np.isnan(mar)
    if valid.sum() < 5:
        return {"score": 0.5, "correlation": None, "note": "face not detected for most of clip"}

    mar = mar[valid]
    env = env[valid]

    if np.std(mar) < 1e-6 or np.std(env) < 1e-6:
        # No mouth movement or no audio energy at all — can't correlate
        # meaningfully. Flag rather than guess.
        return {"score": 0.3, "correlation": 0.0, "note": "flat signal (no movement or no audio)"}

    correlation = float(np.corrcoef(mar, env)[0, 1])
    correlation = max(0.0, correlation)  # negative correlation is not "extra honest"

    if correlation >= MIN_CORRELATION_FOR_FULL_SCORE:
        score = 1.0
    elif correlation <= MIN_CORRELATION_FOR_ZERO_SCORE:
        score = 0.0
    else:
        span = MIN_CORRELATION_FOR_FULL_SCORE - MIN_CORRELATION_FOR_ZERO_SCORE
        score = (correlation - MIN_CORRELATION_FOR_ZERO_SCORE) / span

    return {"score": round(float(score), 3), "correlation": round(correlation, 3)}
