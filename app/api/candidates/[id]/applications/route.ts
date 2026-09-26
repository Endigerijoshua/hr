import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError } from "@/lib/api";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const applications = await prisma.application.findMany({
      where: { candidateId: id },
      orderBy: { shortlistScore: "desc" },
      include: { job: true },
    });

    return NextResponse.json(applications);
  } catch (error) {
    return jsonError(error);
  }
}
