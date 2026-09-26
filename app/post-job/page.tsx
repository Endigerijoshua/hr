"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import "../demo.css";

const DOMAINS = ["engineering", "sales", "arts", "finance", "other"];

export default function PostJobPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("engineering");
  const [description, setDescription] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companyName,
          title,
          domain,
          description,
          requiredSkills,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(`Error ${res.status}: ${JSON.stringify(data)}`);
        return;
      }
      setStatus(`Posted job ${data.id}. Opening applicants…`);
      router.push(`/jobs/${data.id}/candidates`);
    } catch (err) {
      setStatus(`Network error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <h1>Post a job</h1>
      <nav className="nav">
        <a href="/signup">Signup</a>
        <a href="/verify">Verify</a>
        <a href="/post-job">Post job</a>
      </nav>
      <form onSubmit={onSubmit}>
        <label>
          Company name
          <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} required />
        </label>
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        <label>
          Domain
          <select value={domain} onChange={(e) => setDomain(e.target.value)}>
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label>
          Description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} required />
        </label>
        <label>
          Required skills (comma-separated)
          <input
            value={requiredSkills}
            onChange={(e) => setRequiredSkills(e.target.value)}
            placeholder="python, ffmpeg, react"
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Posting…" : "Post job"}
        </button>
      </form>
      {status && <p className="status">{status}</p>}
    </main>
  );
}
