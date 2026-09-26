"use client";

import { useEffect, useRef, useState } from "react";
import "../demo.css";

const DEFAULT_SECS = 15;

function verdict(result: string | undefined) {
  if (!result) return { text: "Not verified âŒ", cls: "no" };
  if (result === "pass") return { text: "Verified âœ…", cls: "yes" };
  if (result === "review") return { text: "Flagged for review âš ï¸", cls: "no" };
  return { text: "Not verified âŒ", cls: "no" };
}

export default function VerifyPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading" | "done" | "error">("idle");
  const [left, setLeft] = useState(0);
  const [secs, setSecs] = useState(DEFAULT_SECS);
  const [result, setResult] = useState<{ text: string; cls: string } | null>(null);
  const [raw, setRaw] = useState<string>("");

  useEffect(() => {
    const requested = Number(new URLSearchParams(window.location.search).get("secs"));
    if (requested > 0) setSecs(requested);
    setCandidateId(localStorage.getItem("candidateId"));
  }, []);

  async function start() {
    setRaw("");
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      const chunks: BlobPart[] = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);

      const done = new Promise<void>((resolve) => {
        rec.onstop = () => resolve();
      });

      rec.start();
      setPhase("recording");

      for (let s = secs; s > 0; s--) {
        setLeft(s);
        await new Promise((r) => setTimeout(r, 1000));
      }

      rec.stop();
      await done;
      stream.getTracks().forEach((t) => t.stop());
      setLeft(0);

      setPhase("uploading");
      const blob = new Blob(chunks, { type: rec.mimeType || "video/webm" });
      setRaw(`recorded ${(blob.size / 1024).toFixed(0)} KB as ${rec.mimeType}`);
      setRaw((p) => `${p}\nUploading to the verification service…\nThis step runs the gaze, lip-sync, audio and liveness models and takes 60-90s on CPU. Keep this tab focused.`);

      const fd = new FormData();
      fd.append("submission_id", candidateId ?? "");
      fd.append("clip", blob, "clip.webm");

      const res = await fetch("http://localhost:8001/verify", { method: "POST", body: fd });
      const data = await res.json();
      setRaw((p) => `${p}\nHTTP ${res.status} from /verify\n${JSON.stringify(data, null, 1)}`);
      setResult(verdict(data?.sent_to_backend?.result));
      setPhase("done");
    } catch (err) {
      setRaw(`Error: ${String(err)}`);
      setPhase("error");
    }
  }

  return (
    <main className="wrap">
      <h1>Live verification</h1>
      <nav className="nav">
        <a href="/signup">Signup</a>
        <a href="/verify">Verify</a>
        <a href="/jobs">Jobs</a>
      </nav>

      <p className="muted">
        Candidate: <strong>{candidateId ?? "none â€” go to /signup first"}</strong> Â· clip length {secs}s
      </p>

      <div className="toolbar">
        <button onClick={start} disabled={phase === "recording" || phase === "uploading"}>
          {phase === "recording" ? `Recording… ${left}s` : phase === "uploading" ? "Scoring (60-90s)…" : "Start verification"}
        </button>
        <a className="btn" href={`/verify?secs=${Math.max(3, secs - 5)}`}>Shorten clip to {Math.max(3, secs - 5)}s</a>
      </div>


      <video ref={videoRef} width={480} muted playsInline />

      {result && (
        <p>
          <span className={`badge ${result.cls}`}>{result.text}</span>
        </p>
      )}
      {raw && <p className="status">{raw}</p>}
    </main>
  );
}
