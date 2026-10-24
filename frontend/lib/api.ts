export const backend = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const apiRoot = `${backend}/api/v1`;

export type User = { id: string; email: string };
export type StoredFile = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  drive_file_id: string | null;
  created_at: string;
};
export type FilePage = { items: StoredFile[]; total: number; page: number; page_size: number };
export type FilePreview =
  | { kind: "text" | "markdown"; text: string; truncated: boolean }
  | { kind: "table"; rows: string[][]; truncated: boolean }
  | { kind: "pdf"; url: string }
  | { kind: "image"; url: string };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiRoot}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return response.json() as Promise<T>;
}

function jsonPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export const api = {
  googleConnectUrl: `${apiRoot}/google/connect`,
  register: (email: string, password: string) =>
    jsonPost<User>("/auth/register", { email, password }),
  login: (email: string, password: string) =>
    jsonPost<User>("/auth/login", { email, password }),
  me: () => request<User>("/auth/me"),
  logout: () => jsonPost<{ signed_out: boolean }>("/auth/logout"),
  googleStatus: () => request<{ connected: boolean; email: string | null; gmail_ready: boolean }>("/google/status"),
  files: (page = 1, pageSize = 10) =>
    request<FilePage>(`/files?page=${page}&page_size=${pageSize}`),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<StoredFile>("/files", { method: "POST", body });
  },
  downloadUrl: (id: string) => `${apiRoot}/files/${encodeURIComponent(id)}`,
  preview: async (id: string, signal?: AbortSignal): Promise<FilePreview> => {
    const response = await fetch(`${apiRoot}/files/${encodeURIComponent(id)}/preview`, {
      credentials: "include", cache: "no-store", signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "Preview failed");
    }
    const type = response.headers.get("content-type") ?? "";
    if (type.startsWith("application/json")) return response.json() as Promise<FilePreview>;
    if (type.startsWith("application/pdf") || type.startsWith("image/")) {
      return { kind: type.startsWith("application/pdf") ? "pdf" : "image",
        url: URL.createObjectURL(await response.blob()) };
    }
    throw new ApiError(502, "Unsupported preview response");
  },
  sendToDrive: (id: string) =>
    jsonPost<{ drive_file_id: string; uploaded: boolean }>(
      `/files/${encodeURIComponent(id)}/drive`,
    ),
  createGmailDraft: (id: string, email: string) =>
    jsonPost<{ draft_id: string; recipient: string }>(
      `/files/${encodeURIComponent(id)}/gmail-draft`, { email },
    ),
};
