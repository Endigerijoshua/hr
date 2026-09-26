import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { jsonError, missingFields } from "@/lib/api";

export async function GET() {
  try {
    const jobs = await prisma.job.findMany({ orderBy: { id: "asc" } });
    return NextResponse.json(jobs);
  } catch (error) {
    return jsonError(error);
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const missing = missingFields(body, ["companyName", "title", "domain", "description", "requiredSkills"]);
    if (missing.length) {
      return NextResponse.json({ error: "Missing required fields", missing }, { status: 400 });
    }

    const job = await prisma.job.create({
      data: {
        companyName: body.companyName,
        title: body.title,
        domain: body.domain,
        description: body.description,
        requiredSkills: body.requiredSkills,
      },
    });

    return NextResponse.json(job, { status: 201 });
  } catch (error) {
    return jsonError(error);
  }
}
