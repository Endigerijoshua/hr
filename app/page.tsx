import Link from "next/link";
import "./demo.css";

const STEPS = [
  {
    href: "/post-job",
    title: "1. Recruiter posts a job",
    body: "Company, title, domain, description, required skills. Lands you on the applicant table.",
  },
  {
    href: "/signup",
    title: "2. Candidate signs up + uploads resume",
    body: "Name, email, domain, resume file. Your candidate id is stored in the browser.",
  },
  {
    href: "/verify",
    title: "3. Candidate passes live verification",
    body: "Webcam + mic recording scored for gaze, lip-sync, audio and liveness. Sets the verified badge.",
  },
  {
    href: "/jobs",
    title: "4. Candidate applies to the job",
    body: "One click from the open-jobs table.",
  },
];

export default function Home() {
  return (
    <main className="wrap">
      <h1>NextGen — verified, anti-gaming candidate screening</h1>
      <nav className="nav">
        <a href="/post-job">Post job</a>
        <a href="/signup">Signup</a>
        <a href="/verify">Verify</a>
        <a href="/jobs">Jobs</a>
      </nav>

      <p className="valueprop">
        Shortlist the top 20% of applicants automatically — and catch the ones holding a
        prerecorded clip to the webcam before they ever reach your shortlist.
      </p>

      <p className="muted">
        Live video verification plus a ranked shortlist. Every candidate is scored on gaze, lip-sync,
        audio and liveness before they reach the recruiter&apos;s table, so a stolen or AI-generated
        clip shows up as a red badge instead of a name on a list.
      </p>

      <table>
        <thead>
          <tr>
            <th>Step</th>
            <th>What happens</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {STEPS.map((s) => (
            <tr key={s.href}>
              <td>
                <strong>{s.title}</strong>
                <div className="muted">{s.body}</div>
              </td>
              <td>
                <Link href={s.href}>Open →</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
