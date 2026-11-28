# Frontend · Nodo Ruta

Página para consultar las entregas y ver el estado del servicio. Es HTML, CSS y JavaScript, sin dependencias ni compilación. Solo necesita Python 3.

## 1. Levantarlo

**Todo con un comando**, desde la carpeta del proyecto:

```powershell
python iniciar.py
```

En Mac/Linux también sirve `make iniciar`. Levanta el backend (`8080`) y el frontend (`3000`) y abre el navegador. La primera vez crea `.venv`, instala dependencias y prepara `data/pedidos.json`. `Ctrl+C` detiene todo. En Windows, si `python` no existe, usar `py`.

**Por separado**, si se necesita: dos terminales de PowerShell en la carpeta del proyecto.

Terminal 1, backend en el puerto 8080. Solo la primera vez:

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```powershell
.venv\Scripts\python.exe scripts\datos.py preparar
```

Después, cada vez:

```powershell
.venv\Scripts\python.exe scripts\ejecutar_local.py --puerto 8080 --id local-1
```

Terminal 2, frontend en el puerto 3000:

```powershell
python frontend\servidor.py
```

Abrir <http://127.0.0.1:3000>.

## Puertos

| Puerto | Qué es | Cómo cambiarlo |
| --- | --- | --- |
| `8080` | Backend, o NGINX si se usa Docker Compose | `python iniciar.py --puerto-api 8081`. Por separado: `--puerto 8081` en el backend y `--api http://127.0.0.1:8081` en el frontend |
| `3000` | Frontend | `python iniciar.py --puerto-web 3001`. Por separado: `python frontend\servidor.py --puerto 3001` |

- Con Docker Compose (`make compose-up`), NGINX también queda en el `8080`. El frontend se conecta sin cambios y muestra si respondió `instancia-1` o `instancia-2`. Como comparten puerto, no se puede usar `iniciar.py` a la vez: levanten solo el frontend con `python frontend/servidor.py`.
- Los dos servidores solo escuchan en `127.0.0.1`, así que solo abren en el mismo PC. No hace falta abrir puertos en el firewall.
- Si sale el error de puerto en uso (`WinError 10048`), otro programa ya usa ese puerto. Se cierra la otra terminal o se cambia el puerto como dice la tabla.

## 2. Conectarlo a otro backend

Solo se toca [`api.js`](api.js):

- **`API_BASE`**: se deja en `/api` (usa `servidor.py`) o se pone la URL completa del backend si ese backend permite CORS.
- **`normalizarPedido`**: si los campos cambian de nombre, aquí se traducen a `id`, `zona` y `estado`.

La página espera esta respuesta:

```text
GET /pedidos  ->  200  { "instancia": "app1", "version": "datos-v1", "pedidos": [ { "id": "PED-001", "zona": "Norte", "estado": "En ruta" } ] }
GET /pedidos  ->  503  { "estado": "error_datos", "instancia": "app1" }
```

La cabecera `X-Trace-Id` es opcional. Si llega, se muestra para buscar la traza en Logfire.

## Archivos

| Archivo | Qué hace |
| --- | --- |
| `index.html` | Estructura de la página |
| `estilos.css` | Estilos |
| `app.js` | Estado del servicio, filtros, búsqueda y tabla |
| `api.js` | Conexión con la API (lo único que cambia con otro backend) |
| `servidor.py` | Sirve la página y reenvía `/api/*` al backend, así no hace falta CORS |
