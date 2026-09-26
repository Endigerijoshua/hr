import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError, missingFields } from "@/lib/api";

export async function GET() {
  try {
    const candidates = await prisma.candidate.findMany({ orderBy: { name: "asc" } });
    return NextResponse.json(candidates);
  } catch (error) {
    return jsonError(error);
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const missing = missingFields(body, ["name", "email", "domain"]);
    if (missing.length) {
      return NextResponse.json({ error: "Missing required fields", missing }, { status: 400 });
    }

    const candidate = await prisma.candidate.create({
      data: {
        name: body.name,
        email: body.email,
        domain: body.domain,
        skills: body.skills ?? "",
        resumeFileUrl: body.resumeFileUrl ?? null,
      },
    });

    return NextResponse.json(candidate, { status: 201 });
  } catch (error) {
    return jsonError(error);
  }
}
