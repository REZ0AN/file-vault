import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backend, type User } from "@/lib/api";
import DashboardClient from "./DashboardClient";

export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const token = (await cookies()).get("filevault_auth")?.value;
  if (!token) redirect("/");

  const response = await fetch(`${backend}/api/v1/auth/me`, {
    headers: { Cookie: `filevault_auth=${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/");
  if (!response.ok) throw new Error("Unable to verify your session");
  const user = await response.json() as User;
  const error = (await searchParams).error;
  return <DashboardClient user={user} initialMessage={typeof error === "string" ? error : ""} />;
}
