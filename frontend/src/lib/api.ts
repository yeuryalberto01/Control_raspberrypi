import axios from "axios";

const API = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, "") || "http://localhost:8000";

let TOKEN = "";
let ACTIVE_DEVICE = localStorage.getItem("pi_active_device") || "local";
const DEVICE_SUBSCRIBERS = new Set<() => void>();

export const setToken = (token: string) => {
  TOKEN = token;
  localStorage.setItem("pi_token", token);
};

export const getToken = (): string => {
  if (TOKEN) {
    return TOKEN;
  }
  const stored = localStorage.getItem("pi_token") || "";
  TOKEN = stored;
  return TOKEN;
};

export const clearToken = () => {
  TOKEN = "";
  localStorage.removeItem("pi_token");
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
