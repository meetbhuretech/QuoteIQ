const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Session = {
  access_token: string;
  role: string;
  user: { full_name: string; email: string };
  organization: { id: string; name: string } | null;
};

export function token() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("quoteiq_token");
}

export function saveSession(session: Session) {
  localStorage.setItem("quoteiq_token", session.access_token);
  localStorage.setItem("quoteiq_role", session.role || "");
  localStorage.setItem("quoteiq_name", session.user.full_name);
  localStorage.setItem("quoteiq_org", session.organization?.name || "");
}

export function clearSession() {
  ["quoteiq_token", "quoteiq_role", "quoteiq_name", "quoteiq_org"].forEach((key) => localStorage.removeItem(key));
}

export async function api<T>(path: string, options: RequestInit & { form?: boolean } = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const current = token();
  if (current) headers.set("Authorization", `Bearer ${current}`);
  if (!options.form && options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${base}${path}`, { ...options, headers });
  if (response.status === 401 && !path.includes("/auth/login") && !path.includes("/auth/register")) {
    clearSession();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : "The request failed.");
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("pdf") || type.startsWith("image/")) return (await response.blob()) as T;
  return response.json();
}
