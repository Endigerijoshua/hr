import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError, missingFields, toNumber } from "@/lib/api";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const missing = missingFields(body, ["candidateId", "jobId"]);
    if (missing.length) {
      return NextResponse.json({ error: "Missing required fields", missing }, { status: 400 });
    }

    const application = await prisma.application.create({
      data: {
        candidateId: body.candidateId,
        jobId: body.jobId,
        shortlistScore: body.shortlistScore === undefined || body.shortlistScore === null
          ? null
          : toNumber(body.shortlistScore),
        shortlisted: body.shortlisted ?? false,
        status: body.status ?? "applied",
      },
    });

    return NextResponse.json(application, { status: 201 });
  } catch (error) {
    return jsonError(error);
  }
}
