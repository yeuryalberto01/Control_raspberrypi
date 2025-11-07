import { useState } from "react";
import { X, Sparkles, Clipboard, ClipboardCheck } from "lucide-react";
import { AIAnalysis } from "@/lib/api";

interface LogAnalyzerProps {
  analysis: AIAnalysis;
  onClose: () => void;
}

export default function LogAnalyzer({ analysis, onClose }: LogAnalyzerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!analysis.command) return;
    navigator.clipboard.writeText(analysis.command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="relative mt-4 rounded-xl border border-indigo-500/50 bg-slate-900/70 p-4">
      <button onClick={onClose} className="absolute top-2 right-2 text-slate-500 hover:text-slate-300">
        <X size={18} />
      </button>
      <div className="flex items-center gap-2 text-indigo-400">
        <Sparkles size={18} />
        <h3 className="text-lg font-semibold">Análisis de IA</h3>
      </div>
      <p className="mt-2 text-sm text-slate-300">{analysis.explanation}</p>
      {analysis.command && (
        <div className="mt-3">
          <div className="text-xs font-semibold text-slate-400">Comando sugerido:</div>
          <div className="relative mt-1 flex items-center rounded-lg bg-slate-950 p-2 font-mono text-sm">
            <pre className="flex-1 overflow-x-auto pr-10"><code>{analysis.command}</code></pre>
            <button
              onClick={handleCopy}
              className="absolute top-1/2 right-2 -translate-y-1/2 text-slate-400 hover:text-white"
              title="Copy to clipboard"
            >
              {copied ? <ClipboardCheck size={16} /> : <Clipboard size={16} />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
