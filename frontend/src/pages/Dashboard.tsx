import { useCallback, useEffect, useMemo, useState } from "react";
import { http } from "@/lib/api";
import { useActiveDevice } from "@/lib/hooks";
import StatCard from "@/components/StatCard";
import { openWs } from "@/lib/ws";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type ProcessMetric = {
  pid: number;
  name: string;
  cpu_percent: number;
  mem_percent: number;
};

type Metrics = {
  cpu_percent?: number;
  cpu_cores?: number;
  cpu_per_core?: number[];
  mem_percent?: number;
  mem_used_mb?: number;
  mem_total_mb?: number;
  mem_available_mb?: number;
  swap_total_mb?: number;
  swap_used_mb?: number;
  disk_percent?: number;
  disk_used_gb?: number;
  disk_total_gb?: number;
  net_rx_kbps?: number;
  net_tx_kbps?: number;
  process_count?: number;
  top_cpu?: ProcessMetric[];
  top_mem?: ProcessMetric[];
  temp_c?: number | null;
  load1?: number;
  load5?: number;
  load15?: number;
  uptime_seconds?: number;
};

type HistoryPoint = { t: number; v: number };

const HISTORY_LENGTH = 180;

const CARD_COLORS = {
  cpu: "bg-gradient-to-br from-indigo-600/20 via-indigo-800/30 to-slate-950",
  ram: "bg-gradient-to-br from-emerald-600/20 via-emerald-800/30 to-slate-950",
  disk: "bg-gradient-to-br from-amber-600/20 via-amber-800/30 to-slate-950",
  temp: "bg-gradient-to-br from-rose-500/20 via-rose-700/30 to-slate-950",
  swap: "bg-gradient-to-br from-purple-600/20 via-purple-800/30 to-slate-950",
  proc: "bg-gradient-to-br from-cyan-600/20 via-cyan-800/30 to-slate-950",
  net: "bg-gradient-to-br from-sky-600/20 via-sky-800/30 to-slate-950",
  avail: "bg-gradient-to-br from-lime-500/20 via-lime-700/30 to-slate-950",
};

type DetailMetric = "cpu" | "ram" | "disk" | "net";

const appendPoint = (points: HistoryPoint[], point: HistoryPoint) => [...points.slice(-HISTORY_LENGTH + 1), point];

const MetricHistoryCard = ({
  title,
  datasets,
  unit,
  domain,
}: {
  title: string;
  unit: string;
  datasets: { key: string; label: string; color: string; data: HistoryPoint[] }[];
  domain?: [number, number];
}) => {
  if (!datasets.length || !datasets[0].data.length) {
    return null;
  }
  const length = datasets[0].data.length;
  const chartData = datasets[0].data.map((point, idx) => {
    const row: Record<string, number | string> = { t: point.t };
    datasets.forEach(({ key, data }) => {
      row[key] = data[idx]?.v ?? data[data.length - 1]?.v ?? 0;
    });
    return row;
  });

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-2 text-sm text-slate-400">{title}</div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <XAxis dataKey="t" hide />
            <YAxis domain={domain} hide />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
              labelFormatter={(ts) => new Date(ts as number).toLocaleTimeString()}
              formatter={(value: number, name) => [`${value.toFixed(1)} ${unit}`, name]}
            />
            {datasets.map(({ key, color }) => (
              <Line key={key} type="monotone" dataKey={key} stroke={color} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const DetailPanel = ({ metric, metrics }: { metric: DetailMetric; metrics: Metrics }) => {
  if (metric === "cpu") {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="text-sm text-slate-400">Resumen</div>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <div>
              <div className="text-xs text-slate-500">Uso actual</div>
              <div className="text-2xl font-semibold text-slate-100">{metrics.cpu_percent?.toFixed(1) ?? "0"}%</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">N&uacute;cleos</div>
              <div className="text-2xl font-semibold text-slate-100">{metrics.cpu_cores ?? "N/A"}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Load avg</div>
              <div className="text-sm text-slate-100">
                {metrics.load1?.toFixed(2) ?? "0"} / {metrics.load5?.toFixed(2) ?? "0"} / {metrics.load15?.toFixed(2) ?? "0"}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Procesos</div>
              <div className="text-2xl font-semibold text-slate-100">{metrics.process_count ?? 0}</div>
            </div>
          </div>
          <div className="mt-4">
            <div className="mb-2 text-xs text-slate-500">Distribuci&oacute;n por n&uacute;cleo</div>
            {metrics.cpu_per_core && metrics.cpu_per_core.length > 0 ? (
              <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
                {metrics.cpu_per_core.map((value, index) => (
                  <div key={index}>
                    <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                      <span>N&uacute;cleo {index + 1}</span>
                      <span className="font-semibold text-slate-100">{value.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-500">Sin datos de n&uacute;cleo</div>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-3 text-sm text-slate-400">Top procesos (CPU)</div>
          {metrics.top_cpu && metrics.top_cpu.length ? (
            <div className="space-y-2">
              {metrics.top_cpu.map((proc) => (
                <div key={`cpu-${proc.pid}`} className="flex items-center justify-between rounded-lg border border-slate-800/50 bg-slate-900/40 px-3 py-2 text-sm">
                  <div>
                    <div className="font-semibold text-slate-100">{proc.name}</div>
                    <div className="text-xs text-slate-500">PID {proc.pid}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-base font-semibold text-slate-100">{proc.cpu_percent.toFixed(1)}%</div>
                    <div className="text-xs text-slate-500">CPU</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-500">Sin datos de procesos</div>
          )}
        </div>
      </div>
    );
  }

  if (metric === "ram") {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="text-sm text-slate-400">Resumen</div>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="text-xs text-slate-500">Uso</div>
            <div className="text-2xl font-semibold text-slate-100">{metrics.mem_percent?.toFixed(1) ?? "0"}%</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Libre</div>
            <div className="text-2xl font-semibold text-slate-100">{metrics.mem_available_mb ?? 0} MB</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Swap usado</div>
            <div className="text-lg font-semibold text-slate-100">
              {metrics.swap_used_mb ?? 0} / {metrics.swap_total_mb ?? 0} MB
            </div>
          </div>
        </div>
        <div className="mt-4 mb-3 text-sm text-slate-400">Top procesos (RAM)</div>
        {metrics.top_mem && metrics.top_mem.length ? (
          <div className="space-y-2">
            {metrics.top_mem.map((proc) => (
              <div key={`mem-${proc.pid}`} className="flex items-center justify-between rounded-lg border border-slate-800/50 bg-slate-900/40 px-3 py-2 text-sm">
                <div>
                  <div className="font-semibold text-slate-100">{proc.name}</div>
                  <div className="text-xs text-slate-500">PID {proc.pid}</div>
                </div>
                <div className="text-right">
                  <div className="text-base font-semibold text-slate-100">{proc.mem_percent.toFixed(1)}%</div>
                  <div className="text-xs text-slate-500">RAM</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-500">Sin datos de procesos</div>
        )}
      </div>
    );
  }

  if (metric === "disk") {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-2 text-sm text-slate-400">Detalle de almacenamiento</div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs text-slate-500">Total</div>
            <div className="text-xl font-semibold text-slate-100">{metrics.disk_total_gb?.toFixed(2) ?? "0"} GB</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">En uso</div>
            <div className="text-xl font-semibold text-slate-100">{metrics.disk_used_gb?.toFixed(2) ?? "0"} GB</div>
          </div>
        </div>
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
            <span>Porcentaje utilizado</span>
            <span className="font-semibold text-slate-100">{metrics.disk_percent?.toFixed(1) ?? "0"}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-amber-500"
              style={{ width: `${Math.min(100, Math.max(0, metrics.disk_percent ?? 0))}%` }}
            />
          </div>
        </div>
      </div>
    );
  }

  // net
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 text-sm text-slate-400">Detalle de red</div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-xs text-slate-500">RX actual</div>
          <div className="text-xl font-semibold text-slate-100">{(metrics.net_rx_kbps ?? 0).toFixed(1)} KB/s</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">TX actual</div>
          <div className="text-xl font-semibold text-slate-100">{(metrics.net_tx_kbps ?? 0).toFixed(1)} KB/s</div>
        </div>
      </div>
      <div className="mt-3 text-xs text-slate-500">Usa la tarjeta de historial para visualizar tendencias.</div>
    </div>
  );
};

export default function Dashboard() {
  const { activeDeviceId, isLocal } = useActiveDevice();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [detailMetric, setDetailMetric] = useState<DetailMetric>("cpu");
  const [history, setHistory] = useState<{
    cpu: HistoryPoint[];
    ram: HistoryPoint[];
    disk: HistoryPoint[];
    netRx: HistoryPoint[];
    netTx: HistoryPoint[];
  }>({ cpu: [], ram: [], disk: [], netRx: [], netTx: [] });

  const recordHistory = useCallback((incoming: Metrics) => {
    const timestamp = Date.now();
    setHistory((prev) => ({
      cpu: appendPoint(prev.cpu, { t: timestamp, v: incoming.cpu_percent ?? 0 }),
      ram: appendPoint(prev.ram, { t: timestamp, v: incoming.mem_percent ?? 0 }),
      disk: appendPoint(prev.disk, { t: timestamp, v: incoming.disk_percent ?? 0 }),
      netRx: appendPoint(prev.netRx, { t: timestamp, v: incoming.net_rx_kbps ?? 0 }),
      netTx: appendPoint(prev.netTx, { t: timestamp, v: incoming.net_tx_kbps ?? 0 }),
    }));
  }, []);

  useEffect(() => {
    let cancelled = false;

    const endpoint = isLocal ? "/metrics" : activeDeviceId ? `/api/devices/${activeDeviceId}/metrics` : null;
    if (!endpoint) {
      setMetrics(null);
      return () => {
        cancelled = true;
      };
    }

    const handleData = (incoming: Metrics) => {
      if (!cancelled) {
        setMetrics(incoming);
        recordHistory(incoming);
      }
    };

    const fetchMetrics = async () => {
      try {
        const { data } = await http.get<Metrics>(endpoint);
        handleData(data);
      } catch {
        if (!cancelled) {
          setMetrics(null);
        }
      }
    };

    fetchMetrics().catch(() => undefined);

    if (isLocal) {
      const ws = openWs("/metrics/ws");
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Metrics;
          handleData(data);
        } catch {
          // ignore
        }
      };
      ws.onerror = () => ws.close();
      return () => {
        cancelled = true;
        ws.close();
      };
    }

    const interval = setInterval(fetchMetrics, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeDeviceId, isLocal, recordHistory]);

  const historyConfig = useMemo(() => {
    switch (detailMetric) {
      case "cpu":
        return {
          title: "CPU en tiempo real",
          datasets: [{ key: "cpu", label: "CPU", color: "#6366f1", data: history.cpu }],
          unit: "%",
          domain: [0, 100] as [number, number],
        };
      case "ram":
        return {
          title: "Memoria en tiempo real",
          datasets: [{ key: "ram", label: "RAM", color: "#22c55e", data: history.ram }],
          unit: "%",
          domain: [0, 100] as [number, number],
        };
      case "disk":
        return {
          title: "Disco en tiempo real",
          datasets: [{ key: "disk", label: "Disco", color: "#f97316", data: history.disk }],
          unit: "%",
          domain: [0, 100] as [number, number],
        };
      case "net":
        return {
          title: "Red en tiempo real",
          datasets: [
            { key: "rx", label: "RX", color: "#38bdf8", data: history.netRx },
            { key: "tx", label: "TX", color: "#0ea5e9", data: history.netTx },
          ],
          unit: "KB/s",
        };
      default:
        return null;
    }
  }, [detailMetric, history]);

  if (!metrics) {
    return <div>Cargando m&eacute;tricas...</div>;
  }

  const value = <T extends number | undefined>(input: T, fallback = 0): number =>
    typeof input === "number" && Number.isFinite(input) ? input : fallback;

  const cpuPercent = value(metrics.cpu_percent);
  const memPercent = value(metrics.mem_percent);
  const memUsed = value(metrics.mem_used_mb);
  const memTotal = value(metrics.mem_total_mb);
  const memAvailable = value(metrics.mem_available_mb);
  const diskPercent = value(metrics.disk_percent);
  const diskUsed = value(metrics.disk_used_gb);
  const diskTotal = value(metrics.disk_total_gb);
  const swapTotal = value(metrics.swap_total_mb);
  const swapUsed = value(metrics.swap_used_mb);
  const uptimeSeconds = value(metrics.uptime_seconds);
  const load1 = value(metrics.load1);
  const load5 = value(metrics.load5);
  const load15 = value(metrics.load15);
  const netRx = value(metrics.net_rx_kbps);
  const netTx = value(metrics.net_tx_kbps);
  const processCount = value(metrics.process_count);
  const cpuCores = value(metrics.cpu_cores);

  const selectMetric = (metric: DetailMetric) => {
    setDetailMetric(metric);
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="CPU"
          value={`${cpuPercent.toFixed(1)}%`}
          hint={`Loads: ${load1.toFixed(2)} / ${load5.toFixed(2)} / ${load15.toFixed(2)}`}
          status={cpuPercent >= 85 ? "alert" : cpuPercent >= 65 ? "warn" : "default"}
          color={CARD_COLORS.cpu}
          onClick={() => selectMetric("cpu")}
          onDoubleClick={() => selectMetric("cpu")}
        />
        <StatCard
          title="RAM"
          value={`${memPercent.toFixed(1)}%`}
          hint={`${memUsed} / ${memTotal} MB (Libre: ${memAvailable} MB)`}
          status={memPercent >= 85 ? "alert" : memPercent >= 70 ? "warn" : "default"}
          color={CARD_COLORS.ram}
          onClick={() => selectMetric("ram")}
          onDoubleClick={() => selectMetric("ram")}
        />
        <StatCard
          title="Disco /"
          value={`${diskPercent.toFixed(1)}%`}
          hint={`${diskUsed} / ${diskTotal} GB`}
          status={diskPercent >= 90 ? "alert" : diskPercent >= 75 ? "warn" : "default"}
          color={CARD_COLORS.disk}
          onClick={() => selectMetric("disk")}
          onDoubleClick={() => selectMetric("disk")}
        />
        <StatCard
          title="Temperatura"
          value={metrics.temp_c != null ? `${metrics.temp_c.toFixed(1)}°C` : "N/A"}
          hint={`${Math.floor(uptimeSeconds / 3600)}h de uptime`}
          color={CARD_COLORS.temp}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Swap"
          value={`${swapUsed} / ${swapTotal} MB`}
          hint="Memoria virtual en uso"
          status={swapTotal === 0 ? "default" : swapUsed / Math.max(1, swapTotal) >= 0.6 ? "alert" : swapUsed / Math.max(1, swapTotal) >= 0.35 ? "warn" : "default"}
          color={CARD_COLORS.swap}
          onClick={() => selectMetric("ram")}
          onDoubleClick={() => selectMetric("ram")}
        />
        <StatCard
          title="Procesos"
          value={`${processCount}`}
          hint={`${cpuCores} nucleos logicos`}
          color={CARD_COLORS.proc}
          onClick={() => selectMetric("cpu")}
          onDoubleClick={() => selectMetric("cpu")}
        />
        <StatCard
          title="Red RX/TX"
          value={`${netRx.toFixed(1)} / ${netTx.toFixed(1)} KB/s`}
          hint="Tr&aacute;fico agregado (excluye loopback)"
          color={CARD_COLORS.net}
          onClick={() => selectMetric("net")}
          onDoubleClick={() => selectMetric("net")}
        />
        <StatCard
          title="Disponibilidad"
          value={`${memAvailable} MB`}
          hint="Memoria libre estimada"
          color={CARD_COLORS.avail}
          onClick={() => selectMetric("ram")}
          onDoubleClick={() => selectMetric("ram")}
        />
      </div>

      {historyConfig && (
        <MetricHistoryCard
          title={`${historyConfig.title} (haz clic en una tarjeta para cambiar)`}
          datasets={historyConfig.datasets}
          unit={historyConfig.unit}
          domain={historyConfig.domain}
        />
      )}

      <DetailPanel metric={detailMetric} metrics={metrics} />
    </div>
  );
}
