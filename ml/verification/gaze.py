"""
Gaze tracking / off-screen-look detection.

Uses MediaPipe FaceLandmarker to estimate, frame by frame, whether the
candidate's gaze is on-screen or has wandered off in a pattern consistent
with reading answers from another screen/device.

Convention used across this whole verification pipeline:
    score in [0, 1], where 1.0 = fully consistent with honest behavior,
    0.0 = strongly consistent with gaming behavior.
This lets fusion.py combine gaze/lipsync/audio scores the same way.

Note on the MediaPipe API: the legacy `mp.solutions.face_mesh.FaceMesh`
solution (and its `refine_landmarks=True` iris points) was removed in
MediaPipe 1.0, which is what an unpinned `mediapipe` in requirements.txt
resolves to today. This module uses the 1.0 Tasks API instead
(`mediapipe.tasks.python.vision.FaceLandmarker`), whose face_landmarker
model emits the same 478-point mesh -- including the iris points at 468-477
-- so the landmark indices and the scoring math below are unchanged. The
model bundle is fetched to ml/verification/models/face_landmarker.task.
"""

from __future__ import annotations

import os

import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

# MediaPipe iris landmark indices (468-477 block; face_landmarker emits these).
# Each iris is a center point (468 / 473) plus a 4-point ring. The ring must be
# paired with the eye corners of the SAME eye: 469-472 belongs to the eye whose
# corners are 33/133, and 474-477 to the eye whose corners are 362/263. The
# two rings used to be paired with the opposite eye's corners here, which put
# the iris ~2.5 eye-widths from the reference midpoint and pinned every frame
# as "off-screen".
LEFT_IRIS = [469, 470, 471, 472]
RIGHT_IRIS = [474, 475, 476, 477]
LEFT_EYE_CORNERS = (33, 133)
RIGHT_EYE_CORNERS = (362, 263)

_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "face_landmarker.task"
)

# How far the iris can drift from the eye-corner midpoint (as a fraction of
# eye width) before we count the frame as "gaze off-screen". Tuned loosely;
# this is exactly the kind of threshold that should be re-tuned against your
# labeled clips (see confusion_matrix.py) rather than trusted as-is.
OFF_SCREEN_RATIO_THRESHOLD = 0.35


class GazeTracker:
    def __init__(self, model_path: str = _MODEL_PATH):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"MediaPipe face_landmarker model bundle not found at {model_path}. "
                f"Download it from storage.googleapis.com/mediapipe-models/"
                f"face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            )
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def close(self):
        self._landmarker.close()

    def _iris_offset_ratio(self, landmarks, iris_idx, corner_idx) -> float | None:
        pts = np.array([[landmarks[i].x, landmarks[i].y] for i in iris_idx])
        iris_center = pts.mean(axis=0)
        c0 = np.array([landmarks[corner_idx[0]].x, landmarks[corner_idx[0]].y])
        c1 = np.array([landmarks[corner_idx[1]].x, landmarks[corner_idx[1]].y])
        eye_width = np.linalg.norm(c1 - c0)
        if eye_width < 1e-6:
            return None
        eye_mid = (c0 + c1) / 2
        offset = np.linalg.norm(iris_center - eye_mid) / eye_width
        return float(offset)

    def score_video(self, frames: list[np.ndarray]) -> dict:
        """
        frames: list of BGR frames (as read by cv2.VideoCapture).
        Returns {"score": float, "off_screen_ratio": float, "frames_scored": int}
        """
        off_screen_flags = []

        for i, frame in enumerate(frames):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            # VIDEO mode requires strictly increasing timestamps; we don't
            # track real fps here, so use a synthetic monotonic one.
            result = self._landmarker.detect_for_video(mp_image, i * 33)
            if not result.face_landmarks:
                # No face detected at all is itself suspicious (candidate
                # stepped out of frame) — treat as off-screen for this frame.
                off_screen_flags.append(True)
                continue

            landmarks = result.face_landmarks[0]
            left = self._iris_offset_ratio(landmarks, LEFT_IRIS, LEFT_EYE_CORNERS)
            right = self._iris_offset_ratio(landmarks, RIGHT_IRIS, RIGHT_EYE_CORNERS)
            offsets = [o for o in (left, right) if o is not None]
            if not offsets:
                continue

            avg_offset = sum(offsets) / len(offsets)
            off_screen_flags.append(avg_offset > OFF_SCREEN_RATIO_THRESHOLD)

        if not off_screen_flags:
            # Couldn't score anything meaningful — flag for human review
            # rather than guessing.
            return {
                "score": 0.5,
                "off_screen_ratio": None,
                "frames_scored": 0,
                "note": "no frames with usable iris landmarks (no face detected)",
            }

        off_screen_ratio = sum(off_screen_flags) / len(off_screen_flags)

        # A candidate glancing away briefly is normal; what matters is a
        # *sustained/repeated pattern*, so the score decays gently for low
        # ratios and drops off faster past ~20% of frames off-screen.
        if off_screen_ratio <= 0.10:
            score = 1.0 - off_screen_ratio  # 0.90–1.0
        else:
            score = max(0.0, 0.90 - (off_screen_ratio - 0.10) * 1.8)

        return {
            "score": round(score, 3),
            "off_screen_ratio": round(off_screen_ratio, 3),
            "frames_scored": len(off_screen_flags),
        }


def score_gaze(video_path: str, sample_every_n_frames: int = 3) -> dict:
    """
    video_path: video file readable by cv2.VideoCapture.

    Returns {"score": float in [0, 1], "off_screen_ratio": float|None,
    "frames_scored": int}. On any failure, returns {"score": 0.5,
    "note": "..."} -- never 0.0 or 1.0, per this repo's nothing-auto-rejects
    architecture contract.
    """
    frames = []
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"cv2 could not open video: {video_path}")
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % sample_every_n_frames == 0:
                frames.append(frame)
            i += 1
        cap.release()
    except Exception as exc:  # noqa: BLE001 -- see docstring: fail neutral
        return {"score": 0.5, "note": f"gaze scoring failed: {exc}"}

    if not frames:
        return {"score": 0.5, "note": f"no frames decoded from {video_path}"}

    tracker = GazeTracker()
    try:
        return tracker.score_video(frames)
    except Exception as exc:  # noqa: BLE001 -- see docstring: fail neutral
        return {"score": 0.5, "note": f"gaze scoring failed: {exc}"}
    finally:
        tracker.close()


# Backwards-compatible alias: evaluate.py / service.py still import this name.
score_gaze_from_path = score_gaze
