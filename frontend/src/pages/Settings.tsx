import { http } from "@/lib/api";
import { confirmAction } from "@/components/ConfirmDialog";

export default function Settings() {
  const handleBackup = async () => {
    const { data } = await http.get("/backup/download", { responseType: "blob" });
    const url = window.URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pi_backup.tar.gz";
    link.click();
    window.URL.revokeObjectURL(url);
  };

  const handleReboot = async () => {
    const ok = await confirmAction("Esto reiniciara la Raspberry. Trabajo en curso se detendra.");
    if (!ok) {
      return;
    }
    await http.post("/system/reboot", {}, { headers: { "X-Confirm": "REBOOT" } });
    alert("Orden de reinicio enviada.");
  };

  const handlePoweroff = async () => {
    const ok = await confirmAction("Esto apagara la Raspberry. Deberas encenderla manualmente.");
    if (!ok) {
      return;
    }
    await http.post("/system/poweroff", {}, { headers: { "X-Confirm": "POWEROFF" } });
    alert("Orden de apagado enviada.");
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Ajustes</h2>
      <div className="flex flex-wrap gap-3">
        <button
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500"
          onClick={handleBackup}
        >
          Descargar backup
        </button>
        <button
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium hover:bg-amber-500"
          onClick={handleReboot}
        >
          Reiniciar
        </button>
        <button
          className="rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium hover:bg-rose-600"
          onClick={handlePoweroff}
        >
          Apagar
        </button>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
        Asegurate de proteger el backend con JWT, restringir CORS y mantener las listas blancas actualizadas. Recuerda
        que las acciones criticas requieren confirmacion manual.
      </div>
    </div>
  );
}
