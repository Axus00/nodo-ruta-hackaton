# Imagen del frontend de Nodo Ruta: sirve los archivos estáticos y reenvía
# /api/* a la API (en Compose, a través de Traefik). Solo usa la biblioteca
# estándar de Python, así que no necesita instalar dependencias.
FROM python:3-slim

WORKDIR /app
COPY servidor.py index.html estilos.css app.js api.js /app/

# Escucha en todas las interfaces para que el puerto publicado por Docker funcione.
ENV PYTHONUNBUFFERED=1 \
    NODO_RUTA_HOST=0.0.0.0 \
    NODO_RUTA_API=http://traefik:80

USER 10001
EXPOSE 3000
CMD ["python", "servidor.py"]
