// Cliente de la API de NEXUS (docs/NEXUS_API_SPEC.md §5).

export type ApiErrorBody = {
  code: string;
  message: string;
  fields?: Record<string, string>;
  [key: string]: unknown;
};

export class ApiError extends Error {
  status: number;
  code: string;
  fields?: Record<string, string>;
  body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.fields = body.fields;
    this.body = body;
  }
}

/** Texto para mostrar al usuario: el detalle del bot si lo hay, si no el mensaje traducido de la API. */
export function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return typeof err.body.detail === "string" ? err.body.detail : err.message || fallback;
  return fallback;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export function loginUrl(next?: string): string {
  const target = next ?? (typeof window !== "undefined" ? window.location.pathname + window.location.search : "/dashboard");
  return `/api/v1/auth/login?next=${encodeURIComponent(target)}`;
}

async function ensureCsrf(): Promise<string | null> {
  let token = readCookie("nexus_csrf");
  if (!token) {
    await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
    token = readCookie("nexus_csrf");
  }
  return token;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  if (method !== "GET" && method !== "HEAD") {
    const csrf = await ensureCsrf();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const res = await fetch(`/api/v1${path}`, { ...init, method, headers, body, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    // respuesta sin cuerpo JSON (por ejemplo, la API está apagada)
  }
  if (!res.ok) {
    const errBody = (data as { error?: ApiErrorBody } | null)?.error ?? {
      code: res.status >= 500 ? "api_unavailable" : "internal",
      message: res.statusText,
    };
    if (res.status === 401 && typeof window !== "undefined") {
      window.location.href = loginUrl();
    }
    throw new ApiError(res.status, errBody);
  }
  return data as T;
}
