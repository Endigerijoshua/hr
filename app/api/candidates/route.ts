import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError, missingFields } from "@/lib/api";

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
        resumeFileUrl: body.resumeFileUrl ?? null,
      },
    });

    return NextResponse.json(candidate, { status: 201 });
  } catch (error) {
    return jsonError(error);
  }
}
