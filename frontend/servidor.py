"""Servidor local del frontend de Nodo Ruta (solo biblioteca estándar de Python).

Sirve los archivos de esta carpeta y reenvía /api/* a la API: /api/pedidos -> <api>/pedidos.
Así el navegador habla con un solo origen y el backend no necesita configurar CORS.

Uso:
    python frontend/servidor.py
    python frontend/servidor.py --api http://127.0.0.1:8080 --puerto 3000
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
PREFIJO_API = "/api/"
CABECERAS_REENVIADAS = ("Content-Type", "X-Trace-Id")


class Manejador(SimpleHTTPRequestHandler):
    api = "http://127.0.0.1:8080"
    # Tipos fijos: en Windows el registro puede declarar .js como text/plain.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
    }

    def do_GET(self):
        if self.path.startswith(PREFIJO_API):
            return self.reenviar()
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reenviar(self):
        destino = self.api + "/" + self.path[len(PREFIJO_API):]
        try:
            with urllib.request.urlopen(destino, timeout=5) as respuesta:
                self.responder(respuesta.status, respuesta.headers, respuesta.read())
        except urllib.error.HTTPError as error:
            # 4xx/5xx de la API (por ejemplo 503 error_datos): se entregan tal cual al navegador.
            self.responder(error.code, error.headers, error.read())
        except OSError:
            cuerpo = json.dumps({"error": "sin_conexion", "api": self.api}).encode("utf-8")
            self.responder(502, {"Content-Type": "application/json; charset=utf-8"}, cuerpo)

    def responder(self, status, cabeceras, cuerpo):
        self.send_response(status)
        for nombre in CABECERAS_REENVIADAS:
            if cabeceras.get(nombre):
                self.send_header(nombre, cabeceras[nombre])
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main():
    parser = argparse.ArgumentParser(description="Sirve el frontend de Nodo Ruta y reenvía /api/* a la API.")
    parser.add_argument("--api", default=os.environ.get("NODO_RUTA_API", "http://127.0.0.1:8080"),
                        help="dirección de la API (por defecto http://127.0.0.1:8080 o la variable NODO_RUTA_API)")
    parser.add_argument("--puerto", type=int, default=3000, help="puerto del frontend (por defecto 3000)")
    args = parser.parse_args()

    Manejador.api = args.api.rstrip("/")
    # Solo escucha en 127.0.0.1: el frontend local no queda expuesto a la red.
    servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), partial(Manejador, directory=str(CARPETA)))
    print(f"Frontend en http://127.0.0.1:{args.puerto}  ·  API: {Manejador.api}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
