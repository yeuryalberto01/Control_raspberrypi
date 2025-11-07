import { ReactNode, useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import { http, clearToken, getActiveDevice, setActiveDevice, subscribeActiveDevice } from "@/lib/api";

type Device = {
  id: string;
  name: string;
  role?: string;
};

interface LayoutProps {
  children: ReactNode;
  onLogout: () => void;
}

export default function Layout({ children, onLogout }: LayoutProps) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [activeDevice, setActive] = useState<string>(getActiveDevice());

  useEffect(() => {
    const load = async () => {
      setLoadingDevices(true);
      try {
        const { data } = await http.get<Device[]>("/api/devices");
        setDevices(data || []);
      } catch {
        // ignore
      } finally {
        setLoadingDevices(false);
      }
    };
    void load();
    const handler = () => void load();
    window.addEventListener("pi-devices-refresh", handler);
    return () => window.removeEventListener("pi-devices-refresh", handler);
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeActiveDevice(() => setActive(getActiveDevice()));
    return () => unsubscribe();
  }, []);

  const handleDeviceChange = (value: string) => {
    setActive(value);
    setActiveDevice(value);
  };

  const handleLogout = () => {
    clearToken();
    onLogout();
  };

  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-100">
      <Sidebar />
      <main className="flex-1 flex flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-slate-800 bg-slate-900/60 px-6 py-4">
          <div>
            <div className="text-sm text-slate-400">Dispositivo activo</div>
            <select
              className="mt-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={activeDevice}
              onChange={(e) => handleDeviceChange(e.target.value)}
            >
              <option value="local">Esta Raspberry (local)</option>
              {devices.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </select>
            {loadingDevices && <div className="text-xs text-slate-500 mt-1">Cargando dispositivos...</div>}
          </div>
          <button
            onClick={handleLogout}
            className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800"
          >
            Cerrar sesion
          </button>
        </header>
        <section className="flex-1 overflow-y-auto p-6">{children}</section>
      </main>
    </div>
  );
}
