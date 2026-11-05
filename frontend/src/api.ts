// Thin typed client for the FastAPI backend. Same origin, so no CORS.

const TOKEN_KEY = "roster.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session just won't survive a reload */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// FastAPI returns {detail: "text"} for rule errors and {detail: [{msg, loc}]} for validation errors.
function readableError(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
        const msg = (d.msg ?? "is invalid").replace(/^Value error, /, "");
        return field && field !== "body" ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
      })
      .join(". ");
  }
  return status >= 500 ? "The server hit a problem. Try again in a moment." : `Request failed (${status}).`;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("roster:signed-out"));
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, readableError(body, res.status));
  return body as T;
}

// ---------- types mirroring the API ----------

export type Module = "roster" | "resource" | "inventory";
export type Role = "owner" | "manager" | "staff";

export interface Tenant { id: string; name: string; modules: Module[]; created_at: string }
export interface User { id: string; email: string; name: string; role: Role; is_active: boolean; created_at: string }
export interface Me { user: User; tenant: Tenant }

export interface JobRole { id: string; name: string }
export interface ShiftType {
  id: string; name: string; start_time: string; end_time: string; job_role_id: string | null; overnight: boolean;
}
export interface Shift {
  id: string; user_id: string; start_at: string; end_at: string;
  shift_type_id: string | null; job_role_id: string | null; notes: string | null; created_by: string;
}

export type ResourceStatus = "available" | "out_of_service";
export interface ResourceType { id: string; name: string }
export interface Resource {
  id: string; resource_type_id: string; name: string; location: string | null; status: ResourceStatus; version: number;
}
export interface Booking {
  id: string; resource_id: string; start_at: string; end_at: string; purpose: string | null;
  status: "active" | "cancelled"; booked_by: string; client_id: string | null; cancelled_at: string | null;
}

export interface Client {
  id: string; name: string; email: string | null; phone: string | null; notes: string | null; is_active: boolean; created_at: string;
}
export interface ActivityItem { kind: "booking" | "usage"; at: string; title: string; detail: string | null }

export interface Product { id: string; name: string; unit: string; on_hand: number; reorder_level: number; low_stock: boolean }
export interface Movement {
  id: string; product_id: string; change: number; balance_after: number; reason: "received" | "used" | "counted";
  client_id: string | null; note: string | null; created_by: string; created_at: string;
}
