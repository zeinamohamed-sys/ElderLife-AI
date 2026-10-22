import { translate } from "./i18n.jsx";

export const BASE = import.meta.env.VITE_API || "http://localhost:8000";

export const getToken = () => localStorage.getItem("token");
export const setToken = (t) => (t ? localStorage.setItem("token", t) : localStorage.removeItem("token"));

/** The language chosen in Settings; sent with every request so the API answers in it too. */
export const getLang = () => (localStorage.getItem("ui_lang") === "ar" ? "ar" : "en");
const headers = () => ({ "Accept-Language": getLang(), ...(getToken() ? { Authorization: "Bearer " + getToken() } : {}) });
const jsonHeaders = () => ({ "Content-Type": "application/json", ...headers() });

async function parse(res) {
  if (res.ok) return res.json();
  const body = await res.json().catch(() => null);
  throw new Error(body?.detail || translate(getLang(), "err.request_failed", { status: res.status }));
}

export async function api(path, method = "GET", body) {
  const res = await fetch(BASE + path, { method, headers: jsonHeaders(), body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && getToken()) { setToken(null); window.dispatchEvent(new Event("logout")); }
  return parse(res);
}

export async function elder(path, code, method = "GET") {
  const res = await fetch(BASE + path, { method, headers: { ...jsonHeaders(), "X-Elder-Code": code } });
  return parse(res);
}

export async function download(name) {
  const res = await fetch(`${BASE}/export/${name}`, { headers: jsonHeaders() });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob()); a.download = `${name}.csv`; a.click();
}
