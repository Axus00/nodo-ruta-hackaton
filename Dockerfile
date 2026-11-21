FROM python:3-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py
COPY pedidos.json /data/pedidos.json
# LOGFIRE_TOKEN se entrega solo al ejecutar el contenedor (docker run -e / secreto de la plataforma), nunca en la imagen.
ENV DATA_PATH=/data/pedidos.json PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8080
CMD ["python", "app.py"]
