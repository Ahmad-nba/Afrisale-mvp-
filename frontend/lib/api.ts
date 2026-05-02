/**
 * Thin fetch wrapper for the seller API.
 *
 * Auth model (single-seller MVP): the agent shares a URL like
 *   https://app.example.com/seller/upload?t=<SELLER_ACCESS_TOKEN>
 * The token is read from the URL once and cached in sessionStorage so the
 * seller can navigate between pages without losing the bearer.
 */

const TOKEN_STORAGE_KEY = "afrisale_seller_token";
const API_BASE_ENV = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function getAuthToken(): string {
  if (!isBrowser()) return "";
  try {
    const url = new URL(window.location.href);
    const fromQuery = (url.searchParams.get("t") || "").trim();
    if (fromQuery) {
      window.sessionStorage.setItem(TOKEN_STORAGE_KEY, fromQuery);
      return fromQuery;
    }
    const cached = window.sessionStorage.getItem(TOKEN_STORAGE_KEY) || "";
    return cached.trim();
  } catch {
    return "";
  }
}

function apiBase(): string {
  if (API_BASE_ENV) return API_BASE_ENV;
  // Fallback for local dev where the FastAPI app runs on :8000 alongside
  // the Next.js dev server on :3000.
  return "http://localhost:8000";
}

export interface ApiOptions {
  method?: "GET" | "POST";
  body?: BodyInit | null;
  headers?: Record<string, string>;
}

export async function callApi<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(opts.headers || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(`${apiBase()}${path}`, {
    method: opts.method || "GET",
    body: opts.body,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "";
    try {
      const data = await response.json();
      detail = (data && (data.detail || data.message)) || "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    const message =
      detail || `${response.status} ${response.statusText || "Request failed"}`;
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface CatalogueItem {
  id: number;
  name: string;
  description: string;
  price: number;
  stock_total: number;
  stock_label: "in" | "low" | "out";
  variants_count: number;
  image_url: string;
  image_gcs_uri: string;
}

export interface OrderItem {
  product_name: string;
  size: string;
  color: string;
  quantity: number;
  unit_price: number;
}

export interface SellerOrder {
  id: number;
  buyer_name: string;
  phone: string;
  delivery_location: string;
  items: OrderItem[];
  total_price: number;
  status: string;
}

export function getCatalogue(): Promise<CatalogueItem[]> {
  return callApi<CatalogueItem[]>("/api/seller/catalogue");
}

export function getOrders(): Promise<SellerOrder[]> {
  return callApi<SellerOrder[]>("/api/seller/orders");
}

export function createProduct(form: FormData): Promise<{
  id: number;
  name: string;
  variant_id: number;
  price: number;
  stock_quantity: number;
  image_url?: string;
  image_error?: string;
}> {
  return callApi("/api/seller/products", {
    method: "POST",
    body: form,
  });
}
