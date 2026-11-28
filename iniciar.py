"""Levanta Nodo Ruta completo en local: backend (puerto 8080) y frontend (puerto 3000).

Uso, desde la carpeta del proyecto:
    python iniciar.py
    python iniciar.py --puerto-api 8081 --puerto-web 3001

La primera vez crea .venv, instala requirements.txt y prepara data/pedidos.json.
Ctrl+C detiene los dos servidores.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
# logfire 6 (requirements.txt) no se instala en Python 3.9, que es el python3 que trae macOS.
VERSION_MINIMA = (3, 10)


def paso(texto):
    print(f"> {texto}", flush=True)


def version_de(python):
    """(mayor, menor) del intérprete indicado, o (0, 0) si no se puede ejecutar."""
    salida = subprocess.run(
        [python, "-c", "import sys; print(*sys.version_info[:2])"], capture_output=True, text=True
    )
    try:
        return tuple(int(n) for n in salida.stdout.split())
    except ValueError:
        return (0, 0)


def preparar_entorno():
    if not PYTHON.exists():
        paso("Creando el entorno virtual .venv (solo la primera vez)")
        venv.create(VENV, with_pip=True)
    elif version_de(PYTHON) < VERSION_MINIMA:
        # Un .venv creado antes con Python 3.9 nunca podrá instalar las dependencias: se rehace.
        paso("El .venv existente usa Python anterior a 3.10; se crea de nuevo con este Python")
        venv.create(VENV, with_pip=True, clear=True)
    if subprocess.run([PYTHON, "-c", "import logfire"], capture_output=True).returncode != 0:
        paso("Instalando requirements.txt (solo la primera vez, tarda unos minutos)")
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", RAIZ / "requirements.txt"],
            check=True,
        )
    if not (RAIZ / "data" / "pedidos.json").exists():
        paso("Preparando la copia de trabajo data/pedidos.json (solo la primera vez)")
        subprocess.run([PYTHON, RAIZ / "scripts" / "datos.py", "preparar"], check=True)


def entorno_con_env():
    """Entorno actual más las variables de .env (LOGFIRE_TOKEN, ...); lo ya definido en el entorno manda.

    Sin LOGFIRE_TOKEN el backend responde igual, pero no envía trazas a Logfire.
    """
    entorno = dict(os.environ)
    archivo = RAIZ / ".env"
    if archivo.is_file():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("export "):
                linea = linea[len("export "):].lstrip()
            if not linea or linea.startswith("#"):
                continue
            clave, separador, valor = linea.partition("=")
            if separador and clave.strip() and not entorno.get(clave.strip()):
                entorno[clave.strip()] = valor.strip().strip("'\"")
    if not entorno.get("LOGFIRE_TOKEN"):
        paso("Aviso: no hay LOGFIRE_TOKEN (ni en el entorno ni en .env); las trazas no se enviarán a Logfire")
    return entorno


def puerto_ocupado(puerto):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def esperar(url, proceso, segundos=30):
    """Espera a que la URL responda. Devuelve False si el proceso se cae o se acaba el tiempo."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            return False
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return True
        except urllib.error.HTTPError:
            return True  # Responde, aunque sea con error (por ejemplo, 503 si los datos son inválidos).
        except OSError:
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Levanta el backend y el frontend de Nodo Ruta en local.")
    parser.add_argument("--puerto-api", type=int, default=8080, help="puerto del backend (por defecto 8080)")
    parser.add_argument("--puerto-web", type=int, default=3000, help="puerto del frontend (por defecto 3000)")
    parser.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador al terminar")
    args = parser.parse_args()

    if sys.version_info < VERSION_MINIMA:
        sys.exit(
            f"Nodo Ruta necesita Python 3.10 o superior y este es {sys.version.split()[0]}.\n"
            "En Mac/Linux usen `make iniciar` (busca solo un Python 3.10+) o, por ejemplo, `python3.12 iniciar.py`.\n"
            "Si no tienen uno: https://www.python.org/downloads/ (en Mac también: brew install python@3.12)."
        )

    for puerto, opcion in ((args.puerto_api, "--puerto-api"), (args.puerto_web, "--puerto-web")):
        if puerto_ocupado(puerto):
            sys.exit(
                f"El puerto {puerto} ya está en uso. Cierren lo que lo usa o cambien el puerto con {opcion}.\n"
                "Si es el Docker Compose del proyecto (también usa el 8080), deténganlo con: make compose-down"
            )

    preparar_entorno()

    api = f"http://127.0.0.1:{args.puerto_api}"
    web = f"http://127.0.0.1:{args.puerto_web}"
    procesos = []
    try:
        paso(f"Levantando el backend en {api}")
        backend = subprocess.Popen(
            [PYTHON, RAIZ / "scripts" / "ejecutar_local.py", "--puerto", str(args.puerto_api), "--id", "local-1"],
            cwd=RAIZ,
            env=entorno_con_env(),
        )
        procesos.append(backend)
        if not esperar(api + "/health", backend):
            sys.exit("El backend no arrancó. Revisen los mensajes de arriba.")

        paso(f"Levantando el frontend en {web}")
        frontend = subprocess.Popen(
            [PYTHON, RAIZ / "frontend" / "servidor.py", "--api", api, "--puerto", str(args.puerto_web)],
            cwd=RAIZ,
        )
        procesos.append(frontend)
        if not esperar(web + "/", frontend):
            sys.exit("El frontend no arrancó. Revisen los mensajes de arriba.")

        print(f"\nListo: abran {web}  (Ctrl+C para detener todo)\n", flush=True)
        if not args.sin_navegador:
            webbrowser.open(web)

        while all(p.poll() is None for p in procesos):
            time.sleep(1)
        print("Uno de los servidores se detuvo; se cierra el otro.", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procesos:
            if p.poll() is None:
                p.terminate()
        for p in procesos:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        if procesos:
            print("Servidores detenidos.", flush=True)


if __name__ == "__main__":
    main()
