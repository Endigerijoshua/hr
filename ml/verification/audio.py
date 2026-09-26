"""
Background-audio consistency check: flag a second voice or overlapping
speech (proxy for someone off-camera feeding answers).

Hackathon-speed approach (no speaker-diarization model needed):
1. Voice-activity segments via energy + zero-crossing rate.
2. Within each voiced segment, estimate the dominant pitch (f0) with
   librosa.pyin.
3. If a *second*, sufficiently different and sufficiently persistent pitch
   track shows up simultaneously with the first (rather than the natural
   pitch wobble of one speaker), treat it as a second voice.

This is intentionally a coarse proxy, not a diarization system — say so in
the paper. It's good enough to catch the obvious case (someone else audibly
talking in the background) without pretending to solve general speaker
diarization in a weekend.

Same convention: score in [0, 1], 1.0 = consistent with a single speaker.
"""

from __future__ import annotations

import numpy as np
import librosa

FRAME_LENGTH = 2048
HOP_LENGTH = 512
MIN_SEMITONE_GAP_FOR_SECOND_VOICE = 4.0  # pitch difference unlikely from one person's natural variation
MAX_ACCEPTABLE_OVERLAP_RATIO = 0.05  # fraction of voiced frames allowed to look "second-voice-like"


def _voice_activity_mask(y: np.ndarray, sr: int) -> np.ndarray:
    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    threshold = np.percentile(rms, 60) * 0.5 + 1e-6
    return rms > threshold


def score_audio(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    voiced = _voice_activity_mask(y, sr)

    if voiced.sum() < 10:
        return {"score": 0.5, "second_voice_frame_ratio": None, "note": "not enough voiced audio to score"}

    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )

    n = min(len(f0), len(voiced))
    f0 = f0[:n]
    voiced = voiced[:n]

    valid = voiced & ~np.isnan(f0)
    if valid.sum() < 10:
        return {"score": 0.5, "second_voice_frame_ratio": None, "note": "pitch not trackable"}

    midi = librosa.hz_to_midi(f0[valid])

    # Rolling-median pitch as the "primary speaker" track; frames that jump
    # far from the recent local median, then jump back, look like a brief
    # second voice rather than natural pitch drift (which is gradual).
    window = 15
    padded = np.pad(midi, (window // 2, window // 2), mode="edge")
    rolling_median = np.array([
        np.median(padded[i:i + window]) for i in range(len(midi))
    ])
    deviation = np.abs(midi - rolling_median)
    second_voice_like = deviation > MIN_SEMITONE_GAP_FOR_SECOND_VOICE

    ratio = float(second_voice_like.sum() / len(second_voice_like))

    if ratio <= MAX_ACCEPTABLE_OVERLAP_RATIO:
        score = 1.0
    else:
        # Scale down; fully saturate to 0 once ~25% of voiced frames look
        # like a second voice.
        score = max(0.0, 1.0 - (ratio - MAX_ACCEPTABLE_OVERLAP_RATIO) / 0.25)

    return {
        "score": round(float(score), 3),
        "second_voice_frame_ratio": round(ratio, 3),
    }
