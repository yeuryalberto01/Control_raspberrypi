# 🚀 Panel de Control Raspberry Pi - Guía Completa

## 📋 **Resumen del Proyecto**

Sistema completo para **descubrir, monitorear y desplegar** aplicaciones en dispositivos Raspberry Pi usando SSH. Incluye:

- 🔍 **Detección automática** de Raspberry Pi en la red
- 📊 **Monitoreo remoto** en tiempo real
- 🚀 **Despliegue automatizado** one-click
- 🎨 **Interfaz modular** refactorizada
- 🔒 **Integración SSH** completa

## 🛠️ **Instalación Rápida**

### Opción 1: Script Automático (Recomendado)
```powershell
# Ejecutar el script de setup completo
.\setup_and_run.ps1
```

### Opción 2: Instalación Manual
```powershell
# 1. Ir al directorio del proyecto
cd "C:\Users\yeury\Desktop\Proyecto Cenecompuc\Panel para las Rasberry pi"

# 2. Quitar atributos de solo lectura
attrib -R -S *.* /S

# 3. Crear y activar entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 4. Instalar dependencias
pip install -e .
pip install customtkinter psutil scikit-learn numpy joblib paramiko fabric invoke jinja2 python-dotenv zeroconf
pip install -r raspi_deployer_starter\examples\fastapi_demo\requirements.txt
```

## 🎯 **Master Launcher (Recomendado)**

### Launcher Maestro Interactivo
```powershell
# Ejecutar el launcher maestro (menú interactivo)
.\master_launcher.ps1
```

**Opciones del Master Launcher:**
- 🔧 **Setup Completo** - Instalación automática del sistema
- 🔍 **Escanear Red** - Buscar Raspberry Pi automáticamente
- 🌐 **Iniciar Servidor** - Levantar backend FastAPI
- 🚀 **Launcher Refactorizado** - Interfaz gráfica completa
- 🔐 **Probar SSH** - Verificar integración SSH
- 🎉 **Ejecutar TODO** - Setup + servidor + escaneo completo

### Uso con Parámetros
```powershell
# Setup automático
.\master_launcher.ps1 -Setup

# Escanear red específica
.\master_launcher.ps1 -Scan -Network "192.168.1.0/24" -Method "ssh"

# Iniciar servidor
.\master_launcher.ps1 -Server

# Probar SSH
.\master_launcher.ps1 -SSHTest

# Todo el flujo automático
.\master_launcher.ps1 -All
```

## 🚀 **Uso del Sistema**

### 1. Iniciar el Backend FastAPI
```powershell
uvicorn raspi_deployer_starter.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Escanear Red en Busca de Raspberry Pi
```powershell
# Opción automática
.\scan_network.ps1

# Opción manual
curl.exe -N -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/discover -d '{"scan_method":"ssh","network":"192.168.1.0/24","timeout":1.5,"max_concurrency":100}'
```

### 3. Usar el Launcher Refactorizado
```powershell
python raspi_deployer_starter/launcher/ultimate_launcher_refactored.py
```

### 4. Probar Integración SSH
```powershell
python raspi_deployer_starter/examples/example_ssh_launcher.py
```

## 🌐 **URLs y Endpoints**

| Servicio | URL | Descripción |
|----------|-----|-------------|
| **Panel FastAPI** | http://127.0.0.1:8000 | Interfaz web principal |
| **Documentación API** | http://127.0.0.1:8000/docs | Swagger UI completo |
| **Health Check** | http://127.0.0.1:8000/health | Verificación de estado |
| **Redes Locales** | http://127.0.0.1:8000/api/local-networks | Detectar redes disponibles |

## 📊 **Funcionalidades del API**

### Detección de Dispositivos
```bash
# Escanear con SSH (recomendado)
POST /api/discover
{
  "scan_method": "ssh",
  "network": "192.168.1.0/24",
  "timeout": 1.5,
  "max_concurrency": 100
}

# Escanear con Ping
POST /api/discover
{
  "scan_method": "ping",
  "network": "192.168.1.0/24"
}

# Escanear con ARP
POST /api/discover
{
  "scan_method": "arp",
  "network": "192.168.1.0/24"
}
```

### Obtener Detalles de Dispositivo
```bash
POST /api/device/details/{ip}
{
  "user": "pi",
  "password": "tu_password"
}
```

## 🔧 **Arquitectura del Sistema**

```
📁 Proyecto/
├── 🎯 master_launcher.ps1        # Launcher maestro interactivo
├── 🚀 setup_and_run.ps1          # Script de instalación automática
├── 🔍 scan_network.ps1           # Script de escaneo de red
├── 📚 ROADMAP_RASPBERRY_PI_IMPROVEMENTS.md  # Plan de mejoras futuras
├── 📦 raspi_deployer_starter/
│   ├── 🐍 app/                   # Backend FastAPI + módulos SSH
│   │   ├── main.py               # API principal
│   │   ├── ssh_manager.py        # ✅ Gestión conexiones SSH
│   │   ├── remote_deployer.py    # ✅ Despliegue remoto
│   │   └── device_monitor.py     # ✅ Monitoreo dispositivos
│   ├── 🎨 launcher/              # Launcher refactorizado
│   │   ├── ultimate_launcher_refactored.py
│   │   └── 📁 modules/           # Arquitectura modular
│   │       ├── database.py       # Gestión de BD
│   │       ├── ssh_manager.py    # Conexiones SSH
│   │       ├── remote_deployer.py # Despliegue remoto
│   │       ├── device_monitor.py # Monitoreo
│   │       └── ui_manager.py     # Interfaz
│   ├── 🔐 examples/example_ssh_launcher.py # ✅ Demo integración SSH
│   ├── 🚀 deploy/                # Sistema de deploy existente
│   └── 📝 examples/fastapi_demo/ # Proyecto de ejemplo
```

## 🔐 **Configuración SSH**

### Credenciales por Defecto
- **Usuario:** `pi`
- **Puerto:** `22`
- **Método:** Contraseña (se puede cambiar a clave SSH)

### Variables de Entorno
```bash
# Archivo .env en la raíz del proyecto
PI_HOST=192.168.1.161
PI_USER=yeury
PI_HOST_CANDIDATES=raspberrypi.local,192.168.1.161
PI_SUBNET=192.168.1.0/24
```

## 📈 **Funcionalidades Implementadas**

### ✅ **Completadas**
- [x] Arquitectura modular refactorizada
- [x] **Módulos SSH completos:**
  - [x] `ssh_manager.py` - Gestión avanzada de conexiones SSH
  - [x] `remote_deployer.py` - Despliegue remoto automatizado
  - [x] `device_monitor.py` - Monitoreo completo con métricas y alertas
- [x] **Scripts de automatización:**
  - [x] `master_launcher.ps1` - Launcher maestro interactivo
  - [x] `setup_and_run.ps1` - Instalación automática completa
  - [x] `scan_network.ps1` - Escaneo de red inteligente
- [x] API FastAPI completa para detección
- [x] Persistencia en base de datos SQLite
- [x] `example_ssh_launcher.py` - Demo de integración SSH

### 🔄 **En Desarrollo**
- [ ] Interfaz gráfica completa para SSH
- [ ] Dashboard de monitoreo visual
- [ ] Detección automática avanzada
- [ ] Sistema de backup/restore
- [ ] APIs REST completas

## 🐛 **Solución de Problemas**

### Error: "No se puede conectar al dispositivo"
```powershell
# Verificar que la Raspberry Pi esté encendida
ping 192.168.1.161

# Verificar SSH
ssh pi@192.168.1.161
```

### Error: "Módulo no encontrado"
```powershell
# Reinstalar dependencias
pip install -e .
pip install -r requirements.txt
```

### Error: "Puerto ocupado"
```powershell
# Cambiar puerto en el comando uvicorn
uvicorn raspi_deployer_starter.app.main:app --host 0.0.0.0 --port 8080 --reload
```

## 📞 **Soporte y Desarrollo**

### Comandos Útiles para Desarrollo
```powershell
# Ejecutar tests
python -m pytest raspi_deployer_starter/tests/ -v

# Ver logs del launcher
python raspi_deployer_starter/launcher/ultimate_launcher_refactored.py

# Probar integración SSH
python raspi_deployer_starter/examples/example_ssh_launcher.py
```

### Archivos Importantes
- `ROADMAP_RASPBERRY_PI_IMPROVEMENTS.md` - Plan de mejoras futuras
- `setup_and_run.ps1` - Instalación automática
- `scan_network.ps1` - Escaneo de red
- `raspi_deployer_starter/launcher/modules/` - Arquitectura modular

## 🎯 **Próximos Pasos**

### 🚀 **Inicio Rápido Recomendado**
```powershell
# 1. Usar el launcher maestro (opción más fácil)
.\master_launcher.ps1

# Seleccionar opción 6: "Ejecutar TODO"
# Esto hace setup completo + servidor + escaneo automático
```

### 📋 **Pasos Manuales (Alternativo)**
1. **Ejecutar setup automático:** `.\setup_and_run.ps1`
2. **Probar detección:** `.\scan_network.ps1`
3. **Explorar funcionalidades:** Ver documentación en `/docs`
4. **Probar SSH:** `.\master_launcher.ps1 -SSHTest`
5. **Implementar mejoras:** Seguir el roadmap para funcionalidades avanzadas

### 🔧 **Comandos del Master Launcher**
```powershell
# Menú interactivo completo
.\master_launcher.ps1

# Comandos directos
.\master_launcher.ps1 -Setup    # Instalación
.\master_launcher.ps1 -Scan     # Escaneo de red
.\master_launcher.ps1 -Server   # Iniciar API
.\master_launcher.ps1 -All      # Todo automático
```

---

**Proyecto:** Panel de Control Raspberry Pi con SSH  
**Versión:** 2.1.0  
**Fecha:** Noviembre 2025  
**Estado:** Funcional y listo para uso

## Scripts para Raspberry Pi

`ash
python3 scripts/install_backend_service.sh
chmod +x scripts/deploy_frontend_to_nginx.sh
./scripts/deploy_frontend_to_nginx.sh
`\r\nEl primer script crea el servicio systemd 'pi-admin'. El segundo compila el frontend y configura nginx para servirlo desde /var/www/pi-admin.\r\n

## Scripts para Raspberry Pi

```bash
python3 scripts/install_backend_service.sh
chmod +x scripts/deploy_frontend_to_nginx.sh
./scripts/deploy_frontend_to_nginx.sh
```

El primer script crea el servicio systemd 'pi-admin'. El segundo compila el frontend y configura nginx para servirlo desde /var/www/pi-admin.
