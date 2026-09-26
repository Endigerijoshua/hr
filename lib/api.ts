import { NextResponse } from "next/server";
import { Prisma } from "@prisma/client";

export function jsonError(error: unknown) {
  if (error instanceof Prisma.PrismaClientValidationError) {
    return NextResponse.json({ error: error.message }, { status: 400 });
  }
  if (error instanceof Prisma.PrismaClientKnownRequestError) {
    if (error.code === "P2002") {
      return NextResponse.json({ error: "Unique constraint failed", meta: error.meta }, { status: 409 });
    }
    if (error.code === "P2003") {
      return NextResponse.json({ error: "Related record not found", meta: error.meta }, { status: 400 });
    }
    return NextResponse.json({ error: error.message, code: error.code }, { status: 400 });
  }
  return NextResponse.json({ error: error instanceof Error ? error.message : "Unknown error" }, { status: 500 });
}

export function toNumber(value: unknown): number {
  return typeof value === "number" ? value : Number(value);
}

export function missingFields(body: Record<string, unknown>, fields: string[]) {
  return fields.filter((field) => body[field] === undefined || body[field] === null);
}
