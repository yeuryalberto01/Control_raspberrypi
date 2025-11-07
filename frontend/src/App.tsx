import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Services from "@/pages/Services";
import Logs from "@/pages/Logs";
import Deploy from "@/pages/Deploy";
import Devices from "@/pages/Devices";
import Settings from "@/pages/Settings";
import Terminal from "@/pages/Terminal";
import { getToken } from "@/lib/api";

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);

  // Temporarily bypass authentication
  // const [isAuthenticated, setIsAuthenticated] = useState<boolean>(Boolean(getToken()));
  // useEffect(() => {
  //   setIsAuthenticated(Boolean(getToken()));
  // }, []);

  // if (!isAuthenticated) {
  //   return <Login onOk={() => setIsAuthenticated(true)} />;
  // }

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout onLogout={() => setIsAuthenticated(false)}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/services" element={<Services />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/deploy" element={<Deploy />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/terminal" element={<Terminal />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
