import json
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import logfire
from opentelemetry.trace import SpanKind

DATA = Path(os.environ.get("DATA_PATH", "pedidos.json"))
INSTANCE = os.environ.get("INSTANCE_ID", "instancia-ejemplo")
ERRORES_DATOS = (OSError, ValueError, TypeError, AttributeError)

# Las trazas solo se envían si existe LOGFIRE_TOKEN; sin token el servicio responde igual y no envía nada.
# console=False mantiene la salida estándar del servicio igual que antes: las trazas se consultan en Logfire.
logfire.configure(service_name="nodo-ruta", send_to_logfire="if-token-present", console=False)

def leer_datos():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(data.get("pedidos"), list):
        raise ValueError("Formato de datos inválido")
    return data

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/pedidos":
            return self.responder_pedidos()
        if route not in ("/", "/health"):
            status, response = 404, {"error": "Ruta no disponible", "instancia": INSTANCE}
        else:
            try:
                data = leer_datos()
                status = 200
                if route == "/health":
                    response = {"estado": "ok", "instancia": INSTANCE, "version_datos": data.get("version")}
                else:
                    response = {"servicio": "Nodo Ruta - caso ficticio", "instancia": INSTANCE, "rutas": ["/health", "/pedidos"]}
            except ERRORES_DATOS:
                status, response = 503, {"estado": "error_datos", "instancia": INSTANCE}
        self.responder(status, response)

    def responder_pedidos(self):
        # Única ruta trazada: la consulta de pedidos es la operación de negocio que se quiere seguir.
        atributos = {"http.request.method": "GET", "url.path": "/pedidos", "http.route": "/pedidos", "instancia": INSTANCE}
        with logfire.span("GET /pedidos", _span_kind=SpanKind.SERVER, **atributos) as span:
            try:
                with logfire.span("Leer datos de pedidos") as lectura:
                    data = leer_datos()
                    lectura.set_attribute("pedidos.version", data.get("version"))
                    lectura.set_attribute("pedidos.total", len(data["pedidos"]))
                status, response = 200, {"instancia": INSTANCE, **data}
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
