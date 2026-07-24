import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { currentCustomerSession } from "@/platform/session/current-session";

export const dynamic = "force-dynamic";

export default async function AccountLayout({
  children,
}: {
  readonly children: ReactNode;
}) {
  if ((await currentCustomerSession()) === null) {
    redirect("/api/auth/login?returnTo=/account");
  }

  return children;
}
