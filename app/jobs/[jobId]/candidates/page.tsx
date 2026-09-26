"use client";

import { use, useCallback, useEffect, useState } from "react";
import "../../../demo.css";

type Row = {
  id: string;
  shortlistScore: number | null;
  shortlisted: boolean;
  status: string;
  candidate: { id: string; name: string; domain: string; verified: boolean };
  matchedSkills?: string[];
  missingSkills?: string[];
};

const VERDICT_CLASS: Record<string, string> = {
  pass: "pass",
  flagged: "flagged",
  fail: "fail",
};

export default function JobCandidatesPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, string>>({});
  const [job, setJob] = useState<{ id: string; companyName: string; title: string; requiredSkills: string } | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [appsRes, jobsRes, vsRes] = await Promise.all([
      fetch(`/api/jobs/${jobId}/applications`),
      fetch("/api/jobs"),
      fetch("/api/verification-sessions"),
    ]);
    if (appsRes.ok) setRows(await appsRes.json());
    else setStatus(`Error ${appsRes.status}: ${await appsRes.text()}`);
    if (vsRes.ok) {
      const sessions: { candidateId: string; result: string }[] = await vsRes.json();
      const latest: Record<string, string> = {};
      for (const s of sessions) latest[s.candidateId] = s.result;
      setVerdicts(latest);
    }
    if (jobsRes.ok) {
      const all = await jobsRes.json();
      setJob(all.find((j: { id: string }) => j.id === jobId) ?? null);
    }
  }, [jobId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time
    // client-side hydration from window/query params on mount, not a
    // render-loop risk
    load();
  }, [load]);

  async function runShortlist() {
    setBusy(true);
    setStatus("Running shortlisting…");
    try {
      const res = await fetch(`/api/jobs/${jobId}/shortlist`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setStatus(`Error ${res.status}: ${JSON.stringify(data)}`);
      } else {
        setStatus(`Shortlisted ${data.updated.filter((a: Row) => a.shortlisted).length} of ${data.updated.length} (threshold ${data.threshold}).`);
        await load();
      }
    } catch (err) {
      setStatus(`Network error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <h1>{job ? `${job.title} — ${job.companyName}` : "Applicants"}</h1>
      <nav className="nav">
        <a href="/post-job">Post job</a>
      </nav>
      {job && <p className="muted">Required skills: {job.requiredSkills}</p>}

      <div className="toolbar">
        <button onClick={runShortlist} disabled={busy}>
          {busy ? "Running…" : "Run shortlisting"}
        </button>
        <button onClick={load} disabled={busy}>
          Refresh
        </button>
      </div>

      {status && <p className="status">{status}</p>}

      <p className="muted">
        Ranked on required-skill overlap (55%), domain match (25%) and anti-spoofing verification (20%).
        Cut-off at {rows?.length ? Math.round((rows.filter((r) => r.shortlisted).length / rows.length) * 100) : 0}% shortlisted.
      </p>

      {rows === null ? (
        <p className="muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No applicants yet. POST to /api/applications for this jobId.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Candidate</th>
              <th>Domain</th>
              <th>Shortlist score</th>
              <th>Skills matched</th>
              <th>Decision</th>
              <th>Verification</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const verdict = verdicts[row.candidate.id] ?? "flagged";
              const pct = Math.round((row.shortlistScore ?? 0) * 100);
              return (
                <tr key={row.id} className={row.shortlisted ? "shortlisted" : undefined}>
                  <td className="rank">{i + 1}</td>
                  <td>{row.candidate.name}</td>
                  <td className="muted">{row.candidate.domain}</td>
                  <td className="num">
                    <div>{row.shortlistScore === null ? "—" : row.shortlistScore.toFixed(2)}</div>
                    {row.shortlistScore !== null && (
                      <div className="skillbar" aria-hidden="true">
                        <span style={{ width: `${pct}%` }} />
                      </div>
                    )}
                  </td>
                  <td className="muted">
                    {row.matchedSkills?.length ? row.matchedSkills.join(", ") : "—"}
                  </td>
                  <td>
                    <span className={`verdict ${row.shortlisted ? "pass" : "fail"}`}>
                      {row.shortlisted ? "Shortlisted" : "Not shortlisted"}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${VERDICT_CLASS[verdict] ?? "flagged"}`}>{verdict}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </main>
  );
}
