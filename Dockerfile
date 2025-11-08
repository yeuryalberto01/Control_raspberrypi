FROM python:3.12-slim
WORKDIR /app

# Instala dependencias antes de copiar el resto del proyecto para aprovechar cache.
COPY raspi_deployer_starter/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app

# Apunta al paquete real dentro de raspi_deployer_starter.
CMD ["uvicorn","raspi_deployer_starter.app.main:app","--host","0.0.0.0","--port","8080"]
