import json
import os
import signal
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import logfire
import psycopg
from opentelemetry.trace import SpanKind
from psycopg.rows import dict_row

# Sin INSTANCE_ID (por ejemplo con réplicas de Compose) se usa el hostname del
# contenedor, que Docker genera único: así se distingue qué réplica respondió.
INSTANCE = os.environ.get("INSTANCE_ID") or socket.gethostname()
ERRORES_DATOS = (psycopg.Error, OSError, ValueError, TypeError, AttributeError)

# Las trazas solo se envían si existe LOGFIRE_TOKEN; sin token el servicio responde igual y no envía nada.
# console=False mantiene la salida estándar del servicio igual que antes: las trazas se consultan en Logfire.
logfire.configure(service_name="nodo-ruta", send_to_logfire="if-token-present", console=False)


def conectar():
    """Abre una conexión corta a PostgreSQL (una por petición: el servidor usa hilos).

    Prioriza DATABASE_URL; si no existe, arma la conexión con las variables POSTGRES_*.
    Los timeouts evitan que una base lenta bloquee las peticiones.
    """
    comun = {
        "connect_timeout": 3,
        "application_name": "nodo-ruta",
        "options": "-c statement_timeout=3000",
        "row_factory": dict_row,
    }
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg.connect(url, **comun)
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "estudia_logitica"),
        user=os.environ.get("POSTGRES_USER", "admin_estudia"),
        password=os.environ.get("POSTGRES_PASSWORD", "admin_etudia_123."),
        **comun,
    )


def leer_datos():
    """Consulta los pedidos en la tabla `pedidos` y devuelve la misma forma que antes el JSON."""
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute("SELECT id, zona, estado FROM pedidos ORDER BY id")
        pedidos = cursor.fetchall()
        version = conexion.info.dbname
    if not isinstance(pedidos, list):
        raise ValueError("Respuesta inesperada de la base de datos")
    return {"version": version, "pedidos": pedidos}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/pedidos":
            return self.responder_trazado(route, lambda data: {"instancia": INSTANCE, **data})
        if route == "/health":
            return self.responder_trazado(
                route, lambda data: {"estado": "ok", "instancia": INSTANCE, "version_datos": data.get("version")}
            )
        if route != "/":
            status, response = 404, {"error": "Ruta no disponible", "instancia": INSTANCE}
        else:
            try:
                leer_datos()
                status = 200
                response = {"servicio": "Nodo Ruta - caso ficticio", "instancia": INSTANCE, "rutas": ["/health", "/pedidos"]}
            except ERRORES_DATOS:
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE}
        self.responder(status, response)

    def responder_trazado(self, route, armar_respuesta):
        # Rutas trazadas: /pedidos (consulta de negocio) y /health (salud de la instancia y de sus datos).
        # Ambas leen los datos, así que comparten la misma estructura de traza.
        atributos = {"http.request.method": "GET", "url.path": route, "http.route": route, "instancia": INSTANCE}
        # El nombre se arma fuera de la llamada: logfire inspecciona los f-strings y usaría "GET {route}" como nombre.
        nombre = f"GET {route}"
        with logfire.span(nombre, _span_name=nombre, _span_kind=SpanKind.SERVER, **atributos) as span:
            try:
                with logfire.span("Leer datos de pedidos") as lectura:
                    data = leer_datos()
                    lectura.set_attribute("pedidos.version", data.get("version"))
                    lectura.set_attribute("pedidos.total", len(data["pedidos"]))
                status, response = 200, armar_respuesta(data)
            except ERRORES_DATOS as error:
                # El span hijo ya registró la excepción; aquí se marca la solicitud como fallida.
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE}
                span.set_level("error")
                span.set_attribute("error.type", type(error).__name__)
            span.set_attribute("http.response.status_code", status)
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.responder(status, response, {"X-Trace-Id": trace_id})

    def responder(self, status, response, cabeceras=None):
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for nombre, valor in (cabeceras or {}).items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(payload)

def detener(signum, frame):
    # SIGTERM (docker stop) termina como Ctrl+C para que logfire envíe las trazas pendientes al salir.
    raise KeyboardInterrupt

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, detener)
    port = int(os.environ.get("PORT", "8080"))
    print(f"Nodo Ruta: {INSTANCE}, puerto {port}", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
