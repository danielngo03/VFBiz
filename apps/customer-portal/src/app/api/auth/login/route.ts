import { NextResponse } from "next/server";
import { startCustomerAuthorization } from "@/platform/auth/start-authorization";

export async function GET(request: Request) {
  return startCustomerAuthorization(request, "login");
}

export async function DELETE() {
  const response = NextResponse.json(
    { error: "method_not_allowed" },
    { status: 405 },
  );
  response.headers.set("Allow", "GET");
  return response;
}
