import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError } from "@/lib/api";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;

    const applications = await prisma.application.findMany({
      where: { jobId },
      orderBy: { shortlistScore: "desc" },
      include: { candidate: true },
    });

    return NextResponse.json(applications);
  } catch (error) {
    return jsonError(error);
  }
}
