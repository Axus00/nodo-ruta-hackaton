"""Prueba de extremo a extremo: las consultas a /pedidos y /health generan trazas que llegan a Logfire.

Ejecutar desde la raíz del repositorio:
    .venv/bin/python -m unittest tests.test_e2e_logfire -v

Requiere LOGFIRE_TOKEN (escritura) y LOGFIRE_READ_TOKEN (lectura) en el entorno o en el archivo .env
de la raíz; si falta alguno, la prueba se omite. Los valores de los tokens nunca se imprimen.
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
ESPERA_LOGFIRE = 90  # segundos máximos esperando que la traza aparezca en la API de consultas
INTERVALO_LOGFIRE = 3
SPAN_PEDIDOS = "GET /pedidos"
SPAN_HEALTH = "GET /health"
SPAN_LECTURA = "Leer datos de pedidos"


def leer_variable(nombre):
    """Toma la variable del entorno o, si no está, del .env de la raíz (formato CLAVE=valor)."""
    if os.environ.get(nombre):
        return os.environ[nombre]
    archivo = RAIZ / ".env"
    if not archivo.is_file():
        return None
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea.startswith("export "):
            linea = linea[len("export "):].lstrip()
        clave, separador, valor = linea.partition("=")
        if separador and clave.strip() == nombre:
            return valor.strip().strip("'\"") or None
    return None


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TrazaPedidosEnLogfire(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = leer_variable("LOGFIRE_TOKEN")
        cls.read_token = leer_variable("LOGFIRE_READ_TOKEN")
        if not cls.token or not cls.read_token:
            raise unittest.SkipTest(
                "Se requieren LOGFIRE_TOKEN y LOGFIRE_READ_TOKEN (entorno o .env en la raíz) para la prueba e2e contra Logfire"
            )

    def iniciar_servidor(self, data_path):
        instancia = f"e2e-{uuid.uuid4()}"
        puerto = puerto_libre()
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        log = open(Path(carpeta.name) / "servidor.log", "w+b")
        self.addCleanup(log.close)
        env = {**os.environ, "DATA_PATH": str(data_path), "INSTANCE_ID": instancia, "PORT": str(puerto),
               "LOGFIRE_TOKEN": self.token, "PYTHONUNBUFFERED": "1"}
        env.pop("LOGFIRE_READ_TOKEN", None)  # el servicio solo necesita el token de escritura
        proceso = subprocess.Popen([sys.executable, str(RAIZ / "app.py")], cwd=carpeta.name, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        self.addCleanup(self.terminar, proceso)
        self.log = log
        url = f"http://127.0.0.1:{puerto}"
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            if proceso.poll() is not None:
                self.fail(f"El servidor terminó al iniciar (código {proceso.returncode}):\n{self.salida()}")
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).close()
                return proceso, url, instancia
            except urllib.error.HTTPError:
                return proceso, url, instancia  # responde (p. ej. 503 con datos inválidos): ya está escuchando
            except OSError:
                time.sleep(0.2)
        self.fail(f"El servidor no respondió /health a tiempo:\n{self.salida()}")

    def salida(self):
        self.log.flush()
        self.log.seek(0)
        return self.log.read().decode("utf-8", "replace")[-2000:]

    @staticmethod
    def terminar(proceso):
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait(timeout=10)

    def detener_con_sigterm(self, proceso):
        """docker stop envía SIGTERM: el servicio debe salir limpio y enviar las trazas pendientes."""
        proceso.send_signal(signal.SIGTERM)
        try:
            codigo = proceso.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.fail(f"El servidor no terminó tras SIGTERM:\n{self.salida()}")
        self.assertEqual(codigo, 0, f"Salida inesperada tras SIGTERM:\n{self.salida()}")

    def consultar(self, url, ruta):
        try:
            with urllib.request.urlopen(f"{url}{ruta}", timeout=5) as r:
                return r.status, r.headers, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers, json.loads(e.read())

    def esperar_traza(self, trace_id, inicio, span_raiz):
        """Consulta la API de Logfire hasta encontrar los dos spans de la traza o agotar el tiempo."""
        from logfire.query_client import LogfireQueryClient, QueryRateLimitedError, UnexpectedResponseError

        self.assertRegex(trace_id, TRACE_ID)  # además evita inyectar texto arbitrario en el SQL
        sql = (
            "SELECT span_name, span_id, parent_span_id, service_name, http_response_status_code, "
            "level >= 'error' AS es_error, is_exception, exception_type, "
            "attributes->>'instancia' AS instancia, attributes->>'error.type' AS error_type, "
            "attributes->'pedidos.total' AS pedidos_total, attributes->>'pedidos.version' AS pedidos_version "
            f"FROM records WHERE trace_id = '{trace_id}' AND kind = 'span'"
        )
        limite = time.monotonic() + ESPERA_LOGFIRE
        filas = {}
        with LogfireQueryClient(read_token=self.read_token) as cliente:
            while True:
                espera = INTERVALO_LOGFIRE
                try:
                    resultado = cliente.query_json_rows(sql, min_timestamp=inicio - timedelta(minutes=5))
                    filas = {fila["span_name"]: fila for fila in resultado["rows"]}
                    if {span_raiz, SPAN_LECTURA} <= filas.keys():
                        return filas
                except QueryRateLimitedError as e:
                    espera = max(INTERVALO_LOGFIRE, min(e.retry_after or INTERVALO_LOGFIRE, 15))
                except UnexpectedResponseError:
                    pass  # error transitorio del servidor (5xx): se reintenta dentro del plazo
                if time.monotonic() + espera > limite:
                    self.fail(f"La traza {trace_id} no apareció completa en Logfire en {ESPERA_LOGFIRE} s; "
                              f"spans encontrados: {sorted(filas)}")
                time.sleep(espera)

    def test_pedidos_genera_traza_en_logfire(self):
        inicio = datetime.now(timezone.utc)
        proceso, url, instancia = self.iniciar_servidor(RAIZ / "pedidos.json")

        status, cabeceras, cuerpo = self.consultar(url, "/pedidos")
        self.assertEqual(status, 200)
        self.assertEqual(cuerpo["instancia"], instancia)
        self.assertEqual(len(cuerpo["pedidos"]), 6)
        trace_id = cabeceras.get("X-Trace-Id", "")
        self.assertRegex(trace_id, TRACE_ID)
        self.detener_con_sigterm(proceso)

        filas = self.esperar_traza(trace_id, inicio, SPAN_PEDIDOS)
        print(f"\nTraza encontrada en Logfire: {trace_id}", file=sys.stderr)
        raiz, lectura = filas[SPAN_PEDIDOS], filas[SPAN_LECTURA]
        self.assertIsNone(raiz["parent_span_id"])
        self.assertEqual(raiz["http_response_status_code"], 200)
        self.assertEqual(raiz["instancia"], instancia)
        self.assertEqual(raiz["service_name"], "nodo-ruta")
        self.assertFalse(raiz["es_error"])
        self.assertEqual(lectura["parent_span_id"], raiz["span_id"])
        self.assertEqual(lectura["service_name"], "nodo-ruta")
        self.assertEqual(lectura["pedidos_total"], 6)
        self.assertEqual(lectura["pedidos_version"], "datos-v1")

    def test_error_de_datos_marca_la_traza_como_error(self):
        inicio = datetime.now(timezone.utc)
        proceso, url, instancia = self.iniciar_servidor(self.datos_invalidos())

        status, cabeceras, cuerpo = self.consultar(url, "/pedidos")
        self.assertEqual(status, 503)
        self.assertEqual(cuerpo, {"estado": "error_datos", "instancia": instancia})
        trace_id = cabeceras.get("X-Trace-Id", "")
        self.assertRegex(trace_id, TRACE_ID)
        self.detener_con_sigterm(proceso)

        filas = self.esperar_traza(trace_id, inicio, SPAN_PEDIDOS)
        print(f"\nTraza de error encontrada en Logfire: {trace_id}", file=sys.stderr)
        raiz, lectura = filas[SPAN_PEDIDOS], filas[SPAN_LECTURA]
        self.assertEqual(raiz["http_response_status_code"], 503)
        self.assertEqual(raiz["instancia"], instancia)
        self.assertTrue(raiz["es_error"])
        self.assertEqual(raiz["error_type"], "JSONDecodeError")
        self.assertEqual(lectura["parent_span_id"], raiz["span_id"])
        self.assertTrue(lectura["es_error"])
        self.assertTrue(lectura["is_exception"])
        self.assertIn("JSONDecodeError", lectura["exception_type"])


    def datos_invalidos(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        invalido = Path(carpeta.name) / "pedidos.json"
        invalido.write_text('{"version": "roto", "pedidos": ', encoding="utf-8")
        return invalido

    def test_health_genera_traza_en_logfire(self):
        inicio = datetime.now(timezone.utc)
        proceso, url, instancia = self.iniciar_servidor(RAIZ / "pedidos.json")

        status, cabeceras, cuerpo = self.consultar(url, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(cuerpo, {"estado": "ok", "instancia": instancia, "version_datos": "datos-v1"})
        trace_id = cabeceras.get("X-Trace-Id", "")
        self.assertRegex(trace_id, TRACE_ID)
        self.detener_con_sigterm(proceso)

        filas = self.esperar_traza(trace_id, inicio, SPAN_HEALTH)
        print(f"\nTraza de /health encontrada en Logfire: {trace_id}", file=sys.stderr)
        raiz, lectura = filas[SPAN_HEALTH], filas[SPAN_LECTURA]
        self.assertIsNone(raiz["parent_span_id"])
        self.assertEqual(raiz["http_response_status_code"], 200)
        self.assertEqual(raiz["instancia"], instancia)
        self.assertEqual(raiz["service_name"], "nodo-ruta")
        self.assertFalse(raiz["es_error"])
        self.assertEqual(lectura["parent_span_id"], raiz["span_id"])
        self.assertEqual(lectura["pedidos_total"], 6)
        self.assertEqual(lectura["pedidos_version"], "datos-v1")

    def test_health_con_error_de_datos_marca_la_traza_como_error(self):
        inicio = datetime.now(timezone.utc)
        proceso, url, instancia = self.iniciar_servidor(self.datos_invalidos())

        status, cabeceras, cuerpo = self.consultar(url, "/health")
        self.assertEqual(status, 503)
        self.assertEqual(cuerpo, {"estado": "error_datos", "instancia": instancia})
        trace_id = cabeceras.get("X-Trace-Id", "")
        self.assertRegex(trace_id, TRACE_ID)
        self.detener_con_sigterm(proceso)

        filas = self.esperar_traza(trace_id, inicio, SPAN_HEALTH)
        print(f"\nTraza de error de /health encontrada en Logfire: {trace_id}", file=sys.stderr)
        raiz, lectura = filas[SPAN_HEALTH], filas[SPAN_LECTURA]
        self.assertEqual(raiz["http_response_status_code"], 503)
        self.assertEqual(raiz["instancia"], instancia)
        self.assertTrue(raiz["es_error"])
        self.assertEqual(raiz["error_type"], "JSONDecodeError")
        self.assertEqual(lectura["parent_span_id"], raiz["span_id"])
        self.assertTrue(lectura["es_error"])
        self.assertTrue(lectura["is_exception"])
        self.assertIn("JSONDecodeError", lectura["exception_type"])

if __name__ == "__main__":
    unittest.main()
