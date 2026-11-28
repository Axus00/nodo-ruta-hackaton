"""Autoescalado sencillo del servicio `backend` según su uso de CPU.

Docker Compose no incluye autoescalado por carga: este script hace de
controlador externo. Mantiene entre MIN y MAX réplicas:

  - Con las 2 réplicas activas por debajo del umbral, la tercera queda como
    reserva (no existe hasta que hace falta).
  - Si el promedio de CPU de las réplicas supera --alto durante --muestras
    comprobaciones seguidas, arranca una réplica más (hasta --maximo).
  - Si baja de --bajo durante --muestras seguidas, apaga la sobrante.

Traefik detecta las réplicas nuevas solas (proveedor Docker + healthcheck),
así que no hay que tocar su configuración.

Uso (desde la raíz del proyecto, con el stack levantado):
    python scripts/autoscaler.py
    python scripts/autoscaler.py --alto 50 --bajo 15 --intervalo 5
    python scripts/autoscaler.py --una-vez          # evalúa y sale (para cron)

Requiere el CLI de Docker en el PATH y permiso para usarlo.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = RAIZ / "docker-compose.yml"
SERVICIO = "backend"


def ejecutar(comando):
    return subprocess.run(comando, capture_output=True, text=True, check=True).stdout


def replicas_activas():
    """Nombres de los contenedores en ejecución del servicio backend."""
    salida = ejecutar([
        "docker", "ps",
        "--filter", f"label=com.docker.compose.service={SERVICIO}",
        "--filter", "status=running",
        "--format", "{{.Names}}",
    ])
    return [linea.strip() for linea in salida.splitlines() if linea.strip()]


def cpu_promedio(nombres):
    """Promedio de CPU (%) de los contenedores indicados."""
    if not nombres:
        return 0.0
    salida = ejecutar([
        "docker", "stats", "--no-stream", "--format", "{{.Name}};{{.CPUPerc}}", *nombres,
    ])
    valores = []
    for linea in salida.splitlines():
        _, _, cpu = linea.partition(";")
        try:
            valores.append(float(cpu.strip().rstrip("%")))
        except ValueError:
            continue
    return sum(valores) / len(valores) if valores else 0.0


def escalar(cantidad):
    subprocess.run([
        "docker", "compose", "-f", str(COMPOSE),
        "up", "-d", "--no-recreate", "--no-deps",
        "--scale", f"{SERVICIO}={cantidad}", SERVICIO,
    ], check=True)
    print(f"  -> {SERVICIO} escalado a {cantidad} réplica(s)", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Escala el backend según su CPU.")
    parser.add_argument("--minimo", type=int, default=2, help="réplicas mínimas (por defecto 2)")
    parser.add_argument("--maximo", type=int, default=3, help="réplicas máximas (por defecto 3)")
    parser.add_argument("--alto", type=float, default=60.0, help="CPU % para escalar (por defecto 60)")
    parser.add_argument("--bajo", type=float, default=15.0, help="CPU % para reducir (por defecto 15)")
    parser.add_argument("--muestras", type=int, default=3, help="comprobaciones seguidas (por defecto 3)")
    parser.add_argument("--intervalo", type=float, default=5.0, help="segundos entre comprobaciones (por defecto 5)")
    parser.add_argument("--una-vez", action="store_true", help="evalúa una sola vez y termina")
    args = parser.parse_args()

    if args.minimo < 1 or args.maximo < args.minimo:
        sys.exit("Rango de réplicas inválido: se espera 1 <= --minimo <= --maximo")
    if args.bajo > args.alto:
        sys.exit("--bajo no puede ser mayor que --alto")

    altas = bajas = 0
    print(f"Autoscaler: {SERVICIO} entre {args.minimo} y {args.maximo} réplicas "
          f"(alto={args.alto}%, bajo={args.bajo}%, cada {args.intervalo}s)", flush=True)
    try:
        while True:
            nombres = replicas_activas()
            actuales = len(nombres)
            cpu = cpu_promedio(nombres)
            print(f"[{time.strftime('%H:%M:%S')}] réplicas={actuales} cpu_promedio={cpu:.1f}%", flush=True)

            if cpu >= args.alto:
                altas, bajas = altas + 1, 0
            elif cpu <= args.bajo:
                altas, bajas = 0, bajas + 1
            else:
                altas = bajas = 0

            if altas >= args.muestras and actuales < args.maximo:
                escalar(actuales + 1)
                altas = 0
            elif bajas >= args.muestras and actuales > args.minimo:
                escalar(actuales - 1)
                bajas = 0

            if args.una_vez:
                return
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nAutoscaler detenido (las réplicas quedan como estén).", flush=True)


if __name__ == "__main__":
    main()
