import { useState, useEffect, useCallback } from "react";
import { http, subscribeActiveDevice, getActiveDevice } from "./api";
import { Device } from "@/pages/Devices";

type ActiveDeviceState = {
  activeDeviceId: string;
  isLocal: boolean;
};

export function useActiveDevice(): ActiveDeviceState {
  const [activeDeviceId, setActiveDeviceId] = useState(getActiveDevice() || "local");

  useEffect(() => {
    const unsub = subscribeActiveDevice(() => {
      setActiveDeviceId(getActiveDevice() || "local");
    });
    return () => unsub();
  }, []);

  return {
    activeDeviceId,
    isLocal: !activeDeviceId || activeDeviceId === "local",
  };
}

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadDevices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await http.get<Device[]>("/api/devices");
      setDevices(data || []);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Failed to load devices.";
      setError(msg);
      setDevices([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  return { devices, loading, error, loadDevices };
}
