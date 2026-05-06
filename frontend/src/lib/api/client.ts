/**
 * HTTP client con bearer auth + auto-refresh su 401.
 *
 * Flusso:
 * 1. Aggiunge `Authorization: Bearer <access>` se presente
 * 2. Su 401 (e con refresh token disponibile, e non in chiamata auth):
 *    chiama /api/auth/refresh, riprova UNA volta
 * 3. Se anche il refresh fallisce: pulisce i token e notifica
 *    `onAuthInvalid` (registrato dall'AuthContext) → redirect login
 */

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
} from "@/lib/auth/tokenStorage";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type AuthInvalidHandler = () => void;
let onAuthInvalid: AuthInvalidHandler = () => {};

/** Registra il callback chiamato quando il refresh fallisce. */
export function setOnAuthInvalid(handler: AuthInvalidHandler): void {
  onAuthInvalid = handler;
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight !== null) return refreshInFlight;

  refreshInFlight = (async () => {
    const refresh = getRefreshToken();
    if (refresh === null) return false;
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access_token: string };
      setAccessToken(data.access_token);
      return true;
    } catch {
      return false;
    }
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Se true, NON tenta refresh in caso di 401. Default: false. */
  skipAuthRefresh?: boolean;
}

async function buildRequest(
  path: string,
  options: ApiFetchOptions,
): Promise<{ url: string; init: RequestInit }> {
  const headers = new Headers(options.headers);
  // FormData: il browser deve generare ``multipart/form-data; boundary=...``.
  // Se settiamo manualmente ``application/json`` o un altro Content-Type
  // l'upload si rompe (boundary mancante, parser server fallisce).
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (
    !headers.has("Content-Type") &&
    options.body !== undefined &&
    !isFormData
  ) {
    headers.set("Content-Type", "application/json");
  }
  const access = getAccessToken();
  if (access !== null) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  let body: BodyInit | undefined;
  if (options.body === undefined) {
    body = undefined;
  } else if (typeof options.body === "string") {
    body = options.body;
  } else if (isFormData) {
    body = options.body as FormData;
  } else {
    body = JSON.stringify(options.body);
  }
  const init: RequestInit = {
    ...options,
    headers,
    body,
  };
  return { url: `${API_BASE_URL}${path}`, init };
}

/** Fetch grezzo con auth + auto-refresh. Usa `apiJson` per risposte JSON. */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const isAuthEndpoint = path.startsWith("/api/auth/");
  const { url, init } = await buildRequest(path, options);
  let res = await fetch(url, init);

  if (
    res.status === 401 &&
    !isAuthEndpoint &&
    !options.skipAuthRefresh &&
    getRefreshToken() !== null
  ) {
    const ok = await tryRefresh();
    if (ok) {
      const retry = await buildRequest(path, options);
      res = await fetch(retry.url, retry.init);
    } else {
      clearTokens();
      onAuthInvalid();
    }
  }

  return res;
}

interface ErrorBody {
  detail?: string | unknown;
}

/**
 * Fetch con parsing JSON tipizzato. Lancia `ApiError` su status >= 400.
 * Per status 204 (No Content) ritorna `undefined as T`.
 */
export async function apiJson<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const res = await apiFetch(path, options);
  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  }

  if (!res.ok) {
    const errBody = body as ErrorBody | null;
    const detail = errBody?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : detail !== undefined
          ? JSON.stringify(detail)
          : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, detail);
  }

  return body as T;
}
