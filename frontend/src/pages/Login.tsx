import { FormEvent, useState } from "react";
import { http, setToken } from "@/lib/api";

interface LoginProps {
  onOk: () => void;
}

export default function Login({ onOk }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await http.post("/auth/login", {
        username,
        password
      });
      setToken(data.token);
      onOk();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Error desconocido";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-slate-950 text-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-80 space-y-4 rounded-2xl border border-slate-800 bg-slate-900/70 px-6 py-8 shadow-xl"
      >
        <div className="text-xl font-semibold">Iniciar sesion</div>
        <input
          className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 outline-none focus:border-indigo-500"
          placeholder="Usuario"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 outline-none focus:border-indigo-500"
          placeholder="Contrasena"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error ? <div className="text-sm text-rose-400">{error}</div> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-indigo-600 px-3 py-2 font-medium hover:bg-indigo-500 disabled:opacity-60"
        >
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
