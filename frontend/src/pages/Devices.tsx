import { FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { http, setActiveDevice } from "@/lib/api";
import { useActiveDevice, useDevices } from "@/lib/hooks";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Trash2, Edit, Play, CheckCircle } from "lucide-react";

// Updated type to match the new backend schema
export type Device = {
  id: string;
  name: string;
  base_url: string;
  ssh_user: string;
  ssh_pass?: string; // Password is write-only
};

const emptyDevice: Omit<Device, "id"> & { ssh_pass: string } = {
  name: "",
  base_url: "",
  ssh_user: "pi",
  ssh_pass: "",
};

export default function Devices() {
  const { devices, loadDevices, error } = useDevices();
  const [form, setForm] = useState(emptyDevice);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const { activeDeviceId } = useActiveDevice();

  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.name || !form.base_url || !form.ssh_user) {
      toast.error("Completa todos los campos obligatorios.");
      return;
    }

    const payload = {
      ...form,
      // Only send password if it's a new device or password is being changed
      ssh_pass: form.ssh_pass ? form.ssh_pass : undefined,
    };

    try {
      if (editingDevice) {
        // Update existing device
        await http.put(`/api/devices/${editingDevice.id}`, payload);
        toast.success(`Dispositivo "${editingDevice.name}" actualizado.`);
      } else {
        // Create new device
        if (!form.ssh_pass) {
          toast.error("La contraseña es obligatoria para nuevos dispositivos.");
          return;
        }
        await http.post("/api/devices", payload);
        toast.success(`Dispositivo "${form.name}" creado.`);
      }
      // Reset form and state
      setForm(emptyDevice);
      setEditingDevice(null);
      await loadDevices(); // Reload the list
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Error guardando dispositivo.");
    }
  };

  const handleEdit = (device: Device) => {
    setEditingDevice(device);
    setForm({ ...device, ssh_pass: "" }); // Clear password for editing
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleCancelEdit = () => {
    setEditingDevice(null);
    setForm(emptyDevice);
  };

  const handleDelete = async (device: Device) => {
    if (!window.confirm(`¿Seguro que quieres eliminar "${device.name}"?`)) {
      return;
    }
    try {
      await http.delete(`/api/devices/${device.id}`);
      toast.success("Dispositivo eliminado.");
      if (activeDeviceId === device.id) {
        setActiveDevice("local");
      }
      await loadDevices();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "No se pudo eliminar.");
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{editingDevice ? "Editar Dispositivo" : "Añadir Nuevo Dispositivo"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name"
                name="name"
                value={form.name}
                onChange={handleFormChange}
                placeholder="Raspberry Pi Salón"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="base_url">Dirección IP</Label>
              <Input
                id="base_url"
                name="base_url"
                value={form.base_url}
                onChange={handleFormChange}
                placeholder="192.168.1.50"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ssh_user">Usuario SSH</Label>
              <Input
                id="ssh_user"
                name="ssh_user"
                value={form.ssh_user}
                onChange={handleFormChange}
                placeholder="pi"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ssh_pass">Clave SSH</Label>
              <Input
                id="ssh_pass"
                name="ssh_pass"
                type="password"
                value={form.ssh_pass}
                onChange={handleFormChange}
                placeholder={editingDevice ? "Dejar en blanco para no cambiar" : ""}
                required={!editingDevice}
              />
            </div>
            <div className="flex items-end gap-2 md:col-span-2">
              <Button type="submit">{editingDevice ? "Guardar Cambios" : "Añadir Dispositivo"}</Button>
              {editingDevice && (
                <Button type="button" variant="outline" onClick={handleCancelEdit}>
                  Cancelar
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Dispositivos Registrados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {devices.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hay dispositivos registrados.</p>
            ) : (
              devices.map((device) => (
                <div
                  key={device.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-4"
                >
                  <div>
                    <p className="font-semibold">{device.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {device.ssh_user}@{device.base_url}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant={activeDeviceId === device.id ? "secondary" : "default"}
                      onClick={() => setActiveDevice(device.id)}
                    >
                      {activeDeviceId === device.id ? (
                        <><CheckCircle className="mr-2 h-4 w-4" /> Activo</>
                      ) : (
                        <><Play className="mr-2 h-4 w-4" /> Seleccionar</>
                      )}
                    </Button>
                    <Button size="icon" variant="outline" onClick={() => handleEdit(device)}>
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="destructive" onClick={() => handleDelete(device)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
