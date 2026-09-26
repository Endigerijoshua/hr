"""
Gaze tracking / off-screen-look detection.

Predicts the candidate's gaze direction per frame with L2CS-Net (Abdelrahman
et al., "L2CS-Net: Transfer Learning From L2CS to Gaze Estimation", ECCV
2020) -- a ResNet50 + 90-bin classification model pretrained on Gaze360 --
and flags frames where the gaze is far enough from the camera to look like
the candidate is reading from another screen/device.

Pipeline per sampled frame:
  1. MediaPipe FaceLandmarker finds the face (same model the rest of this
     repo already uses; also supplies the 478 landmarks we crop from).
  2. Crop a padded, square-ish face box and resize to 448x448, normalized
     with ImageNet stats -- matching the preprocessing the Gaze360-trained
     checkpoint was trained with.
  3. L2CS-Net returns yaw/pitch in degrees; deviation is the angle between
     the gaze direction and straight-at-camera (0, 0).

Convention used across this whole verification pipeline:
    score in [0, 1], where 1.0 = fully consistent with honest behavior,
    0.0 = strongly consistent with gaming behavior.
This lets fusion.py combine gaze/lipsync/audio scores the same way.

Why angles instead of the previous iris-geometry heuristic: iris offset from
the eye-corner midpoint is a poor proxy for gaze direction (it mostly tracks
eye *aperture* and head pose, and saturated at ~0.145 against a 0.35
threshold on reference footage, so it could not separate an on-camera
subject from a mildly averted one). L2CS-Net estimates the actual gaze
direction in degrees.

Fails soft: any error (missing weights, no face, unreadable video) returns
{"score": 0.5, "note": ...} -- never 0.0 or 1.0, per this repo's
nothing-auto-rejects architecture contract.

Requires the Gaze360 checkpoint at ml/verification/models/L2CSNet_gaze360.pkl
(~96 MB, see README-ml-anti-gaming.md for the download source).
"""

from __future__ import annotations

import os

import numpy as np
import cv2
import torch
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from .l2cs_model import decode_angles, load_l2cs_resnet50

_HERE = os.path.dirname(os.path.abspath(__file__))
_FACE_MODEL_PATH = os.path.join(_HERE, "models", "face_landmarker.task")
_L2CS_WEIGHTS_PATH = os.path.join(_HERE, "models", "L2CSNet_gaze360.pkl")

_INPUT_SIZE = 448  # Gaze360 / L2CS-Net input resolution
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Fraction of the face-mesh bounding box added as padding before cropping.
# Gaze360 crops are face-centred with generous margins; too tight a crop
# loses the cheeks/forehead the model keys on.
_FACE_CROP_PADDING = 0.35

# Minimum face-box edge in pixels; below this the crop is too small for the
# 448x448 input to carry any signal.
_MIN_FACE_EDGE_PX = 48

# --- UNVALIDATED THRESHOLD. ---
# Angular deviation from camera at which a frame counts as "off-screen".
# Chosen from the model's own reported accuracy on Gaze360 (L2CS-Net is
# ~6-7 deg mean angular error, so 20 deg is a few sigma out) and from the
# observation that a person reading a second screen typically turns well
# past that. This is NOT tuned against labeled honest/gamed clips and must
# not be presented as validated. Tune it with confusion_matrix.py /
# evaluate.py against real numbers before trusting it, exactly like the
# thresholds it replaced.
OFF_SCREEN_ANGLE_THRESHOLD_DEG = 20.0

_BATCH_SIZE = 16


class GazeError(RuntimeError):
    """Raised when the face detector or the L2CS-Net model can't be used."""


def _load_face_landmarker() -> vision.FaceLandmarker:
    if not os.path.isfile(_FACE_MODEL_PATH):
        raise GazeError(f"MediaPipe face_landmarker bundle not found at {_FACE_MODEL_PATH}")
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_FACE_MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.FaceLandmarker.create_from_options(options)


def _face_crop(frame_bgr: np.ndarray, landmarks) -> np.ndarray | None:
    """
    Returns an RGB uint8 face crop resized to (_INPUT_SIZE, _INPUT_SIZE), or
    None if the detected face is too small to be usable.
    """
    xs = [p.x for p in landmarks]
    ys = [p.y for p in landmarks]
    h, w = frame_bgr.shape[:2]

    x_min, x_max = min(xs) * w, max(xs) * w
    y_min, y_max = min(ys) * h, max(ys) * h

    cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
    half_w = (x_max - x_min) / 2.0 * (1.0 + _FACE_CROP_PADDING)
    half_h = (y_max - y_min) / 2.0 * (1.0 + _FACE_CROP_PADDING)
    # Square-ish crop: L2CS expects a face-centred box, not a stretched one.
    half = max(half_w, half_h)

    if 2 * half < _MIN_FACE_EDGE_PX:
        return None

    x0 = int(max(0, round(cx - half)))
    y0 = int(max(0, round(cy - half)))
    x1 = int(min(w, round(cx + half)))
    y1 = int(min(h, round(cy + half)))
    if x1 - x0 < _MIN_FACE_EDGE_PX or y1 - y0 < _MIN_FACE_EDGE_PX:
        return None

    crop = frame_bgr[y0:y1, x0:x1]
    crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return cv2.resize(crop, (_INPUT_SIZE, _INPUT_SIZE), interpolation=cv2.INTER_AREA)


def _preprocess(crops: list[np.ndarray]) -> torch.Tensor:
    """uint8 RGB crops -> normalized float tensor, matching the checkpoint's training."""
    arr = np.stack(crops).astype(np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    return torch.from_numpy(np.ascontiguousarray(arr.transpose(0, 3, 1, 2)))


@torch.no_grad()
def _predict_deviations(model, crops: list[np.ndarray]) -> list[float]:
    """Runs L2CS-Net over face crops; returns per-crop angular deviation in degrees."""
    deviations: list[float] = []
    for start in range(0, len(crops), _BATCH_SIZE):
        batch = _preprocess(crops[start:start + _BATCH_SIZE])
        yaw_logits, pitch_logits = model(batch)
        yaw_deg, pitch_deg = decode_angles(yaw_logits, pitch_logits)
        for y, p in zip(yaw_deg.tolist(), pitch_deg.tolist()):
            # Euclidean angle between the gaze direction and dead-at-camera.
            deviations.append(float(np.hypot(y, p)))
    return deviations


def score_gaze(video_path: str, sample_every_n_frames: int = 3) -> dict:
    """
    video_path: video file readable by cv2.VideoCapture.

    Returns {"score": float in [0, 1], "off_screen_ratio": float|None,
    "frames_scored": int, "mean_deviation_deg": float|None,
    "max_deviation_deg": float|None}. On any failure returns
    {"score": 0.5, "note": "..."} -- never 0.0 or 1.0, per this repo's
    nothing-auto-rejects architecture contract.
    """
    frames = []
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise GazeError(f"cv2 could not open video: {video_path}")
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

    try:
        if not os.path.isfile(_L2CS_WEIGHTS_PATH):
            raise GazeError(
                f"L2CS-Net checkpoint not found at {_L2CS_WEIGHTS_PATH}. "
                f"See README-ml-anti-gaming.md for the download source."
            )
        model = load_l2cs_resnet50(_L2CS_WEIGHTS_PATH, device="cpu")
        landmarker = _load_face_landmarker()
    except Exception as exc:  # noqa: BLE001 -- see docstring: fail neutral
        return {"score": 0.5, "note": f"gaze model init failed: {exc}"}

    try:
        crops: list[np.ndarray] = []
        frames_without_face = 0

        for i, frame in enumerate(frames):
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
            )
            # VIDEO mode needs strictly increasing timestamps; we don't track
            # real fps here, so use a synthetic monotonic one.
            result = landmarker.detect_for_video(mp_image, i * 33)

            if not result.face_landmarks:
                # No face in frame is itself suspicious (candidate stepped
                # out of view) — count it as off-screen, as before.
                frames_without_face += 1
                continue

            crop = _face_crop(frame, result.face_landmarks[0])
            if crop is None:
                frames_without_face += 1
                continue
            crops.append(crop)

        if not crops:
            return {
                "score": 0.5,
                "note": "no frames with a usable face crop (face never detected)",
            }

        deviations = _predict_deviations(model, crops)
    except Exception as exc:  # noqa: BLE001 -- see docstring: fail neutral
        return {"score": 0.5, "note": f"gaze scoring failed: {exc}"}
    finally:
        landmarker.close()

    off_screen_flags = [d > OFF_SCREEN_ANGLE_THRESHOLD_DEG for d in deviations]
    off_screen_flags += [True] * frames_without_face

    off_screen_ratio = sum(off_screen_flags) / len(off_screen_flags)

    # Same decay shape the previous implementation used, so scores stay
    # comparable across the two: gentle under 10% of frames off-screen,
    # steeper after.
    if off_screen_ratio <= 0.10:
        score = 1.0 - off_screen_ratio  # 0.90-1.0
    else:
        score = max(0.0, 0.90 - (off_screen_ratio - 0.10) * 1.8)

    return {
        "score": round(score, 3),
        "off_screen_ratio": round(off_screen_ratio, 3),
        "frames_scored": len(off_screen_flags),
        "mean_deviation_deg": round(float(np.mean(deviations)), 2),
        "max_deviation_deg": round(float(np.max(deviations)), 2),
    }


# Back-compat alias: score_gaze_from_path was the pre-L2CS-Net name, still
# imported by service.py and evaluate.py.
score_gaze_from_path = score_gaze
