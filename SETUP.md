# SETUP

Requirements and gotchas for getting this running from a fresh clone. Read this
before `npm run dev` — two of the three failure modes below produce errors that
look like unrelated ML bugs.

## 1. Prerequisites

- **Node.js** 20+ (built and tested on Node 24)
- **Python** 3.12
- **ffmpeg** on `PATH` — required by `ml/verification/audio.py` to demux audio out
  of the uploaded clip. Without it the audio scorer returns neutral 0.5 rather
  than failing loudly.

## 2. OpenCV must be pinned below 5

```bash
pip install "opencv-python-headless<5"
```

The vendored anti-spoofing repo
(`third_party/Silent-Face-Anti-Spoofing/`) calls `cv2.dnn.readNetFromCaffe`,
which OpenCV 5 removed. `ml/verification/liveness.py:68-69` shims it to
`cv2.dnn.readNet`, but do not rely on 5.x regardless — the shim is a
compatibility band-aid, not a fix. OpenCV 4.14.0.94 is the version this was
last verified against.

> Note: installing this can drag `numpy` forward past what other packages in the
> same environment allow. If you see `inference-sdk requires numpy<2.4.0` or
> `opencv-python requires numpy<2.3.0`, pin numpy back into range.

## 3. `SYNCNET_REPO_DIR` must be set

The lip-sync scorer shells out to a local [joonson/syncnet_python](https://github.com/joonson/syncnet_python)
checkout. It is **not** configured automatically:

```bash
# PowerShell
$env:SYNCNET_REPO_DIR = "C:\path\to\hr\syncnet_python"
```

If unset, `/verify` still returns 200 — the lipsync scorer is wrapped in `_safe()`
(`ml/verification/service.py:40-48`), so it degrades to a neutral `0.5` with an
`error` field in `diagnostics` instead of failing the request. **Check
`diagnostics.lipsync` when judging a run; a silent 0.5 means the model never ran.**

## 4. Database — use `migrate deploy`, not `db push`

```bash
npx prisma migrate deploy     # applies migrations/ to your dev.db
npx prisma db seed            # optional; see scripts/seed-demo-v2.ps1 instead
```

`prisma migrate dev` will refuse to run and report *drift* if the database was
ever created with `db push`, because `db push` writes schema without recording
a migration. If you hit that:

```bash
npx prisma migrate reset --force --skip-seed   # destructive, dev only
npx prisma migrate dev --name <your_change>
```

Never use `db push` on this project. It is the only thing that produces drift, and
drift blocks every future migration.

`prisma/*.db` is gitignored, so **no database file is committed** — every fresh
clone starts empty and must run `migrate deploy` before the app will boot.

## 5. Seed the demo data

```bash
npm run dev                              # in one terminal
powershell -ExecutionPolicy Bypass -File scripts/seed-demo-v2.ps1
```

Creates 3 jobs (Sales Executive / Software Engineer / Financial Analyst) with 15
candidates each and a deliberate spread of resume quality and verification
outcomes. The script is idempotent — safe to re-run; it upserts by email and will
not create duplicates.

Then open http://localhost:3000/jobs.

## 6. Running the ML verification service

Separate process from the Next.js app, on port 8001:

```bash
cd C:\path\to\hr
python -m uvicorn ml.verification.service:app --port 8001
```

The `/verify` page posts to `http://localhost:8001/verify`. Point it elsewhere with
`BACKEND_BASE_URL` (defaults to `http://localhost:3000`).

Scoring is CPU-only and slow: **60-90 seconds per clip.** The UI shows a spinner
and progress bar for exactly this reason — a static "Scoring…" line reads as a
frozen page.

## 7. Gotcha: Prisma client lock on Windows

`npx prisma generate` fails with
`EPERM: operation not permitted, rename ...query_engine-windows.dll.node`
while a Next.js server is running, because the running process holds the DLL open.
**Stop the dev server before regenerating the Prisma client.**

## 8. Known issues

- **Gaze scorer is strict on synthetic/demo clips.** `score_gaze_from_path`
  frequently returns `0.0` on clips that are not a real centred webcam
  recording, which drags fused scores down and pushes submissions to
  `flagged`. Weights in `ml/verification/fusion.py` are untuned placeholders —
  they are not calibrated against a labelled set and should not be treated as
  production thresholds.
- **Four `react-hooks/set-state-in-effect` lint errors are suppressed, not
  fixed.** `app/jobs/page.tsx`, `app/jobs/[jobId]/candidates/page.tsx` and
  `app/verify/page.tsx` carry deliberate `eslint-disable-next-line` comments.
  The pattern is safe (one-time mount-time hydration from `localStorage` /
  query params, not a render loop) but it does bypass the React Compiler's
  cascading-render optimisation. Worth revisiting properly.
- **Scratch media is not gitignored.** `test_clip.mp4`, `test_clip.wav` and
  `shot-*.png` are local debug artefacts; add them to `.gitignore` if they start
  cluttering status output.
