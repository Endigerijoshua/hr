"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const DOMAINS = ["engineering", "sales", "arts", "finance", "other"];

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [domain, setDomain] = useState("engineering");
  const [resume, setResume] = useState<File | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const res = await fetch("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          domain,
          resumeFileUrl: resume ? resume.name : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(`Error ${res.status}: ${JSON.stringify(data)}`);
        return;
      }
      localStorage.setItem("candidateId", data.id);
      localStorage.setItem("candidate", JSON.stringify(data));
      setStatus(`Created candidate ${data.id} â€” saved to localStorage. Redirectingâ€¦`);
      router.push("/verify");
    } catch (err) {
      setStatus(`Network error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <h1>Candidate signup</h1>
      <nav className="nav">
        <a href="/signup">Signup</a>
        <a href="/verify">Verify</a>
        <a href="/jobs">Jobs</a>
      </nav>
      <form onSubmit={onSubmit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
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
          Resume (pdf/docx)
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => setResume(e.target.files?.[0] ?? null)}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Creatingâ€¦" : "Create profile"}
        </button>
      </form>
      {status && <p className="status">{status}</p>}
    </main>
  );
}
