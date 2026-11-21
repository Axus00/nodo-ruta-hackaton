/*
 * Conexión con la API de Nodo Ruta.
 *
 * Es el único archivo que hay que tocar cuando cambie el backend (por ejemplo, al pasar a PostgreSQL):
 *   - API_BASE: dónde está la API. '/api' usa el proxy de servidor.py. Una URL completa
 *     (https://...) también sirve si ese backend permite CORS.
 *   - normalizarPedido: traduce los campos que devuelva el backend a { id, zona, estado }.
 *
 * Contrato que se usa hoy:
 *   GET /pedidos -> 200 { instancia, version, pedidos: [{ id, zona, estado }] } y cabecera X-Trace-Id
 *                -> 503 { estado: "error_datos", instancia } si la instancia no puede leer los datos
 */
window.NodoRutaApi = (function () {
  'use strict';

  const API_BASE = '/api';
  const ESPERA_MAXIMA_MS = 8000;

  function normalizarPedido(pedido) {
    return { id: pedido.id, zona: pedido.zona, estado: pedido.estado };
  }

  // Devuelve siempre un objeto con `estado`: 'en_linea', 'error_datos' o 'sin_respuesta'.
  async function consultarPedidos() {
    const hora = new Date();
    const inicio = performance.now();
    const transcurrido = () => Math.round(performance.now() - inicio);

    let respuesta;
    try {
      respuesta = await fetch(API_BASE + '/pedidos', {
        cache: 'no-store',
        signal: AbortSignal.timeout(ESPERA_MAXIMA_MS),
      });
    } catch (error) {
      return { estado: 'sin_respuesta', detalle: 'sin conexión con ' + API_BASE, hora, ms: transcurrido() };
    }

    const ms = transcurrido();
    let cuerpo = null;
    try {
      cuerpo = await respuesta.json();
    } catch (error) {
      // Respuesta que no es JSON, por ejemplo la página de error de un proxy.
    }

    const base = {
      http: respuesta.status,
      hora,
      ms,
      traza: respuesta.headers.get('X-Trace-Id'),
      instancia: cuerpo && cuerpo.instancia,
    };

    if (respuesta.ok && cuerpo && Array.isArray(cuerpo.pedidos)) {
      return { ...base, estado: 'en_linea', version: cuerpo.version, pedidos: cuerpo.pedidos.map(normalizarPedido) };
    }
    if (cuerpo && cuerpo.estado === 'error_datos') {
      return { ...base, estado: 'error_datos' };
    }

    if (cuerpo && cuerpo.error === 'sin_conexion') {
      // El 502 lo produce servidor.py, no la API: no se muestra como código de la API.
      return { ...base, http: undefined, estado: 'sin_respuesta', detalle: 'no se pudo conectar con ' + cuerpo.api };
    }
    const detalle = respuesta.ok ? 'formato de respuesta inesperado' : 'HTTP ' + respuesta.status;
    return { ...base, estado: 'sin_respuesta', detalle };
  }

  return { base: API_BASE, consultarPedidos };
})();
