"use client";

import { useEffect, useState } from "react";
import "../demo.css";

type Job = { id: string; companyName: string; title: string; domain: string; description: string; requiredSkills: string };

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [applied, setApplied] = useState<string[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time client-side hydration from localStorage on mount, not a render-loop risk
    setCandidateId(localStorage.getItem("candidateId"));
    fetch("/api/jobs")
      .then((r) => r.json())
      .then(setJobs);
  }, []);

  async function apply(job: Job) {
    if (!candidateId) {
      setMsg("No candidateId in localStorage â€” do /signup first.");
      return;
    }
    const res = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidateId, jobId: job.id, status: "applied" }),
    });
    const data = await res.json();
    if (!res.ok) {
      setMsg(`Apply failed ${res.status}: ${JSON.stringify(data)}`);
      return;
    }
    setApplied((a) => [...a, job.id]);
    setMsg(`Applied to ${job.title} at ${job.companyName} (${data.id})`);
  }

  return (
    <main className="wrap">
      <h1>Open jobs</h1>
      <nav className="nav">
        <a href="/signup">Signup</a>
        <a href="/verify">Verify</a>
        <a href="/jobs">Jobs</a>
        <a href="/post-job">Post job</a>
      </nav>
      <p className="muted">Candidate: <strong>{candidateId ?? "none â€” do /signup first"}</strong></p>
      {msg && <p className="status">{msg}</p>}

      {jobs === null ? (
        <p className="muted">Loadingâ€¦</p>
      ) : jobs.length === 0 ? (
        <p className="muted">No jobs posted yet. Use /post-job.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th>Company</th>
              <th>Domain</th>
              <th>Skills</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.title}</td>
                <td>{j.companyName}</td>
                <td>{j.domain}</td>
                <td className="muted">{j.requiredSkills}</td>
                <td>
                  <button onClick={() => apply(j)} disabled={applied.includes(j.id)}>
                    {applied.includes(j.id) ? "Applied âœ“" : "Apply"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
