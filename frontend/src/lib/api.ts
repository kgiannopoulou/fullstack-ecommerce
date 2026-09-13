// Backend base URL. Configurable via NEXT_PUBLIC_API_URL (see
// .env.local.example) since the frontend and backend are separate apps
// that could be deployed to different hosts.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

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
    // Backend error responses are always { error: string } (see
    // errorHandler.ts) — fall back to statusText if the body isn't JSON.
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new ApiError(res.status, body.error ?? "Request failed");
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
