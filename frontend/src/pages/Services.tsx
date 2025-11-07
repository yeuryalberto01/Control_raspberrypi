import { useEffect, useState } from "react";
import { http } from "@/lib/api";
import { useActiveDevice } from "@/lib/hooks";
import ServiceRow from "@/components/ServiceRow";

type ServiceStatus = {
  name: string;
  active_state: string;
  sub_state: string;
};

export default function Services() {
  const { isLocal } = useActiveDevice();
  const [services, setServices] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isLocal) {
      setServices([]);
      setStatuses({});
      return;
    }
    void refresh();
  }, [isLocal]);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await http.get<string[]>("/service");
      setServices(data);
      if (data.length) {
        const statusRes = await http.post<ServiceStatus[]>("/service/status", { services: data });
        const map: Record<string, string> = {};
        statusRes.data.forEach((item) => {
          map[item.name] = `${item.active_state}${item.sub_state ? ` / ${item.sub_state}` : ""}`;
        });
        setStatuses(map);
      } else {
        setStatuses({});
      }
    } catch {
      setStatuses({});
    } finally {
      setLoading(false);
    }
  };

  if (!isLocal) {
    return (
      <div className="rounded-xl border border-amber-600/60 bg-amber-900/20 p-6 text-sm text-amber-200">
        La gestion de servicios solo esta disponible cuando el dispositivo activo es el local.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Servicios systemd</h2>
        <button
          onClick={refresh}
          className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800"
          disabled={loading}
        >
          {loading ? "Actualizando..." : "Refrescar"}
        </button>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        {services.length === 0 && !loading ? (
          <div className="text-sm text-slate-400">No hay servicios listados en la whitelist.</div>
        ) : (
          services.map((service) => (
            <ServiceRow
              key={service}
              name={service}
              status={statuses[service] || "desconocido"}
              onChanged={refresh}
            />
          ))
        )}
      </div>
    </div>
  );
}
