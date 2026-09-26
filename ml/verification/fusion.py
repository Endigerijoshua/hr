"""
Fuse gaze / lip-sync / audio scores into a single VerificationSession result.

Design principle (this is the core anti-gaming argument, keep it front and
center in the paper): don't threshold any single signal alone. A candidate
who glances off-screen once (gaze dips) but has clean lip-sync and audio is
almost certainly fine — thresholding gaze alone would false-positive them.
Conversely a candidate with perfect gaze but a second voice audibly feeding
answers is clearly gaming, even though gaze alone looks clean. Fusion is
what lets one weak signal be overruled by two clean ones, and lets two bad
signals overrule one clean one.

Nothing here is auto-rejection. "fail" still means "route to a human with
high suspicion", not "candidate is banned". reviewedByHR is set to True for
anything that isn't a clean pass, per the platform's actual anti-gaming
safeguard: a human always makes the final call on ambiguous cases.
"""

from __future__ import annotations

from dataclasses import dataclass

# Weights reflect that audio (a second voice) and lip-sync (someone else
# answering) are stronger, harder-to-fake-innocently signals than gaze
# (which legitimately varies a lot: note-glancing, thinking pauses, screen
# reflections confusing iris tracking, etc). Re-tune against your labeled
# set — don't ship these numbers as gospel, that's exactly the kind of
# unjustified threshold the paper should call out if left untuned.
WEIGHTS = {"gaze": 0.25, "lipsync": 0.4, "audio": 0.35}

PASS_THRESHOLD = 0.80
FAIL_THRESHOLD = 0.35  # below this AND at least one raw signal is very bad -> "fail" (still human-reviewed)


@dataclass
class FusionResult:
    fused_score: float
    result: str  # "pass" | "flagged" | "fail"
    reviewed_by_hr: bool
    reasons: list[str]


def fuse(gaze_score: float, lipsync_score: float, audio_score: float) -> FusionResult:
    fused = (
        WEIGHTS["gaze"] * gaze_score
        + WEIGHTS["lipsync"] * lipsync_score
        + WEIGHTS["audio"] * audio_score
    )

    reasons = []
    if gaze_score < 0.5:
        reasons.append("gaze pattern inconsistent with staying on-screen")
    if lipsync_score < 0.5:
        reasons.append("mouth movement doesn't track with detected speech")
    if audio_score < 0.5:
        reasons.append("possible second voice / overlapping speech detected")

    any_signal_very_bad = min(gaze_score, lipsync_score, audio_score) < 0.2

    if fused >= PASS_THRESHOLD and not any_signal_very_bad:
        result = "pass"
        reviewed_by_hr = False
        if not reasons:
            reasons.append("all signals consistent with honest, unassisted work")
    elif fused < FAIL_THRESHOLD and any_signal_very_bad:
        # Strong multi-signal or single very-bad-signal case. Still not an
        # auto-reject — just a stronger recommendation to the human.
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


def to_verification_session_payload(submission_id: str, gaze: dict, lipsync: dict, audio: dict) -> dict:
    """Build the exact POST body for /api/verification-sessions per the
    shared VerificationSession entity contract — field names must not
    change, the backend teammate codes directly against these."""
    fusion = fuse(gaze["score"], lipsync["score"], audio["score"])
    return {
        "submissionId": submission_id,
        "gazeScore": gaze["score"],
        "lipSyncScore": lipsync["score"],
        "audioScore": audio["score"],
        "result": fusion.result,
        "reviewedByHR": fusion.reviewed_by_hr,
        # Extra diagnostic fields — harmless if the backend ignores unknown
        # keys, useful for the reviewer UI and for the paper's appendix.
        "_fusedScore": fusion.fused_score,
        "_reasons": fusion.reasons,
    }
