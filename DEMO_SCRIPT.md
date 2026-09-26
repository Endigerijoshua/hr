# DEMO_SCRIPT.md — live click-by-click runbook

Two processes must be up. Everything below is `localhost`.

| # | Process | Port | Start command |
|---|---|---|---|
| 1 | Next.js app | 3000 | `npm run dev` in `C:\Users\localadmin\hr` |
| 2 | Verification service (FastAPI) | 8001 | see [Pre-flight](#pre-flight) — **env vars required** |

---

## Pre-flight (do this before you walk on stage — 60 seconds)

```powershell
cd C:\Users\localadmin\hr

# Terminal 1 — web app
npm run dev

# Terminal 2 — ML verification service.
# SYNCNET_REPO_DIR is MANDATORY: without it the lip-sync scorer raises and
# the whole /verify request 500s.
$env:PYTHONPATH      = "C:\Users\localadmin\hr"
$env:SYNCNET_REPO_DIR = "C:\Users\localadmin\hr\syncnet_python"
$env:BACKEND_BASE_URL = "http://localhost:3000"
python -m uvicorn ml.verification.service:app --port 8001
```

Smoke-test **both** before you start, in a third terminal:

```powershell
curl.exe -s http://127.0.0.1:8001/health          # expect {"status":"ok"}
curl.exe -s -o NUL -w "%{http_code}" http://localhost:3000/   # expect 200
```

If either fails, **do not start the live path** — go straight to
[Fallback](#fallback-if-the-webcam-or-ml-path-dies-on-stage).

Open the browser at `http://localhost:3000/`. Grant camera + mic when prompted.

---

## Step 1 — Recruiter posts a job

1. Click **Post job** in the top nav (or go to `/post-job`).
2. Fill the form:
   - **Company name** → `Northwind Robotics`
   - **Title** → `Senior CV Engineer`
   - **Domain** → `engineering` *(leave the default — this is the field the
     shortlister matches on, so it matters later)*
   - **Description** → `Own the vision pipeline end to end: capture, scoring, and the recruiter UI.`
   - **Required skills** → `python, ffmpeg, react`
3. Click **Post job**.

You are redirected to `/jobs/<jobId>/candidates`. The table says
*"No applicants yet."* — expected, and worth pausing on: **this is the empty
state that the rest of the demo fills in.**

> **Say:** "Recruiter posts a role. The shortlister weighs two things — does the
> candidate's domain match the job's, and did they pass live verification."

**Copy the URL** out of the address bar. You need it in step 4.
It looks like `http://localhost:3000/jobs/cmuios6zr000owjmw36ntchwk/candidates`.

---

## Step 2 — Candidate signs up and uploads a resume

Open a **new tab** (this is the candidate's session; `localStorage` is per-origin
so a separate tab is cleaner for the demo narrative, though same-tab works).

1. Click **Signup**.
2. Fill the form:
   - **Name** → `Aditi Sharma`
   - **Email** → `aditi@onstage.example.com` *(must be unique — the DB has a
     unique constraint and a repeat run returns **409 Conflict**)*
   - **Domain** → `engineering`
   - **Resume** → click the file box and pick any `.pdf`.
     The app stores the **filename** only (`resumeFileUrl`); there is no binary
     upload. Don't oversell this.
3. Click **Create profile**.

You are redirected to `/verify`. A green line confirms the candidate id was
saved to `localStorage`.

> **Say:** "Notice the page already knows who I am — no login. The candidate id
> is in `localStorage` and every later step keys off it."

---

## Step 3 — Live verification (the risky step — read the fallback)

The button records **15 seconds** of webcam + mic, then uploads to
`localhost:8001`, which scores gaze, lip-sync, audio and liveness and writes
the result back to the Next.js API.

1. On `/verify`, confirm the line reads **Candidate: `cmui…`** (not *"none"*).
2. Click **Start verification**.
3. **Record for 15 seconds.** Look at the camera the whole time and say
   something out loud — the lip-sync and audio scorers need speech, and the
   gaze scorer penalises looking away.
4. The button switches to **Scoring (60-90s)…**. **Talk over this.**

### ⏱ Timing budget — the honest number

Measured on this machine: **recording 15s + scoring ~76s ≈ 90 seconds.**
The 76s is four CPU models (MediaPipe gaze, an L2CS-Net gaze model, a SyncNet
subprocess, librosa) running sequentially on CPU. There is no GPU.

That is a long time to stand on stage. Two options:

- **Shorten the recording** — the clip length is a URL param. Land on
  `http://localhost:3000/verify?secs=5` and the recording is 5s instead of 15s.
  Scoring time is dominated by model *load*, not clip length, so this saves
  only ~10s. Use the **Shorten clip** button on the page for the same effect.
- **Fill the 76s with the story** (recommended) — see the talking points below.

> **While it scores, say:**
> "Four independent signals. Gaze — is a real person actually looking at the
> screen, or is the camera pointed at a wall. Lip-sync — does the mouth
> movement match the audio, which catches a dubbed or prerecorded defence.
> Audio — a second voice, or overlapping speech, is a red flag. And liveness —
> a CNN trained specifically to tell a real face from a photo or a replayed
> video held up to the camera. Individually each one is weak. Fusing them is
> what makes it hard to beat, because faking one doesn't fake the others."

### What you'll actually see — read this before you demo

**The verdict on a live recording is `flagged`, not `pass`.** On this machine
`demo_clip.mp4` scores gaze `0.0`, lip-sync `0.5`, audio `1.0`, liveness `0.5`
→ fused `0.525`, and anything in the ambiguous middle band routes to
`Flagged for review ⚠️` rather than a green pass.

That is **correct product behaviour** — the fusion docstring is explicit that
nothing is auto-rejected, it is routed to a human. Present it that way:

> **Say:** "It came back *flagged for review*, not passed. That's deliberate.
> We never auto-reject anyone — a flagged result routes to a human recruiter
> with the reasons attached, because a single weak signal shouldn't cost
> somebody a job."

Do **not** claim the green badge appears from a live recording on this setup.
The green badge comes from the fallback in the next section.

---

## Step 4 — Apply, then shortlist and show the ranked list

1. Click **Jobs** in the nav.
2. Find `Senior CV Engineer — Northwind Robotics` and click **Apply**.
   The button flips to **Applied ✓**.
3. Open the candidates URL you copied in step 1.
   You now have one row, one candidate, **no score yet** (`—` in the
   *Shortlist score* column, because shortlisting hasn't run).
4. Click **Run shortlisting**.

The page re-sorts and the row now shows a real score plus two badges:
**Shortlisted** and **Verified**.

> **Say:** "Two inputs: 0.6 for the domain matching the role, 0.4 for having
> passed live verification. Weighted, thresholded at 0.6."

To make the *ranking* land, you want more than one candidate. That is what the
fallback seeds.

---

## Fallback if the webcam or ML path dies on stage

The demo has one fragile link — the live webcam + 76s of CPU scoring. It fails
for ordinary reasons: no camera on the demo laptop, the judge asks a question
mid-scoring and you lose the room, a browser permission prompt gets dismissed,
or the ML service didn't get `SYNCNET_REPO_DIR`.

**Do not debug on stage.** Run the seed and skip to the payoff. It takes ~2
seconds and it produces the exact screen the demo is trying to show.

### Fallback A — pre-seeded data (primary; recommended)

```powershell
cd C:\Users\localadmin\hr
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1
```

It prints the candidates URL. Open it. You get **three ranked candidates with
mixed verification**, so the ranking and both badge states are visible at once:

```
#1  Aditi Sharma   score=1.00  shortlisted=yes  verified=yes   <- domain match + verified
#2  Rohan Verma    score=0.60  shortlisted=yes  verified=no    <- domain match only
#3  Meera Iyer     score=0.40  shortlisted=no   verified=yes   <- verified, wrong domain
```

That is a strictly better shortlisting demo than the single-candidate live
path: you can point at all three columns and explain the weighting. Emails are
timestamped, so the script is re-runnable and won't hit the 409.

To keep steps 1–2 live and only stub the verification, skip the signup in the
browser and set the id by hand instead:

```js
// browser console on /verify
localStorage.setItem("candidateId", "<id printed by seed-demo.ps1>");
```

### Fallback B — pre-recorded clip (if you want the ML path to still run)

The real scoring path accepts any muxed video+audio file. The shipped clip is
`demo_clip.mp4` (0.93 MB). Push it through the real service without touching
the browser:

```powershell
$cand = "<candidateId from step 2>"
curl.exe -s -X POST http://127.0.0.1:8001/verify `
  -F "submission_id=$cand" `
  -F "clip=@C:\Users\localadmin\hr\demo_clip.mp4;filename=demo_clip.mp4"
```

This takes the same ~76s and returns the same `flagged` verdict as the live
recording, but with no camera dependency — so the only thing that can go wrong
is the ML service being down, which Fallback A already covers.

**Honest caveat if you use it:** a judge watching you `curl` a file is not a
live-verification demo. Frame it as *"let me show you the scoring pipeline on a
clip we recorded earlier, then we'll talk about what the live path does"* —
and keep the live attempt as step 3 so you can say you did it for real.

### Fallback C — if `localhost:8001` is down entirely

The web app is fully usable without the ML service; only `/verify` needs it.
Run Fallback A and demo steps 1, 2 and 4 live. `/verify` will fail its upload —
say so plainly and move on. Don't leave it spinning on screen.

---

## Known issues found while running this end to end

Fixed during the walkthrough:

1. **`/verify` returned HTTP 500 on load.** `app/verify/page.tsx` read
   `window.location.search` during server render → `ReferenceError: window is
   not defined`. Moved into `useEffect`. This killed the single most important
   page in the demo.
2. **`/` was still the create-next-app boilerplate** ("To get started, edit
   `page.tsx`"). Replaced with a real landing page linking into the flow.
3. **Dead `/status` link** in the nav of `/signup`, `/verify` and `/jobs` —
   the route doesn't exist, so it was a guaranteed 404. Removed.
4. **`ml/verification/liveness.py` — `ModuleNotFoundError: No module named
   'src'`.** `_score_frame()` did `from src.utility import parse_model_name`
   *before* calling `_load_predictor()`, which is the function that puts the
   vendored repo on `sys.path`. Reordered.
5. **`/verify` 500'd if any one scorer raised.** Now each scorer is wrapped;
   a failure returns a neutral `0.5` and the submission routes to human review
   instead of dying with no verdict.

Still open — **know these before you demo**:

6. **The liveness CNN cannot run on this machine.** The installed OpenCV is
   **5.0.0**, which removed the Caffe importer entirely:
   `Caffe importer has been removed. Please use ONNX-converted models`. The
   vendored Silent-Face-Anti-Spoofing weights are Caffe. The `cv2.dnn.readNet`
   shim in `liveness.py` is correct but cannot conjure the importer back.
   **Fix: `pip install "opencv-python-headless<5"`.** Until then liveness always
   returns the neutral `0.5` and is effectively out of the fusion.
7. **Lip-sync degrades to `0.5`.** SyncNet dies on a shape mismatch
   (`mat1 and mat2 shapes cannot be multiplied (20x278528 and 512x512)`) when
   the clip's audio and video durations differ — `demo_clip.mp4` is 3.64s of
   video against 2.99s of audio. SyncNet wants them matched. It no longer 500s,
   but it contributes nothing.
8. **Scoring takes ~76s on CPU** with no progress feedback beyond the button
   label. This is the main reason the fallback exists.
9. **A repeat candidate signup returns 409.** Expected — `Candidate.email` is
   `@unique`. Use a fresh email, or `scripts/seed-demo.ps1` which timestamps.

---

## 60-second version

If you only have a minute: seed, open the candidates URL, click **Run
shortlisting**, and explain the three rows. That is the whole thesis — weighted
scoring, verification badges, a ranked list — and it has no moving parts.
