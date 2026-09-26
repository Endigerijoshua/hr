import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError } from "@/lib/api";

/**
 * Hackathon stand-in for scripts/run_shortlist_for_job.py.
 *
 * The real resume_screening.shortlist.run() scores resume *text* read from
 * files on disk. Candidate.skills is the persisted extraction of that text, so
 * the signal the Python scorer would use is available here too: we score how
 * much of a job's requiredSkills list a candidate actually hits.
 *
 * Scoring (each term in [0,1]):
 *   skills   0.55 - fraction of the job's required skills the candidate has
 *   domain   0.25 - candidate's declared domain matches the job's
 *   verified 0.20 - cleared the anti-spoofing / liveness pipeline
 *
 * Skills dominates deliberately: it is the only term that distinguishes a
 * strong applicant from a weak one *within* a domain, which is what makes the
 * cutoff cut somewhere in the middle instead of admitting a whole domain.
 *
 * TODO: re-tune the weights against a real labelled set; don't ship as gospel.
 */
const WEIGHT_SKILLS = 0.55;
const WEIGHT_DOMAIN = 0.25;
const WEIGHT_VERIFIED = 0.2;
const SHORTLIST_THRESHOLD = 0.6;

/** "Python, React, SQL" -> Set{"python","react","sql"} */
function skillSet(raw: string | null | undefined): Set<string> {
  return new Set(
    (raw ?? "")
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
  );
}

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;

    const job = await prisma.job.findUnique({ where: { id: jobId } });
    if (!job) {
      return NextResponse.json({ error: `Job ${jobId} not found` }, { status: 404 });
    }

    const required = skillSet(job.requiredSkills);
    const applications = await prisma.application.findMany({
      where: { jobId },
      include: { candidate: true },
    });

    const scored = applications.map((application) => {
      const have = skillSet(application.candidate.skills);
      const matched = [...required].filter((s) => have.has(s));
      const skillsRatio = required.size === 0 ? 0 : matched.length / required.size;
      const domainMatch = application.candidate.domain === job.domain ? 1 : 0;

      const score = Number(
        (
          WEIGHT_SKILLS * skillsRatio +
          WEIGHT_DOMAIN * domainMatch +
          WEIGHT_VERIFIED * (application.candidate.verified ? 1 : 0)
        ).toFixed(4)
      );

      return {
        id: application.id,
        score,
        matched,
        missing: [...required].filter((s) => !have.has(s)),
      };
    });

    await prisma.$transaction(
      scored.map((s) =>
        prisma.application.update({
          where: { id: s.id },
          data: { shortlistScore: s.score, shortlisted: s.score >= SHORTLIST_THRESHOLD },
        })
      )
    );

    const updated = await prisma.application.findMany({
      where: { jobId },
      orderBy: { shortlistScore: "desc" },
      include: { candidate: true },
    });

    return NextResponse.json({
      jobId,
      threshold: SHORTLIST_THRESHOLD,
      requiredSkills: [...required],
      updated: updated.map((a) => {
        const detail = scored.find((s) => s.id === a.id);
        return {
          ...a,
          matchedSkills: detail?.matched ?? [],
          missingSkills: detail?.missing ?? [],
        };
      }),
    });
  } catch (error) {
    return jsonError(error);
  }
}
