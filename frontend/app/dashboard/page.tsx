
"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  ChangeEvent,
  FormEvent,
} from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import type { FileMetadata } from "@/lib/api";

// -----------------------------------------------
// Constants
// -----------------------------------------------

const PAGE_SIZE = 10;
const MAX_FILE_SIZE = 5 * 1024 * 1024;

const ALLOWED_TYPES: Record<string, string> = {
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".docx":
    "application/vnd.openxmlformats-officedocument." +
    "wordprocessingml.document",
  ".pptx":
    "application/vnd.openxmlformats-officedocument." +
    "presentationml.presentation",
};

// -----------------------------------------------
// Helper functions
// -----------------------------------------------

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(value: string): string {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "Unknown date"
    : date.toLocaleString();
}

function validateSelectedFile(file: File): string | null {
  if (file.size === 0) {
    return "Empty files are not allowed.";
  }

  if (file.size > MAX_FILE_SIZE) {
    return "File exceeds the 5 MiB limit.";
  }

  const extension = file.name
    .slice(file.name.lastIndexOf("."))
    .toLowerCase();

  const expectedMime = ALLOWED_TYPES[extension];

  if (!expectedMime) {
    return "Unsupported file type. Use PDF, PNG, JPG, DOCX or PPTX.";
  }

  if (file.type !== expectedMime) {
    return "The file MIME type does not match its extension.";
  }

  return null;
}

// -----------------------------------------------
// Dashboard
// -----------------------------------------------

export default function DashboardPage() {
  const router = useRouter();

  const {
    user,
    isAuthenticated,
    getAccessToken,
    logout,
  } = useAuth();

  // File listing
  const [files, setFiles] = useState<FileMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Upload
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const uploadInProgress = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Download
  const [downloadingId, setDownloadingId] = useState<string | null>(
    null
  );
  const [downloadError, setDownloadError] = useState<string | null>(
    null
  );
  const downloadInProgress = useRef(false);

  // ---------------------------------------------
  // Authentication helpers
  // ---------------------------------------------

  const handleLogout = useCallback(() => {
    logout();
    router.replace("/login");
  }, [logout, router]);

  const requireToken = useCallback((): string | null => {
    const token = getAccessToken();

    if (!token) {
      handleLogout();
      return null;
    }

    return token;
  }, [getAccessToken, handleLogout]);

  const handleApiError = useCallback(
    (error: unknown): string | null => {
      if (error instanceof ApiError && error.status === 401) {
        handleLogout();
        return null;
      }

      if (error instanceof ApiError) {
        return error.message;
      }

      return "Network request failed. Please try again.";
    },
    [handleLogout]
  );

  // ---------------------------------------------
  // Redirect unauthenticated users
  // ---------------------------------------------

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  // ---------------------------------------------
  // Fetch file metadata
  // ---------------------------------------------

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    let active = true;

    async function loadFiles() {
      const token = getAccessToken();

      if (!token) {
        handleLogout();
        return;
      }

      setIsLoadingFiles(true);
      setListError(null);

      try {
        const result = await api.listFiles(token, {
          limit: PAGE_SIZE + 1,
          offset: page * PAGE_SIZE,
        });

        if (!active) {
          return;
        }

        setHasMore(result.length > PAGE_SIZE);
        setFiles(result.slice(0, PAGE_SIZE));
      } catch (error) {
        if (!active) {
          return;
        }

        if (
          error instanceof ApiError &&
          error.status === 401
        ) {
          handleLogout();
          return;
        }

        setFiles([]);
        setHasMore(false);

        setListError(
          error instanceof ApiError
            ? error.message
            : "Unable to load your files. Please try again."
        );
      } finally {
        if (active) {
          setIsLoadingFiles(false);
        }
      }
    }

    void loadFiles();

    return () => {
      active = false;
    };
  }, [
    isAuthenticated,
    getAccessToken,
    handleLogout,
    page,
    refreshKey,
  ]);

  // ---------------------------------------------
  // File selection
  // ---------------------------------------------

  function handleFileChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0] ?? null;

    setSelectedFile(file);
    setUploadError(null);
    setUploadSuccess(null);

    if (file) {
      const validationError = validateSelectedFile(file);

      if (validationError) {
        setUploadError(validationError);
      }
    }
  }

  // ---------------------------------------------
  // Upload file
  // ---------------------------------------------

  async function handleUpload(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (uploadInProgress.current || !selectedFile) {
      return;
    }

    const validationError = validateSelectedFile(selectedFile);

    if (validationError) {
      setUploadError(validationError);
      return;
    }

    const token = requireToken();

    if (!token) {
      return;
    }

    uploadInProgress.current = true;
    setIsUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const uploaded = await api.uploadFile(
        token,
        selectedFile
      );

      setUploadSuccess(
        `${uploaded.filename} uploaded successfully.`
      );

      setSelectedFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      // Reload first page to show the new file.
      setPage(0);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      const message = handleApiError(error);

      if (message) {
        setUploadError(message);
      }
    } finally {
      uploadInProgress.current = false;
      setIsUploading(false);
    }
  }

  // ---------------------------------------------
  // Download file
  // ---------------------------------------------

  async function handleDownload(file: FileMetadata) {
    if (downloadInProgress.current) {
      return;
    }

    const token = requireToken();

    if (!token) {
      return;
    }

    downloadInProgress.current = true;
    setDownloadingId(file.id);
    setDownloadError(null);

    try {
      const blob = await api.downloadFile(token, file.id);

      const objectUrl = URL.createObjectURL(blob);

      try {
        const anchor = document.createElement("a");

        anchor.href = objectUrl;
        anchor.download = file.filename;

        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        // Give the browser time to initiate the download.
        window.setTimeout(() => {
          URL.revokeObjectURL(objectUrl);
        }, 1000);
      }
    } catch (error) {
      const message = handleApiError(error);

      if (message) {
        setDownloadError(message);
      }
    } finally {
      downloadInProgress.current = false;
      setDownloadingId(null);
    }
  }

  // ---------------------------------------------
  // Pagination and refresh
  // ---------------------------------------------

  function handleRefresh() {
    setRefreshKey((value) => value + 1);
  }

  function handleNextPage() {
    if (!isLoadingFiles && hasMore) {
      setPage((value) => value + 1);
    }
  }

  function handlePreviousPage() {
    if (!isLoadingFiles && page > 0) {
      setPage((value) => value - 1);
    }
  }

  // ---------------------------------------------
  // Unauthenticated screen
  // ---------------------------------------------

  if (!isAuthenticated || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-900">
        <p role="status" className="text-sm text-slate-600">
          Redirecting to login...
        </p>
      </main>
    );
  }

  // ---------------------------------------------
  // Dashboard UI
  // ---------------------------------------------

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">

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
              Securely upload, manage and download files.
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

        {/* Account */}

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

        {/* Upload */}

        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-lg font-semibold">
            Upload a file
          </h2>

          <p className="mt-2 text-sm text-slate-600">
            PDF, PNG, JPG, DOCX or PPTX. Maximum 5 MiB.
          </p>

          <form
            onSubmit={handleUpload}
            className="mt-5 space-y-4"
          >
            <div>
              <label
                htmlFor="file-upload"
                className="mb-2 block text-sm font-medium"
              >
                Choose a file
              </label>

              <input
                ref={fileInputRef}
                id="file-upload"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.docx,.pptx"
                onChange={handleFileChange}
                disabled={isUploading}
                className="block w-full rounded-lg border border-slate-300 bg-white p-3 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium disabled:opacity-60"
              />
            </div>

            {selectedFile && (
              <div className="rounded-lg bg-slate-50 p-3 text-sm">
                <p className="break-all font-medium">
                  {selectedFile.name}
                </p>

                <p className="mt-1 text-slate-500">
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>
            )}

            {uploadError && (
              <p role="alert" className="text-sm text-red-600">
                {uploadError}
              </p>
            )}

            {uploadSuccess && (
              <p
                role="status"
                className="text-sm text-green-700"
              >
                {uploadSuccess}
              </p>
            )}

            <button
              type="submit"
              disabled={
                !selectedFile ||
                isUploading ||
                Boolean(
                  selectedFile &&
                  validateSelectedFile(selectedFile)
                )
              }
              className="rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUploading ? "Uploading..." : "Upload file"}
            </button>
          </form>
        </section>

        {/* File listing */}

        <section className="mt-8 overflow-hidden rounded-xl border border-slate-200 bg-white">

          <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold">
                Stored Files
              </h2>

              <p className="mt-1 text-sm text-slate-500">
                Only files owned by your account are displayed.
              </p>
            </div>

            <button
              type="button"
              onClick={handleRefresh}
              disabled={isLoadingFiles}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
            >
              {isLoadingFiles ? "Loading..." : "Refresh"}
            </button>
          </div>

          {downloadError && (
            <div
              role="alert"
              className="border-b border-red-100 bg-red-50 px-5 py-3 text-sm text-red-700"
            >
              {downloadError}
            </div>
          )}

          {isLoadingFiles && (
            <div
              role="status"
              className="p-8 text-center text-sm text-slate-600"
            >
              Loading your files...
            </div>
          )}

          {!isLoadingFiles && listError && (
            <div className="p-8 text-center">
              <p role="alert" className="text-sm text-red-600">
                {listError}
              </p>

              <button
                type="button"
                onClick={handleRefresh}
                className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
              >
                Try again
              </button>
            </div>
          )}

          {!isLoadingFiles &&
            !listError &&
            files.length === 0 && (
              <div className="p-12 text-center">
                <p className="font-medium">
                  {page === 0
                    ? "No files uploaded yet"
                    : "No files on this page"}
                </p>

                <p className="mt-2 text-sm text-slate-500">
                  {page === 0
                    ? "Upload a file to get started."
                    : "Return to the previous page."}
                </p>
              </div>
            )}

          {!isLoadingFiles &&
            !listError &&
            files.length > 0 && (
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
                      <th scope="col" className="px-5 py-3">
                        Action
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

                        <td className="px-5 py-4">
                          <button
                            type="button"
                            onClick={() => {
                              void handleDownload(file);
                            }}
                            disabled={downloadingId !== null}
                            className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-slate-50 disabled:opacity-50"
                          >
                            {downloadingId === file.id
                              ? "Downloading..."
                              : "Download"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          {/* Pagination */}

          {!isLoadingFiles && !listError && (
            <div className="flex items-center justify-between border-t border-slate-200 p-5">
              <p className="text-sm text-slate-500">
                Page {page + 1}
              </p>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handlePreviousPage}
                  disabled={page === 0}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-40"
                >
                  Previous
                </button>

                <button
                  type="button"
                  onClick={handleNextPage}
                  disabled={!hasMore}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-40"
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
