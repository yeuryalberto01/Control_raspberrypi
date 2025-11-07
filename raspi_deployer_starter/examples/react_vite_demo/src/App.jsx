import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const METHOD_OPTIONS = [
  {
    value: "ssh",
    label: "Exploración SSH inteligente",
    description: "Identifica Raspberry Pi leyendo el banner del puerto 22 y resolviendo DNS inverso."
  },
  {
    value: "ping",
    label: "Ping (ICMP)",
    description: "Descubre hosts activos respondiendo a paquetes ICMP."
  },
  {
    value: "arp",
    label: "Tabla ARP + prefijos MAC",
    description: "Detecta dispositivos comparando los prefijos MAC conocidos de Raspberry Pi."
  }
];

function formatTimestamp(date = new Date()) {
  return date.toLocaleTimeString("es-ES", { hour12: false });
}

function parseHosts(raw) {
  if (!raw) {
    return [];
  }
  return raw
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function StatusBadge({ label, tone }) {
  return <span className={`badge badge-${tone}`}>{label}</span>;
}

export default function App() {
  const [localNetworks, setLocalNetworks] = useState([]);
  const [form, setForm] = useState({
    scan_method: "ssh",
    network: "",
    hosts: "",
    timeout: 1.5,
    max_concurrency: 100,
    include_reverse_dns: true
  });

  const [discovering, setDiscovering] = useState(false);
  const [logs, setLogs] = useState([]);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);
  const [credentials, setCredentials] = useState({ user: "pi", password: "" });
  const [deviceDetails, setDeviceDetails] = useState({});

  const controllerRef = useRef(null);
  const logContainerRef = useRef(null);

  useEffect(() => {
    fetchLocalNetworks();
    return () => {
      if (controllerRef.current) {
        controllerRef.current.abort();
      }
    };
  }, []);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const fetchLocalNetworks = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/local-networks`);
      if (!response.ok) {
        throw new Error("No se pudieron obtener las redes locales");
      }
      const data = await response.json();
      setLocalNetworks(data);
      if (!form.network && data.length) {
        setForm((prev) => ({ ...prev, network: data[0] }));
      }
    } catch (err) {
      appendLog(`Advertencia: ${err.message}`, "warning");
    }
  };

  const appendLog = useCallback((message, level = "info") => {
    setLogs((prev) => {
      const next = [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          timestamp: formatTimestamp(),
          level,
          message
        }
      ];
      return next.slice(-200); // mantener las últimas 200 entradas
    });
  }, []);

  const handleFieldChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const stopDiscovery = useCallback(
    (reason = "Escaneo cancelado por el usuario") => {
      if (controllerRef.current) {
        controllerRef.current.abort();
        controllerRef.current = null;
      }
      setDiscovering(false);
      appendLog(reason, "warning");
    },
    [appendLog]
  );

  const handleDiscoveryEvent = useCallback(
    (eventType, payload) => {
      if (eventType === "log") {
        if (payload?.message) {
          appendLog(payload.message, payload.level ?? "info");
        } else if (typeof payload === "string") {
          appendLog(payload, "info");
        }
        return;
      }

      if (eventType === "result") {
        setResults((prev) => {
          const index = prev.findIndex((item) => item.ip === payload.ip);
          const updatedItem = {
            ...prev[index],
            ...payload,
            lastSeen: new Date().toISOString()
          };

          if (index >= 0) {
            const cloned = [...prev];
            cloned[index] = updatedItem;
            return cloned;
          }

          return [...prev, updatedItem];
        });

        if (payload.status === "active") {
          appendLog(`Host activo ${payload.ip} (${payload.method.toUpperCase()})`, "info");
        } else {
          appendLog(`Host inactivo ${payload.ip}`, "warning");
        }
        return;
      }

      // Eventos genéricos
      if (typeof payload === "string") {
        appendLog(payload, "info");
      }
    },
    [appendLog]
  );

  const startDiscovery = useCallback(async () => {
    if (!form.network && !form.hosts.trim()) {
      setError("Define una red CIDR o una lista de hosts a analizar.");
      appendLog("Ingresa una red o lista de hosts para comenzar.", "error");
      return;
    }

    if (controllerRef.current) {
      controllerRef.current.abort();
    }

    const payload = {
      scan_method: form.scan_method,
      timeout: Number(form.timeout) || 1.5,
      max_concurrency: Number(form.max_concurrency) || 100,
      include_reverse_dns: form.include_reverse_dns
    };

    const hostsList = parseHosts(form.hosts);
    if (hostsList.length) {
      payload.hosts = hostsList;
    }
    if (form.network) {
      payload.network = form.network;
    }

    const controller = new AbortController();
    controllerRef.current = controller;

    setDiscovering(true);
    setError(null);
    setResults([]);
    setLogs([]);
    appendLog("Iniciando exploración de la red…", "info");

    try {
      const response = await fetch(`${API_BASE_URL}/api/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      if (!response.ok || !response.body) {
        throw new Error("La API no soporta streaming en este momento.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const eventChunk of events) {
          const lines = eventChunk.split("\n");
          let eventType = "message";
          let dataBuffer = "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataBuffer += line.slice(5).trim();
            }
          }

          if (!dataBuffer) continue;

          let payloadObj = dataBuffer;
          try {
            payloadObj = JSON.parse(dataBuffer);
          } catch {
            // mantener string crudo
          }
          handleDiscoveryEvent(eventType, payloadObj);
        }
      }

      if (buffer.trim()) {
        handleDiscoveryEvent("log", buffer.trim());
      }

      appendLog("Exploración finalizada.", "info");
    } catch (err) {
      if (err.name === "AbortError") {
        appendLog("Exploración detenida.", "warning");
      } else {
        setError(err.message);
        appendLog(`Error: ${err.message}`, "error");
      }
    } finally {
      setDiscovering(false);
      controllerRef.current = null;
    }
  }, [form, appendLog, handleDiscoveryEvent]);

  const stats = useMemo(() => {
    const total = results.length;
    const active = results.filter((item) => item.status === "active").length;
    const inactive = results.filter((item) => item.status !== "active").length;
    const raspberry = results.filter((item) => item.is_raspberry_pi).length;
    const sshOpen = results.filter((item) => item.method === "ssh" && item.status === "active").length;

    return {
      total,
      active,
      inactive,
      raspberry,
      sshOpen
    };
  }, [results]);

  const fetchDeviceDetails = async (ip) => {
    if (!credentials.password.trim()) {
      appendLog("Define la contraseña SSH para consultar detalles del dispositivo.", "warning");
      return;
    }

    setDeviceDetails((prev) => ({
      ...prev,
      [ip]: { ...prev[ip], loading: true, error: null }
    }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/device/details/${encodeURIComponent(ip)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user: credentials.user || "pi",
          password: credentials.password
        })
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.detail || "No se pudieron obtener los detalles del dispositivo.");
      }

      const data = await response.json();
      setDeviceDetails((prev) => ({
        ...prev,
        [ip]: { loading: false, data, error: null, timestamp: formatTimestamp() }
      }));
      appendLog(`Detalles actualizados para ${ip}`, "info");
    } catch (err) {
      setDeviceDetails((prev) => ({
        ...prev,
        [ip]: { loading: false, data: null, error: err.message }
      }));
      appendLog(`Error obteniendo detalles de ${ip}: ${err.message}`, "error");
    }
  };

  return (
    <div className="app">
      <header className="top-bar">
        <div>
          <h1>Raspberry Fleet Control</h1>
          <p>Monitorea, descubre y administra tus Raspberry Pi en una sola vista.</p>
        </div>
        <div className="actions">
          {!discovering && (
            <button className="primary" onClick={startDiscovery}>
              Iniciar exploración
            </button>
          )}
          {discovering && (
            <button className="secondary" onClick={() => stopDiscovery()}>
              Detener
            </button>
          )}
        </div>
      </header>

      <div className="layout">
        <section className="panel">
          <h2>Configuración de descubrimiento</h2>
          <div className="form-row">
            <label>
              Método de exploración
              <select
                value={form.scan_method}
                onChange={(event) => handleFieldChange("scan_method", event.target.value)}
                disabled={discovering}
              >
                {METHOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Timeout (s)
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={form.timeout}
                onChange={(event) => handleFieldChange("timeout", event.target.value)}
                disabled={discovering}
              />
            </label>
            <label>
              Concurrencia máx.
              <input
                type="number"
                min="1"
                max="512"
                value={form.max_concurrency}
                onChange={(event) => handleFieldChange("max_concurrency", event.target.value)}
                disabled={discovering}
              />
            </label>
          </div>

          <div className="method-description">
            {METHOD_OPTIONS.find((option) => option.value === form.scan_method)?.description}
          </div>

          <div className="form-row">
            <label>
              Red CIDR
              <select
                value={form.network}
                onChange={(event) => handleFieldChange("network", event.target.value)}
                disabled={discovering}
              >
                <option value="">Selecciona una red o déjala vacía</option>
                {localNetworks.map((network) => (
                  <option key={network} value={network}>
                    {network}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-row">
            <label>
              Hosts específicos (opcional)
              <textarea
                placeholder="192.168.1.10, 192.168.1.11..."
                value={form.hosts}
                onChange={(event) => handleFieldChange("hosts", event.target.value)}
                disabled={discovering}
              />
            </label>
          </div>

          <div className="form-row">
            <label className="toggle">
              <input
                type="checkbox"
                checked={form.include_reverse_dns}
                disabled={discovering}
                onChange={(event) => handleFieldChange("include_reverse_dns", event.target.checked)}
              />
              <span>Resolver DNS inverso (recomendado para identificar hostnames)</span>
            </label>
          </div>

          {error && <div className="error-banner">{error}</div>}
        </section>

        <section className="panel">
          <h2>Estado general</h2>
          <div className="metrics-grid">
            <MetricCard title="Dispositivos detectados" value={stats.total} accent="primary" />
            <MetricCard title="Activos" value={stats.active} accent="success" />
            <MetricCard title="Inactivos" value={stats.inactive} accent="warning" />
            <MetricCard title="Raspberry Pi" value={stats.raspberry} accent="raspberry" />
            <MetricCard title="SSH disponible" value={stats.sshOpen} accent="neutral" />
          </div>

          <div className="credentials-card">
            <label>
              Usuario SSH
              <input
                type="text"
                value={credentials.user}
                onChange={(event) =>
                  setCredentials((prev) => ({ ...prev, user: event.target.value }))
                }
                placeholder="pi"
              />
            </label>
            <label>
              Contraseña SSH
              <input
                type="password"
                value={credentials.password}
                onChange={(event) =>
                  setCredentials((prev) => ({ ...prev, password: event.target.value }))
                }
                placeholder="••••••••"
              />
            </label>
            <button
              className="secondary"
              onClick={() => {
                setCredentials({ user: "pi", password: "" });
                appendLog("Credenciales restauradas a valores por defecto.", "info");
              }}
            >
              Restablecer
            </button>
          </div>
        </section>
      </div>

      <div className="layout">
        <section className="panel logs-panel">
          <div className="panel-header">
            <h2>Registro en tiempo real</h2>
            <button className="secondary" onClick={() => setLogs([])}>
              Limpiar
            </button>
          </div>
          <div className="logs-container" ref={logContainerRef}>
            {logs.length === 0 && <div className="empty-state">Los mensajes aparecerán aquí.</div>}
            {logs.map((entry) => (
              <div key={entry.id} className={`log-entry ${entry.level}`}>
                <span className="log-timestamp">{entry.timestamp}</span>
                <span className="log-message">{entry.message}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Dispositivos descubiertos</h2>
            <span className="hint">
              {discovering ? "Explorando…" : "Actualiza para mantener la información al día."}
            </span>
          </div>
          {results.length === 0 ? (
            <div className="empty-state">
              Lanza un descubrimiento para poblar esta tabla.
            </div>
          ) : (
            <table className="device-table">
              <thead>
                <tr>
                  <th>IP</th>
                  <th>Estado</th>
                  <th>Método</th>
                  <th>Indicadores</th>
                  <th>Detalles</th>
                </tr>
              </thead>
              <tbody>
                {results.map((device) => {
                  const details = deviceDetails[device.ip];
                  return (
                    <>
                      <tr key={device.ip}>
                        <td>
                          <div className="ip-cell">
                            <strong>{device.ip}</strong>
                            <small>{device.hostname || device.details}</small>
                          </div>
                        </td>
                        <td>
                          {device.status === "active" ? (
                            <StatusBadge label="Activo" tone="success" />
                          ) : (
                            <StatusBadge label="Inactivo" tone="warning" />
                          )}
                        </td>
                        <td>
                          <StatusBadge label={device.method.toUpperCase()} tone="neutral" />
                        </td>
                        <td className="indicators">
                          {device.is_raspberry_pi ? (
                            <StatusBadge label="Raspberry Pi" tone="raspberry" />
                          ) : (
                            <StatusBadge label="Dispositivo genérico" tone="neutral" />
                          )}
                          {device.method === "ssh" && device.status === "active" && (
                            <StatusBadge label="SSH abierto" tone="success" />
                          )}
                        </td>
                        <td>
                          <div className="device-actions">
                            <button
                              className="secondary"
                              onClick={() => fetchDeviceDetails(device.ip)}
                            >
                              {details?.loading ? "Consultando…" : "Obtener detalles"}
                            </button>
                          </div>
                        </td>
                      </tr>
                      {details && (
                        <tr className="device-details" key={`${device.ip}-details`}>
                          <td colSpan={5}>
                            {details.loading && (
                              <div className="device-details__content">Consultando información SSH…</div>
                            )}
                            {details.error && (
                              <div className="device-details__content error">
                                Error: {details.error}
                              </div>
                            )}
                            {details.data && (
                              <div className="device-details__content">
                                {details.data.storage && (
                                  <span>
                                    <strong>Almacenamiento</strong>
                                    <em>{details.data.storage.used} usados de {details.data.storage.total}</em>
                                    <em>Libre: {details.data.storage.free} ({details.data.storage.percent}%)</em>
                                  </span>
                                )}
                                {details.data.uptime && (
                                  <span>
                                    <strong>Uptime</strong>
                                    <em>{details.data.uptime}</em>
                                  </span>
                                )}
                                {details.data.temp && (
                                  <span>
                                    <strong>Temperatura</strong>
                                    <em>{details.data.temp}</em>
                                  </span>
                                )}
                                <span>
                                  <strong>Actualizado</strong>
                                  <em>{details.timestamp}</em>
                                </span>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

function MetricCard({ title, value, accent }) {
  return (
    <div className={`metric-card metric-${accent}`}>
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
