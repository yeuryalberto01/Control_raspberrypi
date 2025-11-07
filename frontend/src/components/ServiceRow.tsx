import { http } from "@/lib/api";

interface ServiceRowProps {
  name: string;
  status: string;
  onChanged: () => void;
}

export default function ServiceRow({ name, status, onChanged }: ServiceRowProps) {
  const handleAction = async (action: "start" | "stop" | "restart") => {
    const { data } = await http.post("/service", { name, action });
    const output = data.stdout || data.stderr || "Sin salida";
    alert(`${name} -> ${action}\n${output}`);
    onChanged();
  };

  return (
    <div className="flex items-center justify-between border-b border-slate-800 py-3">
      <div>
        <span className="font-semibold">{name}</span>
        <span className="ml-2 text-sm text-slate-400">{status}</span>
      </div>
      <div className="flex gap-2 text-xs">
        <button
          className="rounded bg-emerald-700 px-3 py-1 hover:bg-emerald-600"
          onClick={() => handleAction("start")}
        >
          Start
        </button>
        <button
          className="rounded bg-amber-700 px-3 py-1 hover:bg-amber-600"
          onClick={() => handleAction("restart")}
        >
          Restart
        </button>
        <button
          className="rounded bg-rose-700 px-3 py-1 hover:bg-rose-600"
          onClick={() => handleAction("stop")}
        >
          Stop
        </button>
      </div>
    </div>
  );
}
