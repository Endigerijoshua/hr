# Anti-Gaming Architecture: Rank Scoring & Fraud Defense

*Verifiable Proof-of-Work Engineering Discovery & Hiring Platform*

## 1. Ranking Formula

> TODO: pull the exact formula and weights from `lib/ranking.ts` (backend
> teammate) before submission. Do not guess at these — the paper should
> quote the real implementation.

The ranking score for a candidate incorporates a `verificationMultiplier`
read from this scope's `VerificationSession.result`:

| `result` | `verificationMultiplier` |
|---|---|
| `pass` | 1.2x |
| unverified (no session yet) | 1.0x |
| `flagged` (unresolved) | 0.5x |

`fail` is not a separate multiplier tier in the current contract — see
Section 4 for why we deliberately don't treat "fail" as "the model has
spoken"; it's still routed to `reviewedByHR`, and the human's disposition
of it (not the raw model output) is what should ultimately move the
multiplier. TODO: confirm with backend teammate how a post-human-review
`flagged`/`fail` case updates the multiplier once resolved.

## 2. Verification Pipeline

### 2.1 Signals

- **Gaze** (`ml/verification/gaze.py`): MediaPipe iris landmarks estimate
  how far gaze drifts from the eye-corner midpoint, per frame. We track the
  *ratio of frames* where gaze is off-screen, not any single frame — a
  candidate glancing away briefly (checking notes, thinking) is normal and
  shouldn't cost them; a sustained or repeated pattern is what the score
  penalizes.
- **Lip-sync** (`ml/verification/lipsync.py`): mouth-aspect-ratio time
  series vs. the audio amplitude envelope, correlated. If someone off-camera
  is answering, mouth movement and speech energy decouple.
- **Audio** (`ml/verification/audio.py`): pitch-track deviation from a
  rolling median flags segments that look like a second voice rather than
  one speaker's natural pitch variation.

Each signal is scored 0–1 (1.0 = consistent with honest behavior).

### 2.2 Fusion (the actual anti-gaming mechanism)

We explicitly do **not** threshold any single signal alone. Signals are
weighted and combined (`ml/verification/fusion.py`):

- gaze: 0.25
- lip-sync: 0.40
- audio: 0.35

Weights favor lip-sync and audio because they're harder to trigger
innocently than gaze (screen glare, note-checking, and camera-angle
artifacts all move gaze scores without any gaming taking place).

This is the core defensible claim in this section: **reducing false
positives comes from requiring corroboration across independent signals,
not from loosening any one signal's threshold.** An innocent candidate who
glances away once but has clean audio and lip-sync should not be flagged
by gaze alone — and in this design, isn't.

### 2.3 Thresholds and outcome mapping

- fused score ≥ 0.80 **and** no single raw signal below 0.20 → `pass`,
  `reviewedByHR = false`
- fused score < 0.35 **and** at least one signal below 0.20 → `fail`
  (still `reviewedByHR = true` — see below)
- otherwise → `flagged`, `reviewedByHR = true`

TODO: replace these placeholder thresholds with values tuned against
Section 3's labeled set, and note the tradeoff you actually chose (e.g.
"we biased toward more `flagged` results over more `fail` results because
false accusations are costlier than an extra human review").

### 2.4 Never auto-rejected

No `result` value causes an automatic negative consequence for the
candidate beyond the ranking multiplier above. `flagged` and `fail` both
set `reviewedByHR = true` — a human reviewer makes the actual accept/reject
call. This is deliberate: a classifier built in a hackathon weekend, on a
few dozen labeled clips, should not be the final word on someone's hiring
outcome. The system's honesty about its own reliability *is* the
anti-gaming feature here — it's what keeps a false positive from becoming a
false accusation.

## 3. Evaluation: Confusion Matrix & Precision/Recall

> TODO: run `python -m ml.verification.evaluate` against your labeled clip
> set (see `README-ml-anti-gaming.md`) and paste the real output here.
> Report it honestly, including if precision or recall is mediocre — a
> paper claiming implausibly perfect numbers on ~20-30 hackathon clips is
> less credible than one that shows real, modest numbers plus a stated
> tuning tradeoff.

Framing note, stated explicitly for the reader: the goal of tuning is not
to convert false positives/negatives into true positives — that isn't a
coherent target (a model that always predicts "gaming" or always predicts
"honest" trivially destroys its own signal in one direction while
maximizing it in the other). The goal is:

- **Fewer false positives** via multi-signal fusion (Section 2.2) instead
  of a single sensitive threshold.
- **Fewer false negatives** via threshold tuning against the labeled set,
  with the tradeoff made explicit rather than hidden.
- **Bounded damage from remaining errors** via mandatory human review on
  anything that isn't a clean pass (Section 2.4) — this is what makes an
  imperfect classifier into a trustworthy system component, rather than
  requiring the classifier itself to be perfect.

`TODO: confusion matrix table + precision/recall/F1 numbers here`

## 4. Plagiarism / Code-Similarity Check

`ml/plagiarism/similarity.py` compares a submission against a corpus of
public repo snippets and other candidates' submissions using shingled
Jaccard similarity (cheap first pass) confirmed by sequence matching
(precise second pass), after normalizing away comments/whitespace so
formatting differences don't hide real similarity.

Important framing: this catches **high textual similarity**, not
"plagiarism" in the legal/academic-integrity sense — convergent solutions
to a common challenge (especially with shared starter templates) can also
produce high similarity. Matches above threshold are flagged for the same
human-review path as verification sessions, never auto-rejected, for
exactly that reason.

## 5. Other Anti-Gaming Mechanisms (System-Wide)

The verification and plagiarism checks above are this scope's contribution
to a broader set of anti-gaming mechanisms across the system:

| Mechanism | Owner | Status |
|---|---|---|
| Live verification session (gaze/lip-sync/audio fusion) | this scope | built |
| Plagiarism/code-similarity check | this scope | built (secondary mechanism) |
| Reviewer trust scoring | TODO: name the teammate | TODO: pull status |
| Reciprocity credit (must review others for your reviews to count) | TODO | TODO |
| Randomized challenge variants (harder to pre-solve/share answers) | TODO | TODO |

> TODO: fill in the right-hand columns from the other three agents' scopes
> so this section reflects the whole system's defense-in-depth, not just
> what this scope built. The point for judges is that no single mechanism
> here is meant to be airtight alone — verification, plagiarism-checking,
> reviewer trust, reciprocity, and randomized variants are each individually
> gameable in isolation, and the claim is that stacking them raises the
> cost of gaming the whole system well above the cost of just doing the
> work honestly.
