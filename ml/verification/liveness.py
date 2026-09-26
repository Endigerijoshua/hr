"""
Liveness / anti-spoofing check using an EXISTING pretrained CNN — Silent-Face-
Anti-Spoofing (MiniFASNet), from https://github.com/minivision-ai/Silent-Face-Anti-Spoofing

We are NOT training anything here. This wraps their real, shipped inference
code and pretrained weights. It answers a narrower question than the old
gaze/lipsync pipeline: not "is this person's mouth matching their voice" but
"is there a real, live human in front of the camera at all" — i.e. it
catches someone holding up a photo, playing a pre-recorded video of the
candidate, or a screen replay attack. That's a real, well-studied CNN
classification task (real vs. spoof face), which is exactly the kind of
thing an off-the-shelf model is good for, versus rolling your own.

Same score convention as the rest of ml/verification: 0.0-1.0, where 1.0 =
confident real/live face, 0.0 = confident spoof/fake.

SETUP (do this once, before importing this module):
    cd third_party/
    git clone https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git
This module expects that path: third_party/Silent-Face-Anti-Spoofing/
relative to wherever you run Python from (repo root). Their pretrained
weights ship inside the clone at resources/anti_spoof_models/ — no
separate download needed.

Their code hardcodes relative paths like "./resources/detection_model/..."
at construction time, so we chdir into their repo while constructing the
predictor, then chdir back — see _load_predictor() below. That's the only
thing we patch; their prediction math is untouched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np

VENDORED_REPO = Path(__file__).resolve().parents[2] / "third_party" / "Silent-Face-Anti-Spoofing"

_predictor = None
_cropper = None


def _load_predictor():
    global _predictor, _cropper
    if _predictor is not None:
        return _predictor, _cropper

    if not VENDORED_REPO.exists():
        raise FileNotFoundError(
            f"Expected the Silent-Face-Anti-Spoofing repo at {VENDORED_REPO}. "
            "Clone it there first: git clone "
            "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git "
            f"{VENDORED_REPO}"
        )

    sys.path.insert(0, str(VENDORED_REPO))
    from src.anti_spoof_predict import AntiSpoofPredict  # noqa: E402
    from src.generate_patches import CropImage  # noqa: E402

    # Their Detection.__init__ reads "./resources/detection_model/..." —
    # relative to cwd, not to this file — so we chdir for construction only.
    original_cwd = os.getcwd()
    try:
        os.chdir(VENDORED_REPO)
        _predictor = AntiSpoofPredict(device_id=0)  # falls back to CPU automatically if no CUDA
        _cropper = CropImage()
    finally:
        os.chdir(original_cwd)

    return _predictor, _cropper


def _score_frame(frame_bgr: np.ndarray) -> float | None:
    """Returns P(real face) in [0, 1] for one frame, or None if no face found."""
    from src.utility import parse_model_name  # available on sys.path after _load_predictor()

    predictor, cropper = _load_predictor()
    model_dir = VENDORED_REPO / "resources" / "anti_spoof_models"

    bbox = predictor.get_bbox(frame_bgr)
    if bbox is None or bbox[2] <= 0 or bbox[3] <= 0:
        return None

    prediction = np.zeros((1, 3))
    for model_name in os.listdir(model_dir):
        h_input, w_input, model_type, scale = parse_model_name(model_name)
        param = {
            "org_img": frame_bgr,
            "bbox": bbox,
            "scale": scale,
            "out_w": w_input,
            "out_h": h_input,
            "crop": scale is not None,
        }
        img = cropper.crop(**param)
        prediction += predictor.predict(img, str(model_dir / model_name))

    label = int(np.argmax(prediction))
    confidence = float(prediction[0][label] / len(os.listdir(model_dir)))
    # label 1 == real face in the shipped models' convention (see their test.py)
    return confidence if label == 1 else 1.0 - confidence


def score_liveness_from_path(video_path: str, sample_every_n_frames: int = 10, max_frames: int = 15) -> dict:
    """
    Samples a handful of frames from the clip (this model runs on single
    images, not video — sampling several frames and averaging is cheap
    insurance against one bad frame, e.g. motion blur or a bad angle).
    """
    cap = cv2.VideoCapture(video_path)
    scores = []
    i = 0
    while len(scores) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if i % sample_every_n_frames == 0:
            s = _score_frame(frame)
            if s is not None:
                scores.append(s)
        i += 1
    cap.release()

    if not scores:
        # No face detected clearly enough to score — flag for human review
        # rather than silently passing or failing.
        return {"score": 0.5, "frames_scored": 0, "note": "no face detected clearly enough to score"}

    return {"score": round(float(np.mean(scores)), 3), "frames_scored": len(scores)}
