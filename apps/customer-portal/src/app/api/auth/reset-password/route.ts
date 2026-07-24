import { NextResponse } from "next/server";
import { passwordResetUrl } from "@/platform/auth/oidc";
import { hardenPrivateResponse } from "@/platform/api/http-responses";

export async function GET() {
  const response = NextResponse.redirect(passwordResetUrl());
  return hardenPrivateResponse(response);
}
