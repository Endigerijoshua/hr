"""
Fuse gaze / lip-sync / audio / liveness scores into a single verification
result.

liveness (ml/verification/liveness.py, an existing pretrained CNN --
MiniFASNet via Silent-Face-Anti-Spoofing) answers a different question than
the other three: not "is someone else answering for this person" but "is
there even a real live human on camera, or a photo/video/replay being held
up." Both matter, so both are fused, not one replacing the other.

Design principle unchanged from before: don't threshold any single signal
alone. Fusing multiple weak/narrow signals is what reduces false positives
-- an innocent candidate who glances away once (gaze dips) but has clean
lip-sync, audio, and a confirmed-live face is almost certainly fine.

Nothing here is auto-rejection. "fail" still means "route to a human with
high suspicion," not "candidate is banned." reviewedByHR is True for
anything that isn't a clean pass.
"""

from __future__ import annotations

from dataclasses import dataclass

# Liveness gets the highest weight: it's the most direct, hardest-to-fake
# signal of the four (a CNN specifically trained to tell real vs. spoofed
# faces apart, vs. our own hand-rolled proxies for gaze/lipsync/audio).
# Re-tune all of these against your labeled set -- don't ship as gospel.
WEIGHTS = {"gaze": 0.15, "lipsync": 0.25, "audio": 0.20, "liveness": 0.40}

PASS_THRESHOLD = 0.80
FAIL_THRESHOLD = 0.35


@dataclass
class FusionResult:
    fused_score: float
    result: str  # "pass" | "flagged" | "fail"
    reviewed_by_hr: bool
    reasons: list[str]


def fuse(gaze_score: float, lipsync_score: float, audio_score: float, liveness_score: float) -> FusionResult:
    fused = (
        WEIGHTS["gaze"] * gaze_score
        + WEIGHTS["lipsync"] * lipsync_score
        + WEIGHTS["audio"] * audio_score
        + WEIGHTS["liveness"] * liveness_score
    )

    reasons = []
    if liveness_score < 0.5:
        reasons.append("CNN liveness check suggests a possible photo/video/replay spoof")
    if gaze_score < 0.5:
        reasons.append("gaze pattern inconsistent with staying on-screen")
    if lipsync_score < 0.5:
        reasons.append("mouth movement doesn't track with detected speech")
    if audio_score < 0.5:
        reasons.append("possible second voice / overlapping speech detected")

    any_signal_very_bad = min(gaze_score, lipsync_score, audio_score, liveness_score) < 0.2

    if fused >= PASS_THRESHOLD and not any_signal_very_bad:
        result = "pass"
        reviewed_by_hr = False
        if not reasons:
            reasons.append("all signals consistent with an honest, live, unassisted candidate")
    elif fused < FAIL_THRESHOLD and any_signal_very_bad:
        result = "fail"
        reviewed_by_hr = True
    else:
        result = "flagged"
        reviewed_by_hr = True
        if not reasons:
            reasons.append("fused confidence in the ambiguous range")

    return FusionResult(
        fused_score=round(fused, 3),
        result=result,
        reviewed_by_hr=reviewed_by_hr,
        reasons=reasons,
    )


def to_verification_session_payload(submission_id: str, gaze: dict, lipsync: dict, audio: dict, liveness: dict) -> dict:
    """Build the POST body for /api/verification-sessions. NOTE: adds
    livenessScore to the previously-agreed VerificationSession shape --
    confirm this field addition with whoever owns the backend entity/DB
    schema before relying on it being stored, since the original contract
    didn't include it."""
    fusion = fuse(gaze["score"], lipsync["score"], audio["score"], liveness["score"])
    return {
        "submissionId": submission_id,
        "gazeScore": gaze["score"],
        "lipSyncScore": lipsync["score"],
        "audioScore": audio["score"],
        "livenessScore": liveness["score"],
        "result": fusion.result,
        "reviewedByHR": fusion.reviewed_by_hr,
        "_fusedScore": fusion.fused_score,
        "_reasons": fusion.reasons,
    }
