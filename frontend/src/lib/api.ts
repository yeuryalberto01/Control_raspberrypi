import axios from "axios";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

const stripTrailingSlashes = (value: string) => value.replace(/\/+$/, "");

const resolveEnvBase = (): string | undefined => {
  const raw = import.meta.env.VITE_API_BASE as string | undefined;
  if (!raw) {
    return undefined;
  }
  let normalized = stripTrailingSlashes(raw);
  if (typeof window === "undefined") {
    return normalized;
  }
  try {
    const url = new URL(normalized);
    if (LOCAL_HOSTS.has(url.hostname) && !LOCAL_HOSTS.has(window.location.hostname)) {
      url.hostname = window.location.hostname;
      if (!url.port) {
        const port = (import.meta.env.VITE_API_PORT as string | undefined) || "8000";
        if (port) {
          url.port = port;
        }
      }
      normalized = stripTrailingSlashes(url.toString());
    }
    return normalized;
  } catch {
    return normalized;
  }
};

const fallbackBase = (() => {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }
  const { protocol, hostname } = window.location;
  const port = (import.meta.env.VITE_API_PORT as string | undefined) || "8000";
  return stripTrailingSlashes(`${protocol}//${hostname}${port ? `:${port}` : ""}`);
})();

const API = resolveEnvBase() || fallbackBase;

let TOKEN = "";
let USER_ROLE = localStorage.getItem("pi_role") || "";
let ACTIVE_DEVICE = localStorage.getItem("pi_active_device") || "local";
const DEVICE_SUBSCRIBERS = new Set<() => void>();

export const setToken = (token: string, role?: string) => {
  TOKEN = token;
  localStorage.setItem("pi_token", token);
  if (typeof role === "string") {
    USER_ROLE = role;
    localStorage.setItem("pi_role", role);
  }
};

export const getToken = (): string => {
  if (TOKEN) {
    return TOKEN;
  }
  const stored = localStorage.getItem("pi_token") || "";
  TOKEN = stored;
  return TOKEN;
};

export const getRole = (): string => {
  if (USER_ROLE) {
    return USER_ROLE;
  }
  const stored = localStorage.getItem("pi_role") || "";
  USER_ROLE = stored;
  return USER_ROLE;
};

export const clearToken = () => {
  TOKEN = "";
  USER_ROLE = "";
  localStorage.removeItem("pi_token");
  localStorage.removeItem("pi_role");
};

export const setActiveDevice = (deviceId: string) => {
  ACTIVE_DEVICE = deviceId;
  localStorage.setItem("pi_active_device", deviceId);
  DEVICE_SUBSCRIBERS.forEach((fn) => {
    try {
      fn();
    } catch {
      // ignore subscriber errors
    }
  });
};

export const getActiveDevice = (): string => ACTIVE_DEVICE;

export const subscribeActiveDevice = (listener: () => void) => {
  DEVICE_SUBSCRIBERS.add(listener);
  return () => DEVICE_SUBSCRIBERS.delete(listener);
};

export const http = axios.create({
  baseURL: API
});

http.interceptors.request.use((config) => {
  config.headers = config.headers || {};
  const token = getToken();
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

export const apiBase = API;

export type AIAnalysis = {
  explanation: string;
  command: string | null;
};

export async function analyzeLogs(logs: string): Promise<AIAnalysis> {
  const { data } = await http.post<AIAnalysis>("/api/ai/analyze-logs", { logs });
  return data;
}
