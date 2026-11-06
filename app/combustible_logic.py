# -*- coding: utf-8 -*-
"""
Lógica PURA de evaluación de alertas del Módulo de Servicios Públicos
(Control de Combustible), Municipio de Atarjea, Guanajuato.

PRINCIPIO RECTOR: esta función NUNCA bloquea el guardado de un registro.
Solo devuelve una lista de alertas (semáforo) en español simple para que
el Alcalde y la Encargada de Servicios Públicos las revisen.

Esta función es deliberadamente PURA (no importa Flask, SQLAlchemy ni
accede a la base de datos) para poder probarse con pruebas unitarias
sencillas y rápidas. Toda la información que necesita del "mundo real"
(medianas, promedios, fechas de la última carga, etc.) se le entrega ya
calculada en el diccionario `contexto`.
"""

ROJO = 'rojo'
AMARILLO = 'amarillo'


def _agregar(alertas, color, mensaje):
    alertas.append({'color': color, 'mensaje': mensaje})


def obtener_umbrales_default():
    """Umbrales por defecto usados cuando no existe una Configuracion personalizada."""
    return {
        'rendimiento_pct_bajo_mediana': 30,
        'cargas_aprendizaje_minimas': 5,
        'dias_min_entre_cargas': 2,
        'pct_precio_fuera_promedio': 40,
        'dias_ciudadano_apoyo_previo': 30,
        'dias_sin_foto_tablero': 30,
        'capacidad_contenedor_litros': 1000,
    }


def _a_float(valor):
    """Convierte de forma segura a float; retorna None si no es posible."""
    if valor is None or valor == '':
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _calcular_rendimiento_actual(tipo_bitacora, km_anterior, km_actual, horometro_anterior, horometro_actual, litros):
    """Calcula el rendimiento del registro actual (km/L o L/h) para comparar contra la mediana."""
    try:
        if not litros or litros <= 0:
            return None
        if tipo_bitacora == 'MAQUINARIA':
            if horometro_anterior is not None and horometro_actual is not None:
                horas = horometro_actual - horometro_anterior
                if horas > 0:
                    return litros / horas  # L/h
        else:
            if km_anterior is not None and km_actual is not None:
                km_recorridos = km_actual - km_anterior
                if km_recorridos > 0:
                    return km_recorridos / litros  # km/L
    except Exception:
        return None
    return None


def evaluar_registro(reg, contexto=None):
    """
    Evalúa un registro de combustible y devuelve una lista de alertas.
    NUNCA bloquea el guardado; solo informa en español simple.

    Args:
        reg: dict con los datos del registro (ver claves usadas abajo).
        contexto: dict con datos agregados ya calculados por el llamador
            (folio_repetido, mediana_rendimiento_unidad, cargas_previas_unidad,
            dias_desde_ultima_carga_unidad, promedio_precio_litro,
            dias_desde_ultimo_apoyo_ciudadano, dias_desde_ultima_foto_tablero,
            umbrales).

    Returns:
        list[dict]: [{'color': 'rojo'|'amarillo', 'mensaje': str}, ...]
    """
    reg = reg or {}
    contexto = contexto or {}
    umbrales = contexto.get('umbrales') or obtener_umbrales_default()

    alertas = []

    tipo_bitacora = (reg.get('tipo_bitacora') or '').upper()
    litros = _a_float(reg.get('litros'))
    km_anterior = _a_float(reg.get('km_anterior'))
    km_actual = _a_float(reg.get('km_actual'))
    horometro_anterior = _a_float(reg.get('horometro_anterior'))
    horometro_actual = _a_float(reg.get('horometro_actual'))
    capacidad_tanque = _a_float(reg.get('capacidad_tanque'))
    tanque_lleno = bool(reg.get('tanque_lleno'))
    foto_vale = reg.get('foto_vale')
    folio_vale = (reg.get('folio_vale') or '').strip()
    tiene_factura = (reg.get('tiene_factura') or '').upper()

    # ---------------- REGLAS ROJAS (nunca bloquean) ----------------

    if km_anterior is not None and km_actual is not None and km_actual < km_anterior:
        _agregar(alertas, ROJO, 'El kilómetro actual no puede ser menor al kilómetro anterior registrado.')

    if horometro_anterior is not None and horometro_actual is not None and horometro_actual < horometro_anterior:
        _agregar(alertas, ROJO, 'El horómetro actual no puede ser menor al horómetro anterior registrado.')

    if (km_anterior is not None and km_actual is not None
            and km_actual == km_anterior and litros and litros > 0):
        _agregar(alertas, ROJO, 'El kilómetro no cambió desde la última carga, pero se está registrando combustible nuevo.')

    if capacidad_tanque and litros and litros > capacidad_tanque:
        _agregar(alertas, ROJO, f'Los litros cargados ({litros:g} L) superan la capacidad del tanque ({capacidad_tanque:g} L).')

    if not foto_vale:
        _agregar(alertas, ROJO, 'Falta la fotografía del vale de combustible.')

    if tipo_bitacora == 'FORANEA' and tiene_factura in ('', 'NINGUNO'):
        _agregar(alertas, ROJO, 'Falta el ticket o la factura de la gasolinera para esta carga foránea.')

    if not folio_vale:
        _agregar(alertas, ROJO, 'El folio del vale no fue capturado.')
    elif contexto.get('folio_repetido'):
        _agregar(alertas, ROJO, f'El folio "{folio_vale}" ya fue utilizado en otro registro activo.')

    # --------------- REGLAS AMARILLAS (nunca bloquean) ---------------

    mediana_rendimiento = contexto.get('mediana_rendimiento_unidad')
    cargas_previas = contexto.get('cargas_previas_unidad') or 0
    cargas_aprendizaje_minimas = umbrales.get('cargas_aprendizaje_minimas', 5)
    pct_bajo_mediana = umbrales.get('rendimiento_pct_bajo_mediana', 30)

    if (tanque_lleno and mediana_rendimiento and mediana_rendimiento > 0
            and cargas_previas >= cargas_aprendizaje_minimas):
        rendimiento_actual = _calcular_rendimiento_actual(
            tipo_bitacora, km_anterior, km_actual, horometro_anterior, horometro_actual, litros
        )
        if rendimiento_actual is not None:
            limite_inferior = mediana_rendimiento * (1 - pct_bajo_mediana / 100.0)
            if rendimiento_actual < limite_inferior:
                _agregar(alertas, AMARILLO, 'El rendimiento de esta unidad es mucho menor al habitual; conviene revisarla.')

    dias_min_entre_cargas = umbrales.get('dias_min_entre_cargas', 2)
    dias_desde_ultima_carga = contexto.get('dias_desde_ultima_carga_unidad')
    if dias_desde_ultima_carga is not None and dias_desde_ultima_carga < dias_min_entre_cargas:
        _agregar(alertas, AMARILLO, f'Esta unidad ya cargó combustible hace {dias_desde_ultima_carga} día(s); verifique que no sea un registro duplicado.')

    precio_por_litro = _a_float(reg.get('precio_por_litro'))
    promedio_precio = contexto.get('promedio_precio_litro')
    pct_fuera_promedio = umbrales.get('pct_precio_fuera_promedio', 40)
    if precio_por_litro and promedio_precio and promedio_precio > 0:
        desviacion_pct = abs(precio_por_litro - promedio_precio) / promedio_precio * 100.0
        if desviacion_pct > pct_fuera_promedio:
            _agregar(alertas, AMARILLO, 'El precio por litro está muy alejado del precio promedio habitual; verifique el ticket o factura.')

    dias_apoyo_min = umbrales.get('dias_ciudadano_apoyo_previo', 30)
    dias_desde_apoyo = contexto.get('dias_desde_ultimo_apoyo_ciudadano')
    if tipo_bitacora == 'CIUDADANO' and dias_desde_apoyo is not None and dias_desde_apoyo < dias_apoyo_min:
        _agregar(alertas, AMARILLO, f'Este beneficiario ya recibió apoyo de combustible hace {dias_desde_apoyo} día(s).')

    dias_max_sin_foto = umbrales.get('dias_sin_foto_tablero', 30)
    dias_sin_foto = contexto.get('dias_desde_ultima_foto_tablero')
    if dias_sin_foto is not None and dias_sin_foto > dias_max_sin_foto:
        _agregar(alertas, AMARILLO, f'Han pasado más de {dias_max_sin_foto} días sin registrar una foto del tablero/odómetro de esta unidad.')

    return alertas
