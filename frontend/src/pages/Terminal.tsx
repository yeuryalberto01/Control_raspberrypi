import { useEffect, useRef } from "react";
import { Terminal as XtermTerminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";

import { openWs } from "@/lib/ws";
import { useActiveDevice } from "@/lib/hooks";
import { getRole, getToken } from "@/lib/api";

export default function Terminal() {
  const termRef = useRef<HTMLDivElement | null>(null);
  const { activeDeviceId, isLocal } = useActiveDevice();

  useEffect(() => {
    if (!termRef.current) {
      return;
    }

    const term = new XtermTerminal({
      cursorBlink: true,
      fontFamily: 'Consolas, "Courier New", monospace',
      fontSize: 14,
      theme: {
        background: "#0f172a", // slate-900
        foreground: "#f8fafc", // slate-50
        cursor: "#f8fafc",
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());

    term.open(termRef.current);
    fitAddon.fit();

    const handleResize = () => fitAddon.fit();
    window.addEventListener("resize", handleResize);

    const cleanup = () => {
      window.removeEventListener("resize", handleResize);
      term.dispose();
    };

    const role = getRole();
    if (role !== "admin") {
      term.writeln("Solo los administradores pueden usar el terminal.");
      return cleanup;
    }

    const token = getToken();
    if (!token) {
      term.writeln("Sesión no válida. Inicia sesión para continuar.");
      return cleanup;
    }

    if (!isLocal) {
      term.writeln("SSH Terminal is only available for the local device.");
      return cleanup;
    }

    term.writeln("Connecting to SSH...");

    const targetDevice = encodeURIComponent(activeDeviceId || "local");
    const ws = openWs(`/ssh/${targetDevice}/ws`);

    ws.onopen = () => {
      term.writeln("\x1b[32mConnection established.\x1b[0m");
      fitAddon.fit(); // Adjust size after connection message
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onerror = () => {
      term.writeln("\r\n\x1b[31mConnection error.\x1b[0m");
    };

    ws.onclose = () => {
      term.writeln("\r\n\x1b[31mConnection closed.\x1b[0m");
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    return () => {
      ws.close();
      cleanup();
    };
  }, [activeDeviceId, isLocal]);

  return <div ref={termRef} className="h-full w-full" />;
}
