# Frontend · Nodo Ruta

Página para consultar las entregas y ver el estado del servicio. Es HTML, CSS y JavaScript, sin dependencias ni compilación. Solo necesita Python 3.

## 1. Levantarlo

Con el backend corriendo (por defecto en `http://127.0.0.1:8080`):

```powershell
python frontend/servidor.py
```

Abrir <http://127.0.0.1:3000>. En Windows, si `python` no existe, usar `py`.

Si el backend está en otra dirección:

```powershell
python frontend/servidor.py --api http://127.0.0.1:8080
```

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
