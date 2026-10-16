
/**
 * File Vault API Client
 *
 * Centralizes communication with FastAPI.
 * Does not store authentication tokens.
 */

// --------------------------------------------------
// Configuration
// --------------------------------------------------

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

const API_V1 = `${API_BASE_URL}/api/v1`;


// --------------------------------------------------
// API response types
// --------------------------------------------------

export interface HealthResponse {
  status: string;
  service: string;
}

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface FileMetadata {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

export interface FileUploadResponse
  extends FileMetadata {
  message: string;
}

export interface FileListOptions {
  limit?: number;
  offset?: number;
}


// --------------------------------------------------
// Error handling
// --------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiErrorBody = {
  detail?: unknown;
};

function extractErrorMessage(
  body: unknown,
  fallback: string
): string {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body
  ) {
    const detail = (body as ApiErrorBody).detail;

    if (typeof detail === "string") {
      return detail;
    }

    // Pydantic validation errors often return
    // an array of error objects.
    if (Array.isArray(detail)) {
      return detail
        .map((error: unknown) => {
          if (
            error &&
            typeof error === "object" &&
            "msg" in error
          ) {
            return String(error.msg);
          }

          return "Invalid input";
        })
        .join("; ");
    }
  }

  return fallback;
}


// --------------------------------------------------
// HTTP request helpers
// --------------------------------------------------

interface RequestOptions {
  token?: string;
  signal?: AbortSignal;
}

interface JsonRequestOptions extends RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
}

function authHeaders(token?: string): Headers {
  const headers = new Headers();

  if (token) {
    headers.set(
      "Authorization",
      `Bearer ${token}`
    );
  }

  return headers;
}

async function throwIfNotOk(
  response: Response
): Promise<void> {
  if (response.ok) {
    return;
  }

  const body: unknown = await response
    .json()
    .catch(() => null);

  const message = extractErrorMessage(
    body,
    `Request failed with status ${response.status}`
  );

  throw new ApiError(
    response.status,
    message,
    body
  );
}

async function requestJson<T>(
  path: string,
  options: JsonRequestOptions = {}
): Promise<T> {
  const headers = authHeaders(options.token);

  headers.set("Accept", "application/json");

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(
    `${API_V1}${path}`,
    {
      method: options.method ?? "GET",
      headers,
      body:
        options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
      signal: options.signal,
      cache: "no-store",
    }
  );

  await throwIfNotOk(response);

  return (await response.json()) as T;
}


// --------------------------------------------------
// Public application API
// --------------------------------------------------

export const api = {
  // -----------------------------------------------
  // Health
  // -----------------------------------------------

    async health(): Promise<HealthResponse> {
    const response = await fetch(
        `${API_BASE_URL}/health`,
        { cache: "no-store" }
    );

    await throwIfNotOk(response);

    return response.json() as Promise<HealthResponse>;
    },
  // -----------------------------------------------
  // Authentication
  // -----------------------------------------------

  register(
    data: RegisterRequest
  ): Promise<User> {
    return requestJson<User>(
      "/auth/register",
      {
        method: "POST",
        body: data,
      }
    );
  },

  login(
    data: LoginRequest
  ): Promise<TokenResponse> {
    return requestJson<TokenResponse>(
      "/auth/login",
      {
        method: "POST",
        body: data,
      }
    );
  },

  getMe(
    token: string
  ): Promise<User> {
    return requestJson<User>(
      "/auth/me",
      { token }
    );
  },

  // -----------------------------------------------
  // File operations
  // -----------------------------------------------

  listFiles(
    token: string,
    options: FileListOptions = {}
  ): Promise<FileMetadata[]> {
    const params = new URLSearchParams();

    if (options.limit !== undefined) {
      params.set(
        "limit",
        String(options.limit)
      );
    }

    if (options.offset !== undefined) {
      params.set(
        "offset",
        String(options.offset)
      );
    }

    const query = params.toString();

    return requestJson<FileMetadata[]>(
      `/files${query ? `?${query}` : ""}`,
      { token }
    );
  },

  async uploadFile(
    token: string,
    file: File,
    signal?: AbortSignal
  ): Promise<FileUploadResponse> {
    const formData = new FormData();

    formData.append("file", file);

    const response = await fetch(
      `${API_V1}/files`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: formData,
        signal,
      }
    );

    await throwIfNotOk(response);

    return (
      await response.json()
    ) as FileUploadResponse;
  },

  async downloadFile(
    token: string,
    fileId: string,
    signal?: AbortSignal
  ): Promise<Blob> {
    const response = await fetch(
      `${API_V1}/files/${encodeURIComponent(fileId)}/download`,
      {
        headers: authHeaders(token),
        signal,
        cache: "no-store",
      }
    );

    await throwIfNotOk(response);

    return response.blob();
  },
};
