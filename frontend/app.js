(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const INTERVALO_MS = 5000;
  const TODOS = 'Todos';

  // Color del punto según el estado del pedido (la clave se compara sin tildes ni mayúsculas).
  const COLOR_ESTADO = {
    'entregado': 'ok',
    'en ruta': 'ruta',
    'pendiente': 'alerta',
    'en preparacion': 'prep',
  };

  const sesion = {
    pedidos: [],
    filtro: TODOS,
    busqueda: '',
    instancias: new Map(),
    sinRespuesta: 0,
    ultimaCorrecta: null,
    consultando: false,
    temporizador: null,
  };

  const clave = (texto) =>
    String(texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  const formatoHora = (fecha) =>
    fecha.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  function nodo(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);
    if (clase) elemento.className = clase;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
  }

  async function actualizar() {
    if (sesion.consultando) return;
    sesion.consultando = true;
    const boton = $('actualizar');
    boton.disabled = true;
    boton.textContent = 'Consultando…';

    const resultado = await NodoRutaApi.consultarPedidos();

    sesion.consultando = false;
    boton.disabled = false;
    boton.textContent = 'Actualizar';

    if (resultado.estado === 'en_linea') {
      sesion.pedidos = resultado.pedidos;
      sesion.ultimaCorrecta = resultado.hora;
      const estados = new Set(sesion.pedidos.map((p) => p.estado));
      if (!estados.has(sesion.filtro)) sesion.filtro = TODOS;
    }
    if (resultado.instancia) {
      sesion.instancias.set(resultado.instancia, (sesion.instancias.get(resultado.instancia) || 0) + 1);
    } else {
      sesion.sinRespuesta += 1;
    }

    pintarEstado(resultado);
    pintarAviso(resultado);
    pintarFiltros();
    pintarTabla(resultado);
    pintarRegistro(resultado);
  }

  function pintarEstado(r) {
    const textos = {
      en_linea: 'En línea',
      error_datos: 'Error de datos',
      sin_respuesta: 'Sin respuesta',
    };
    $('servicio').className = 'servicio ' + (r.estado === 'en_linea' ? 'ok' : 'error');
    $('servicio-texto').textContent = textos[r.estado] + (r.http && r.http !== 200 ? ' (' + r.http + ')' : '');
    $('instancia').textContent = r.instancia || '—';
    $('version').textContent = r.version || (r.estado === 'en_linea' ? 'sin versión' : '—');
    $('hora').textContent = formatoHora(r.hora);
    $('tiempo').textContent = r.ms + ' ms';
  }

  function pintarAviso(r) {
    const aviso = $('aviso');
    aviso.replaceChildren();
    if (r.estado === 'en_linea') {
      aviso.hidden = true;
      return;
    }
    if (r.estado === 'error_datos') {
      aviso.append(
        nodo('strong', '', 'La instancia ' + (r.instancia || 'desconocida') + ' respondió, pero no pudo leer los datos.'),
        nodo('p', '', 'Revisen el archivo de datos o restauren un respaldo. Las demás instancias leen el mismo archivo.')
      );
    } else {
      aviso.append(
        nodo('strong', '', 'El servicio no responde.'),
        nodo('p', '', 'No hubo respuesta válida de la API: ' + r.detalle + '. Comprueben que el backend esté levantado.')
      );
    }
    aviso.hidden = false;
  }

  function pintarFiltros() {
    const conteo = new Map([[TODOS, sesion.pedidos.length]]);
    sesion.pedidos.forEach((p) => conteo.set(p.estado, (conteo.get(p.estado) || 0) + 1));

    const filtros = $('filtros');
    filtros.replaceChildren();
    if (!sesion.pedidos.length) return;
    conteo.forEach((cantidad, estado) => {
      const boton = nodo('button', '', estado + ' ' + cantidad);
      boton.type = 'button';
      boton.setAttribute('aria-pressed', String(estado === sesion.filtro));
      boton.addEventListener('click', () => {
        sesion.filtro = estado;
        pintarFiltros();
        pintarTabla();
        filtros.querySelector('[aria-pressed="true"]').focus();
      });
      filtros.append(boton);
    });
  }

  function pintarTabla(r) {
    const busqueda = clave(sesion.busqueda);
    const visibles = sesion.pedidos.filter(
      (p) =>
        (sesion.filtro === TODOS || p.estado === sesion.filtro) &&
        (!busqueda || clave(p.id).includes(busqueda) || clave(p.zona).includes(busqueda))
    );

    const filas = visibles.map((p) => {
      const fila = document.createElement('tr');
      const estado = nodo('span', 'estado-pedido');
      estado.append(nodo('span', 'punto ' + (COLOR_ESTADO[clave(p.estado)] || '')), nodo('span', '', p.estado));
      const celdaEstado = nodo('td');
      celdaEstado.append(estado);
      fila.append(nodo('td', '', p.id), nodo('td', '', p.zona), celdaEstado);
      return fila;
    });
    $('filas').replaceChildren(...filas);
    $('vacio').hidden = visibles.length > 0 || sesion.pedidos.length === 0;

    // Solo se reescribe la leyenda cuando llega una consulta nueva; filtrar no la cambia.
    if (!r) return;
    const leyenda = $('leyenda');
    if (r.estado === 'en_linea') {
      leyenda.className = '';
      leyenda.textContent = sesion.pedidos.length + ' pedidos · consulta de las ' + formatoHora(r.hora);
    } else if (sesion.ultimaCorrecta) {
      leyenda.className = 'desactualizada';
      leyenda.textContent = 'Mostrando la última consulta correcta, de las ' + formatoHora(sesion.ultimaCorrecta);
    } else {
      leyenda.className = 'desactualizada';
      leyenda.textContent = 'Sin datos: todavía no hay una consulta correcta';
    }
  }

  function pintarRegistro(r) {
    const partes = [];
    sesion.instancias.forEach((veces, instancia) => {
      partes.push(instancia + ' · ' + veces + (veces === 1 ? ' consulta' : ' consultas'));
    });
    if (sesion.sinRespuesta) partes.push('sin respuesta · ' + sesion.sinRespuesta);
    $('instancias').textContent = partes.join('   ') || '—';
    $('traza').textContent = r.traza || '—';
  }

  function alternarAutomatico(activo) {
    clearInterval(sesion.temporizador);
    sesion.temporizador = activo ? setInterval(actualizar, INTERVALO_MS) : null;
  }

  $('api').textContent = NodoRutaApi.base;
  $('actualizar').addEventListener('click', actualizar);
  $('auto').addEventListener('change', (evento) => alternarAutomatico(evento.target.checked));
  $('buscar').addEventListener('input', (evento) => {
    sesion.busqueda = evento.target.value;
    pintarTabla();
  });

  actualizar();
})();
