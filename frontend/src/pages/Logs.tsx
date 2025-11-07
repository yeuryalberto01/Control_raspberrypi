import { useEffect, useRef, useState } from "react";
import { http, analyzeLogs, AIAnalysis } from "@/lib/api";
import { useActiveDevice } from "@/lib/hooks";
import { openWs } from "@/lib/ws";
import LogAnalyzer from "@/components/LogAnalyzer";
import { Sparkles } from "lucide-react";

export default function Logs() {
  const { isLocal } = useActiveDevice();
  const [unit, setUnit] = useState<string>("pi-admin.service");
  const [units, setUnits] = useState<string[]>([]);
  const [logBuffer, setLogBuffer] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AIAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUnits = async () => {
      try {
        const { data } = await http.get<string[]>("/service");
        setUnits(data);
        if (!data.includes(unit) && data.length) {
          setUnit(data[0]);
        }
      } catch {
        // ignore
      }
    };
    fetchUnits();
  }, []);

  useEffect(() => {
    if (!unit) {
      return;
    }
    let cleanup = () => {};
    if (isLocal) {
      const ws = openWs(`/logs/ws?unit=${encodeURIComponent(unit)}`);
      ws.onmessage = (event) => {
        setLogBuffer((prev) => {
          const next = `${prev}${event.data}`;
          if (textareaRef.current) {
            textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
          }
          return next;
        });
      };
      cleanup = () => ws.close();
    } else {
      // Remote logs not implemented yet - show placeholder
      setLogBuffer("Remote logs functionality not yet implemented. Please select 'Local' to view system logs.");
      cleanup = () => {};
    }
    return cleanup;
  }, [unit, isLocal]);

  const download = async () => {
    if (isLocal) {
      const url = `/logs/download?unit=${encodeURIComponent(unit)}&lines=1000`;
      const { data } = await http.get(url, { responseType: "blob" });
      const blobUrl = window.URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `${unit.replace(/[\\/]/g, "_")}.log`;
      link.click();
      window.URL.revokeObjectURL(blobUrl);
    } else {
      // Remote download not implemented yet
      alert("Remote log download not yet implemented. Please select 'Local' to download logs.");
    }
  };

  const handleAnalyze = async () => {
    if (!logBuffer) return;
    setIsAnalyzing(true);
    setAnalysisResult(null);
    setAnalysisError(null);
    try {
      // Send the last 200 lines for analysis
      const logsToAnalyze = logBuffer.split("\n").slice(-200).join("\n");
      const result = await analyzeLogs(logsToAnalyze);
      setAnalysisResult(result);
    } catch (err: any) {
      setAnalysisError(err?.response?.data?.detail || err.message || "An unknown error occurred.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div className="text-sm text-slate-400">Unidad systemd</div>
          <select
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="mt-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
          >
            {units.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
            {!units.includes(unit) && <option value={unit}>{unit}</option>}
          </select>
        </div>
        <button
          onClick={download}
          className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800"
        >
          Descargar
        </button>
        <button
          onClick={handleAnalyze}
          disabled={isAnalyzing || !logBuffer}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
        >
          <Sparkles size={16} />
          {isAnalyzing ? "Analizando..." : "Analizar con IA"}
        </button>
        {!isLocal && (
          <div className="text-xs text-amber-300">
            El streaming en vivo solo esta disponible para el dispositivo local; se muestra refresco periodico.
          </div>
        )}
      </div>

      {analysisError && (
        <div className="rounded-xl border border-rose-500/50 bg-rose-900/20 p-3 text-sm text-rose-200">
          <strong>Error de Análisis:</strong> {analysisError}
        </div>
      )}

      {analysisResult && <LogAnalyzer analysis={analysisResult} onClose={() => setAnalysisResult(null)} />}

      <textarea
        ref={textareaRef}
        value={logBuffer}
        readOnly
        className="h-[480px] w-full resize-none rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-200"
      />
    </div>
  );
}
