
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import type { FileMetadata } from "@/lib/api";

const PAGE_SIZE = 10;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(date: string): string {
  return new Date(date).toLocaleString();
}

export default function DashboardPage() {
  const router = useRouter();

  const {
    user,
    isAuthenticated,
    getAccessToken,
    logout,
  } = useAuth();

  const [files, setFiles] = useState<FileMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [refreshKey, setRefreshKey] = useState(0);

  // ------------------------------------------------
  // Redirect unauthenticated users
  // ------------------------------------------------

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  // ------------------------------------------------
  // Load files
  // ------------------------------------------------

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    const controller = new AbortController();
    let active = true;

    async function loadFiles() {
      const token = getAccessToken();

      if (!token) {
        logout();
        return;
      }

      setIsLoadingFiles(true);
      setError(null);

      try {
        // Request one extra record to determine
        // whether another page exists.
        const result = await api.listFiles(token, {
          limit: PAGE_SIZE + 1,
          offset: page * PAGE_SIZE,
        });

        if (!active || controller.signal.aborted) {
          return;
        }

        setHasMore(result.length > PAGE_SIZE);
        setFiles(result.slice(0, PAGE_SIZE));
      } catch (err) {
        if (!active || controller.signal.aborted) {
          return;
        }

        if (
          err instanceof ApiError &&
          err.status === 401
        ) {
          logout();
          return;
        }

        setFiles([]);
        setHasMore(false);

        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError(
            "Unable to load your files. Check the connection and try again."
          );
        }
      } finally {
        if (active && !controller.signal.aborted) {
          setIsLoadingFiles(false);
        }
      }
    }

    void loadFiles();

    return () => {
      active = false;
      controller.abort();
    };
  }, [
    isAuthenticated,
    getAccessToken,
    logout,
    page,
    refreshKey,
  ]);

  // ------------------------------------------------
  // Actions
  // ------------------------------------------------

  const handleLogout = useCallback(() => {
    logout();
    router.replace("/login");
  }, [logout, router]);

  function handleRefresh() {
    setRefreshKey((value) => value + 1);
  }

  function handleNextPage() {
    if (!hasMore || isLoadingFiles) {
      return;
    }

    setPage((value) => value + 1);
  }

  function handlePreviousPage() {
    if (page === 0 || isLoadingFiles) {
      return;
    }

    setPage((value) => value - 1);
  }

  // ------------------------------------------------
  // Redirecting state
  // ------------------------------------------------

  if (!isAuthenticated || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-900">
        <p role="status" className="text-sm text-slate-600">
          Redirecting to login...
        </p>
      </main>
    );
  }

  // ------------------------------------------------
  // Dashboard UI
  // ------------------------------------------------

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        {/* Header */}

        <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-500">
              FILE VAULT
            </p>

            <h1 className="mt-2 text-3xl font-bold tracking-tight">
              My Files
            </h1>

            <p className="mt-2 text-sm text-slate-600">
              Your personal, secure file storage.
            </p>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-100"
          >
            Logout
          </button>
        </header>

        {/* Account information */}

        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-lg font-semibold">
            Account
          </h2>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Email
              </p>

              <p className="mt-1 break-all text-sm font-medium">
                {user.email}
              </p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Member since
              </p>

              <p className="mt-1 text-sm">
                {formatDate(user.created_at)}
              </p>
            </div>
          </div>
        </section>

        {/* Files section */}

        <section className="mt-8 overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold">
                Stored Files
              </h2>

              <p className="mt-1 text-sm text-slate-500">
                Only files belonging to your account
                are displayed.
              </p>
            </div>

            <button
              type="button"
              onClick={handleRefresh}
              disabled={isLoadingFiles}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoadingFiles ? "Loading..." : "Refresh"}
            </button>
          </div>

          {/* Loading state */}

          {isLoadingFiles && (
            <div
              role="status"
              className="p-8 text-center text-sm text-slate-600"
            >
              Loading your files...
            </div>
          )}

          {/* Error state */}

          {!isLoadingFiles && error && (
            <div className="p-8 text-center">
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>

              <button
                type="button"
                onClick={handleRefresh}
                className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Try again
              </button>
            </div>
          )}

          {/* Empty state */}

          {!isLoadingFiles && !error && files.length === 0 && (
            <div className="p-12 text-center">
              <p className="text-base font-medium">
                {page === 0
                  ? "No files uploaded yet"
                  : "No files on this page"}
              </p>

              <p className="mt-2 text-sm text-slate-500">
                {page === 0
                  ? "Files you upload will appear here."
                  : "Go back to the previous page."}
              </p>
            </div>
          )}

          {/* File table */}

          {!isLoadingFiles && !error && files.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th scope="col" className="px-5 py-3">
                      Filename
                    </th>

                    <th scope="col" className="px-5 py-3">
                      Type
                    </th>

                    <th scope="col" className="px-5 py-3">
                      Size
                    </th>

                    <th scope="col" className="px-5 py-3">
                      Uploaded
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {files.map((file) => (
                    <tr key={file.id}>
                      <td className="max-w-64 break-words px-5 py-4 font-medium">
                        {file.filename}
                      </td>

                      <td className="px-5 py-4 text-slate-600">
                        {file.mime_type}
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                        {formatFileSize(file.size_bytes)}
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                        {formatDate(file.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}

          {!isLoadingFiles && !error && (
            <div className="flex items-center justify-between border-t border-slate-200 p-5">
              <p className="text-sm text-slate-500">
                Page {page + 1}
              </p>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handlePreviousPage}
                  disabled={page === 0}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Previous
                </button>

                <button
                  type="button"
                  onClick={handleNextPage}
                  disabled={!hasMore}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
