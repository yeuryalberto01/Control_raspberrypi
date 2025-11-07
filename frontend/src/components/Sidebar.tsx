import { Link, useLocation } from "react-router-dom";
import { Activity, Server, FileText, Upload, Network, Settings, TerminalSquare } from "lucide-react";
import clsx from "clsx";

const navItems = [
  { to: "/", label: "Dashboard", icon: Activity },
  { to: "/services", label: "Servicios", icon: Server },
  { to: "/logs", label: "Logs", icon: FileText },
  { to: "/deploy", label: "Deploy", icon: Upload },
  { to: "/devices", label: "Dispositivos", icon: Network },
  { to: "/terminal", label: "Terminal", icon: TerminalSquare },
  { to: "/settings", label: "Ajustes", icon: Settings }
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside className="hidden md:flex w-60 flex-shrink-0 flex-col border-r border-slate-800 bg-slate-900/80">
      <div className="px-4 py-5 text-lg font-semibold tracking-wide">Pi Admin</div>
      <nav className="flex flex-col gap-1 px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.to;
          return (
            <Link
              key={item.to}
              to={item.to}
              className={clsx(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                active ? "bg-slate-800 font-semibold" : "hover:bg-slate-800/80 text-slate-300"
              )}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
