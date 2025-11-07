# 📖 Manual de Usuario: Panel de Administración Pi Admin

## 🚀 1. Introducción

Bienvenido al Panel de Administración Pi Admin. Esta es una interfaz web centralizada diseñada para administrar, monitorear y desplegar aplicaciones en tus dispositivos Raspberry Pi de una manera moderna e intuitiva.

Este panel te permite desde ver métricas en tiempo real hasta ejecutar comandos directamente en la terminal, todo desde la comodidad de tu navegador.

---

## 🚦 2. Primeros Pasos

### Acceso y Login

1.  **Accede a la Interfaz:** Abre tu navegador web y navega a la dirección donde se está ejecutando el frontend (normalmente `http://localhost:5173` si lo ejecutas en modo de desarrollo).
2.  **Inicio de Sesión:** Se te presentará una pantalla de login. Utiliza las credenciales de `ADMIN_USER` y `ADMIN_PASS` que has configurado en el entorno de tu servidor backend.

### Interfaz Principal

Una vez dentro, verás dos áreas principales:

*   **Barra Lateral Izquierda (Menú):** Contiene los enlaces de navegación a todas las secciones principales de la aplicación.
*   **Barra Superior (Cabecera):** Muestra el dispositivo que estás administrando actualmente y el botón para cerrar sesión.

### Selector de Dispositivo Activo

En la barra superior, encontrarás un menú desplegable para seleccionar el **dispositivo activo**. 

*   **Esta Raspberry (local):** Se refiere al propio dispositivo Raspberry Pi donde se está ejecutando el backend. La mayoría de las funciones avanzadas (como la terminal o la gestión de servicios) solo están disponibles para el dispositivo local.
*   **Otros Dispositivos:** Si has añadido otras Raspberry Pis en la sección `Dispositivos`, puedes seleccionarlas aquí para ver sus métricas a través de un proxy.

---

## 🖥️ 3. Secciones de la Aplicación

A continuación se detalla cada sección disponible en la barra de navegación lateral.

### Dashboard

Es la pantalla principal. Te ofrece una vista rápida del estado de salud de tu dispositivo activo, mostrando métricas en tiempo real:

*   **CPU:** Uso actual del procesador y la carga media del sistema.
*   **RAM:** Porcentaje de memoria RAM utilizada.
*   **Disco:** Uso del disco de almacenamiento principal.
*   **Temperatura:** Temperatura del procesador (si está disponible).
*   **Gráfico de CPU:** Una gráfica que muestra el historial reciente del uso de la CPU.

### ⚙️ Servicios

Esta sección te permite administrar los servicios que se ejecutan en tu Pi a través de `systemd`.

*   **Funcionalidad:** Puedes ver una lista de los servicios permitidos, comprobar su estado (`activo`, `inactivo`) y ejecutar acciones como **iniciar, detener y reiniciar** cada servicio.
*   **Uso:** Haz clic en los botones de acción correspondientes a cada servicio. Usa el botón "Refrescar" para obtener el estado más reciente.

### 📜 Logs

Aquí puedes visualizar los registros (logs) de los servicios en tiempo real, lo cual es fundamental para depurar problemas.

*   **Uso:** Selecciona la unidad `systemd` que te interesa del menú desplegable para ver sus logs en vivo.

*   **🤖 ¡Función Inteligente! Análisis con IA:**
    *   **¿Qué hace?:** El botón **"Analizar con IA"** envía los logs actuales a una inteligencia artificial para que los analice. La IA te devolverá una explicación del problema y, si es posible, un comando de terminal para solucionarlo.

    *   **Diagrama de Funcionamiento:**
        ```
              +------------------+        +-----------------+        +-----------------+
              |  Frontend (Tu    |--(1)-->|  Backend (Este  |--(2)-->|   API Externa   |
              |   Navegador)     |        |    Proyecto)    |        |      (IA)       |
              +------------------+        +-----------------+        +-----------------+
                     ^      |                      |                         |
                     |      |                      |                         |
                     +------(4)--------------------+---------(3)-------------+
        ```
        *(1) Envías los logs para analizar.*
        *(2) Tu backend llama a la IA con los logs y tu clave secreta.*
        *(3) La IA devuelve el análisis.*
        *(4) Tu backend te muestra el resultado de forma segura.*

    *   **CONFIGURACIÓN (MUY IMPORTANTE):**
        > Para que esta función se active, debes configurar **dos variables de entorno** en el servidor donde se ejecuta el backend. Si no lo haces, el botón mostrará un error indicando que la función no está configurada.
        >
        > Crea un archivo `.env` en la raíz del proyecto `raspi_deployer_starter` (si no existe) y añade lo siguiente:
        
        ```shell
        # Ejemplo para la API de OpenAI / GPT
        AI_API_ENDPOINT="https://api.openai.com/v1/chat/completions"
        AI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        ```
        > *   `AI_API_ENDPOINT`: La URL del servicio de IA que quieres usar.
        > *   `AI_API_KEY`: Tu clave secreta para ese servicio.

### 📤 Deploy

Esta sección te permite desplegar nuevo código en tu Raspberry Pi de dos maneras:

1.  **Deploy ZIP/TAR:** Sube un archivo comprimido (`.zip`, `.tar.gz`, etc.). El backend lo descomprimirá en el directorio de destino que especifiques.
2.  **Git pull:** Si tu aplicación está en un repositorio Git, puedes hacer que el servidor ejecute `git pull` para actualizarla a la última versión de una rama específica.

### 🌐 Dispositivos

Aquí puedes registrar otras Raspberry Pis de tu red para poder monitorearlas desde este mismo panel. Esto es útil para entornos con múltiples dispositivos.

*   **Uso:** Rellena el formulario para añadir un nuevo dispositivo (necesitarás su ID, nombre y URL base). Una vez añadido, podrás seleccionarlo en el **Selector de Dispositivo Activo** de la barra superior.

### ⌨️ Terminal

Te proporciona una **terminal SSH completamente funcional** dentro de tu navegador. Tienes acceso directo de bajo nivel al dispositivo local.

*   **Uso:** Simplemente escribe los comandos que necesites y presiona Enter. 
*   **Credenciales:** Las credenciales para esta conexión se configuran directamente en el código del backend (`ssh_ws.py`), por lo que no necesitas introducirlas aquí.

### 🔧 Ajustes

Esta sección agrupa acciones críticas a nivel de sistema.

| Botón | Función |
| :--- | :--- |
| **Descargar backup** | Crea y descarga un archivo `.tar.gz` con archivos de configuración clave. |
| **Reiniciar** | Reinicia el sistema operativo de la Raspberry Pi. |
| **Apagar** | Apaga el dispositivo de forma segura. |

> **ADVERTENCIA:**
> *   Al **reiniciar**, se perderá cualquier trabajo no guardado.
> *   Al **apagar**, necesitarás acceso físico al dispositivo para volver a encenderlo.

---

## 💡 Conclusión

Este panel de control unifica todas las herramientas que necesitas para gestionar tus Raspberry Pis de forma eficiente. Explora cada sección y aprovecha las funcionalidades, especialmente el análisis de logs con IA, para simplificar tus tareas de administración.