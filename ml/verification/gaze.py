"""
Gaze tracking / off-screen-look detection.

Uses MediaPipe FaceMesh (with refine_landmarks=True for iris points) to
estimate, frame by frame, whether the candidate's gaze is on-screen or has
wandered off in a pattern consistent with reading answers from another
screen/device.

Convention used across this whole verification pipeline:
    score in [0, 1], where 1.0 = fully consistent with honest behavior,
    0.0 = strongly consistent with gaming behavior.
This lets fusion.py combine gaze/lipsync/audio scores the same way.
"""

from __future__ import annotations

import numpy as np
import cv2
import mediapipe as mp

# MediaPipe iris landmark indices (with refine_landmarks=True)
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_EYE_CORNERS = (33, 133)
RIGHT_EYE_CORNERS = (362, 263)

# How far the iris can drift from the eye-corner midpoint (as a fraction of
# eye width) before we count the frame as "gaze off-screen". Tuned loosely;
# this is exactly the kind of threshold that should be re-tuned against your
# labeled clips (see confusion_matrix.py) rather than trusted as-is.
OFF_SCREEN_RATIO_THRESHOLD = 0.35


class GazeTracker:
    def __init__(self):
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def close(self):
        self._face_mesh.close()

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

        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._face_mesh.process(rgb)
            if not result.multi_face_landmarks:
                # No face detected at all is itself suspicious (candidate
                # stepped out of frame) — treat as off-screen for this frame.
                off_screen_flags.append(True)
                continue

            landmarks = result.multi_face_landmarks[0].landmark
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
            return {"score": 0.5, "off_screen_ratio": None, "frames_scored": 0}

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


def score_gaze_from_path(video_path: str, sample_every_n_frames: int = 3) -> dict:
    """Convenience entrypoint: read a video file and score it."""
    cap = cv2.VideoCapture(video_path)
    frames = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % sample_every_n_frames == 0:
            frames.append(frame)
        i += 1
    cap.release()

    tracker = GazeTracker()
    try:
        return tracker.score_video(frames)
    finally:
        tracker.close()
