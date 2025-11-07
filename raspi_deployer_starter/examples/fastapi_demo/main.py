"""
🚀 API de Ejemplo - FastAPI
Proyecto de demostración para Ultimate Launcher
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import time
import psutil
from datetime import datetime

app = FastAPI(
    title="API de Ejemplo - Ultimate Launcher",
    description="API de demostración para probar el lanzador definitivo",
    version="1.0.0"
)

# Configurar CORS para desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Item(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    in_stock: bool = True

class SystemInfo(BaseModel):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float

# Base de datos simulada
items_db = [
    Item(id=1, name="Ultimate Launcher", description="El lanzador más avanzado", price=999.99),
    Item(id=2, name="CustomTkinter GUI", description="Interfaz moderna y elegante", price=299.99),
    Item(id=3, name="ML Predictor", description="Inteligencia artificial integrada", price=499.99),
]

@app.get("/")
async def root():
    """Endpoint raíz con información del API."""
    return {
        "message": "🚀 Ultimate Launcher API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now(),
        "endpoints": {
            "items": "/items",
            "system": "/system/info",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "uptime": time.time(),
        "version": "1.0.0"
    }

@app.get("/items", response_model=List[Item])
async def get_items():
    """Obtener todos los items."""
    return items_db

@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    """Obtener un item específico por ID."""
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item no encontrado")

@app.post("/items", response_model=Item)
async def create_item(item: Item):
    """Crear un nuevo item."""
    # Verificar que el ID no exista
    for existing_item in items_db:
        if existing_item.id == item.id:
            raise HTTPException(status_code=400, detail="ID ya existe")

    items_db.append(item)
    return item

@app.get("/system/info", response_model=SystemInfo)
async def get_system_info():
    """Obtener información del sistema."""
    return SystemInfo(
        timestamp=datetime.now(),
        cpu_percent=psutil.cpu_percent(interval=1),
        memory_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage('/').percent
    )

@app.get("/demo/slow")
async def slow_endpoint(delay: int = 2):
    """Endpoint que simula procesamiento lento."""
    time.sleep(delay)
    return {
        "message": f"Procesamiento completado después de {delay} segundos",
        "timestamp": datetime.now()
    }

@app.get("/demo/error")
async def error_endpoint():
    """Endpoint que genera un error para testing."""
    raise HTTPException(
        status_code=500,
        detail="Error simulado para testing del lanzador"
    )

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor FastAPI de ejemplo...")
    print("📖 Documentación disponible en: http://localhost:8000/docs")
    print("🔗 API raíz: http://localhost:8000/")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)