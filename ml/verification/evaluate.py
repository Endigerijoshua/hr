"""
Score a hand-labeled test set and report precision / recall / F1 / a
confusion matrix — the numbers the paper needs to report honestly.

Expected labels.json (put clips + labels next to this file, or point
LABELS_PATH at wherever you keep them):

[
  {"video": "clips/honest_01.mp4", "audio": "clips/honest_01.wav", "label": "honest"},
  {"video": "clips/gamed_01.mp4",  "audio": "clips/gamed_01.wav",  "label": "gamed"},
  ...
]

"label" is ground truth from however you constructed the test set (e.g. you
deliberately recorded some clips with a second person feeding answers).
We collapse the model's 3-way result ("pass"/"flagged"/"fail") to a binary
prediction for the standard confusion matrix: "pass" -> predicted honest,
anything else -> predicted gamed/suspicious. Report the 3-way breakdown too
since collapsing "flagged" into "gamed" hides that flagged cases are
*routed to a human*, not auto-condemned — that distinction matters for the
paper's framing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .gaze import score_gaze_from_path
from .lipsync import score_lipsync
from .audio import score_audio
from .fusion import fuse

LABELS_PATH = Path(__file__).parent / "labels.json"


def run_eval(labels_path: Path = LABELS_PATH):
    with open(labels_path) as f:
        cases = json.load(f)

    rows = []
    for case in cases:
        gaze = score_gaze_from_path(case["video"])
        lipsync = score_lipsync(case["video"])
        audio = score_audio(case["video"])
        fusion = fuse(gaze["score"], lipsync["score"], audio["score"])
        predicted_honest = fusion.result == "pass"
        actual_honest = case["label"] == "honest"
        rows.append({
            **case,
            "fused_score": fusion.fused_score,
            "result": fusion.result,
            "predicted_honest": predicted_honest,
            "actual_honest": actual_honest,
        })

    tp = sum(1 for r in rows if not r["predicted_honest"] and not r["actual_honest"])  # correctly flagged gaming
    tn = sum(1 for r in rows if r["predicted_honest"] and r["actual_honest"])           # correctly passed honest
    fp = sum(1 for r in rows if not r["predicted_honest"] and r["actual_honest"])       # honest wrongly flagged
    fn = sum(1 for r in rows if r["predicted_honest"] and not r["actual_honest"])       # gaming wrongly passed

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float("nan")

    result_counts = {"pass": 0, "flagged": 0, "fail": 0}
    for r in rows:
        result_counts[r["result"]] += 1

    report = {
        "n_cases": len(rows),
        "confusion_matrix": {"TP_gaming_caught": tp, "TN_honest_passed": tn, "FP_honest_flagged": fp, "FN_gaming_missed": fn},
        "precision": round(precision, 3) if precision == precision else None,
        "recall": round(recall, 3) if recall == recall else None,
        "f1": round(f1, 3) if f1 == f1 else None,
        "three_way_result_counts": result_counts,
        "rows": rows,
    }
    return report


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else LABELS_PATH
    report = run_eval(path)
    print(json.dumps(report, indent=2, default=str))
