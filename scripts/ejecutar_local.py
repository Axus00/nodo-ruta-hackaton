from pathlib import Path
import argparse, importlib.util, os
p=argparse.ArgumentParser(description="Ejecutar una instancia local del caso Nodo Ruta")
p.add_argument("--puerto",type=int,default=8080)
p.add_argument("--id",default="local-1")
a=p.parse_args()
# Por defecto, la base publicada por docker compose (127.0.0.1:5433).
# Se puede sobrescribir con POSTGRES_HOST / POSTGRES_PORT / DATABASE_URL.
os.environ.setdefault("POSTGRES_HOST","127.0.0.1")
os.environ.setdefault("POSTGRES_PORT","5433")
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("nodo_app",root/"app.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod.INSTANCE=a.id
print(f"Instancia {a.id}: http://127.0.0.1:{a.puerto}/health",flush=True)
server=mod.ThreadingHTTPServer(("127.0.0.1",a.puerto),mod.Handler)
try: server.serve_forever()
except KeyboardInterrupt: pass
finally: server.server_close()
