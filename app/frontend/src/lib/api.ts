// Backend base URL. Configurable via NEXT_PUBLIC_API_URL (see
// .env.local.example) since the frontend and backend are separate apps
// that could be deployed to different hosts.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000";

// Server Components fetch from the server, which needs an absolute URL even
// when the browser uses relative /api paths through the Next.js proxy (see
// next.config.ts and docs/DEPLOY.md).
export const SERVER_API_URL = process.env.API_INTERNAL_URL || API_URL;

// Mirrors the backend's error body (see docs/API.md):
// { error: { code, message, details?, requestId } }. `code` lets pages react
// to specific failures, e.g. EMAIL_NOT_VERIFIED on checkout.
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string = "UNKNOWN",
    public details: { path: string; message: string }[] = []
  ) {
    super(message);
  }
}

export type Pagination = { page: number; pageSize: number; total: number; totalPages: number };

// Every API call in the app goes through this wrapper instead of calling
// fetch() directly, so the two cross-cutting concerns below are handled
// in exactly one place.
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    // Required for the httpOnly auth cookie to be sent to the backend,
    // since frontend (3000) and backend (4000) are different origins.
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    // Backend error responses are always { error: { code, message, ... } }
    // (see errorHandler.ts) — fall back to statusText if the body isn't JSON.
    const body = await res.json().catch(() => null);
    const error = body?.error;
    throw new ApiError(
      res.status,
      error?.message ?? res.statusText ?? "Request failed",
      error?.code,
      error?.details
    );
  }

  // Endpoints like logout/delete return 204 No Content with an empty body,
  // which res.json() would fail to parse.
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export type Product = {
  id: number;
  name: string;
  slug: string;
  description: string;
  price_cents: number;
  image_url: string | null;
  stock: number;
};

// Prices are handled as integer cents everywhere (matching the backend
// schema — see 0001_init.sql) and only converted to a display string here,
// at the last moment, to avoid floating-point rounding issues.
export function formatPrice(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
}
