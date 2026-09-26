import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError, missingFields, toNumber } from "@/lib/api";

const SCORE_FIELDS = ["gazeScore", "lipSyncScore", "audioScore", "livenessScore"] as const;

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // The Python fusion service (ml/verification/fusion.py) sends `submissionId`;
    // this schema keys sessions by candidate. Accept either.
    const candidateId = body.candidateId ?? body.submissionId;
    if (!candidateId) {
      return NextResponse.json(
        { error: "Missing required field: candidateId (or submissionId)" },
        { status: 400 }
      );
    }

    const missing = missingFields(body, [...SCORE_FIELDS, "result"]);
    if (missing.length) {
      return NextResponse.json({ error: "Missing required fields", missing }, { status: 400 });
    }

    const candidate = await prisma.candidate.findUnique({ where: { id: candidateId } });
    if (!candidate) {
      return NextResponse.json(
        { error: `Candidate ${candidateId} not found. Create the candidate via POST /api/candidates first.` },
        { status: 400 }
      );
    }

    const passed = body.result === "pass";

    const session = await prisma.verificationSession.create({
      data: {
        candidateId,
        gazeScore: toNumber(body.gazeScore),
        lipSyncScore: toNumber(body.lipSyncScore),
        audioScore: toNumber(body.audioScore),
        livenessScore: toNumber(body.livenessScore),
        result: body.result,
        reviewedByHR: body.reviewedByHR ?? false,
      },
    });

    if (passed !== candidate.verified) {
      await prisma.candidate.update({ where: { id: candidateId }, data: { verified: passed } });
    }

    return NextResponse.json(session, { status: 201 });
  } catch (error) {
    return jsonError(error);
  }
}
