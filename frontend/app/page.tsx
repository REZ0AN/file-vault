
import { Suspense } from "react";
import { connection } from "next/server";

type HealthResponse = {
  status: string;
  service: string;
};

async function checkBackend(): Promise<{
  connected: boolean;
  data: HealthResponse | null;
}> {
  // Mark this health check as request-time work.
  // Keep it outside try/catch.
  await connection();

  try {
    const response = await fetch(
      "http://127.0.0.1:8000/health",
      {
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      }
    );

    if (!response.ok) {
      return {
        connected: false,
        data: null,
      };
    }

    const data: HealthResponse = await response.json();

    return {
      connected: true,
      data,
    };
  } catch {
    return {
      connected: false,
      data: null,
    };
  }
}

// Async component handles dynamic backend data.
async function BackendStatus() {
  const backend = await checkBackend();

  return (
    <div className="rounded-xl border p-6">
      <h2 className="text-lg font-semibold">
        Backend Connection
      </h2>

      <p className="mt-3">
        Status:{" "}
        <span
          className={
            backend.connected
              ? "font-semibold text-green-600"
              : "font-semibold text-red-600"
          }
        >
          {backend.connected
            ? "Connected"
            : "Disconnected"}
        </span>
      </p>

      {backend.data && (
        <div className="mt-4 space-y-1 text-sm">
          <p>
            Service: {backend.data.service}
          </p>
          <p>
            Health: {backend.data.status}
          </p>
        </div>
      )}
    </div>
  );
}

// Synchronous page component provides a static shell.
export default function HomePage() {
  return (
    <main className="mx-auto min-h-screen max-w-3xl p-8">
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">
            File Vault
          </h1>

          <p className="mt-2 text-gray-500">
            Next.js + FastAPI + PostgreSQL
          </p>
        </div>

        <Suspense
          fallback={
            <div className="rounded-xl border p-6">
              <h2 className="text-lg font-semibold">
                Backend Connection
              </h2>
              <p className="mt-3 text-gray-500">
                Checking backend connection...
              </p>
            </div>
          }
        >
          <BackendStatus />
        </Suspense>

        <p className="text-sm text-gray-500">
          Authentication and file management
          will be added in the next steps.
        </p>
      </div>
    </main>
  );
}
