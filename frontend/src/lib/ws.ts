import { apiBase, getToken } from "./api";

export function makeWsUrl(path: string): string {
  const url = new URL(apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const [pathname, search = ""] = path.split("?");
  url.pathname = pathname;
  const params = new URLSearchParams(search);
  const token = getToken();
  if (token && !params.has("token")) {
    params.set("token", `Bearer ${token}`);
  }
  url.search = params.toString();
  return url.toString();
}

export function openWs(path: string): WebSocket {
  return new WebSocket(makeWsUrl(path));
}
