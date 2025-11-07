import { FormEvent, useState } from "react";
import { http } from "@/lib/api";
import { useActiveDevice } from "@/lib/hooks";

export default function Deploy() {
  const { isLocal } = useActiveDevice();
  const [targetDir, setTargetDir] = useState("/home/pi/tuapp");
  const [branch, setBranch] = useState("");
  const [message, setMessage] = useState<string>("");
  const [uploading, setUploading] = useState(false);

  if (!isLocal) {
    return (
      <div className="rounded-xl border border-amber-600/60 bg-amber-900/20 p-6 text-sm text-amber-200">
        El despliegue solo esta disponible para el dispositivo local.
      </div>
    );
  }

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fileInput = event.currentTarget.elements.namedItem("package") as HTMLInputElement | null;
    if (!fileInput?.files?.length) {
      setMessage("Selecciona un archivo ZIP/TAR primero.");
      return;
    }
    setUploading(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", fileInput.files[0]);
      const { data } = await http.post(`/deploy/archive?target_dir=${encodeURIComponent(targetDir)}`, form, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setMessage(`Despliegue completado en ${data.target || targetDir}.`);
      event.currentTarget.reset();
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || "Error subiendo el paquete.");
    } finally {
      setUploading(false);
    }
  };

  const handleGit = async () => {
    setUploading(true);
    setMessage("");
    try {
      const { data } = await http.post("/deploy/git", {
        target_dir: targetDir,
        branch: branch || undefined
      });
      setMessage(data.stdout || "Git pull completado.");
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || "Error ejecutando git pull.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Deploy ZIP/TAR</h2>
        <form onSubmit={handleUpload} className="mt-4 space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <label className="block text-sm text-slate-300">
            Directorio destino
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              value={targetDir}
              onChange={(e) => setTargetDir(e.target.value)}
              required
            />
          </label>
          <input
            type="file"
            name="package"
            accept=".zip,.tar,.tar.gz,.tgz"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={uploading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
          >
            {uploading ? "Subiendo..." : "Subir y desplegar"}
          </button>
        </form>
      </div>

      <div>
        <h2 className="text-xl font-semibold">Git pull</h2>
        <div className="mt-4 space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <label className="block text-sm text-slate-300">
            Rama (opcional)
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              placeholder="main"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
          </label>
          <button
            onClick={handleGit}
            disabled={uploading}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-60"
          >
            {uploading ? "Ejecutando..." : "Ejecutar git pull"}
          </button>
        </div>
      </div>

      {message && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-200">{message}</div>
      )}
    </div>
  );
}
