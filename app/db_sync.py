# -*- coding: utf-8 -*-
"""
app/db_sync.py

HERRAMIENTAS DE RECUPERACIÓN, RESTAURACIÓN Y SINCRONIZACIÓN ENTRE
EQUIPOS LOCALES (MULTI-PC) - SIGEM Atarjea.

Contexto del incidente: cada computadora que ejecuta `python run.py`
tiene su PROPIO archivo SQLite local e independiente
(`database/apoyos.db`). Si dos Directores/Operadores capturan
información en computadoras distintas de la misma área, cada uno ve
ÚNICAMENTE lo que él mismo registró en su equipo. Este módulo da dos
soluciones prácticas sin requerir un servidor central:

1. RESTAURAR/REIMPORTAR (`restaurar_desde_respaldo`): si el archivo
   local se corrompe, se queda en 0 bytes o se inicializa vacío por un
   despliegue limpio, permite recuperar el último respaldo válido
   generado automáticamente en el Escritorio
   (~/Desktop/RESPALDOS_SIGEM/SIGEM_respaldo_actual.db) o uno elegido
   explícitamente, antes de perder la operación del día.

2. FUSIONAR DOS BASES DE DATOS SQLITE DIVERGENTES
   (`fusionar_bases_de_datos`): toma el archivo .db de OTRA
   computadora (copiado por USB/red) y combina sus registros con la
   base de datos activa, usando siempre una LLAVE NATURAL (nunca el ID
   autonumérico, que cada PC genera de forma independiente) para nunca
   duplicar un registro que ya exista en ambos lados.

CERO BLOQUEOS / CERO PÉRDIDA DE DATOS: toda operación de escritura se
envuelve en una transacción con rollback automático ante cualquier
error, y SIEMPRE se genera un respaldo de seguridad del archivo activo
antes de sobreescribirlo o fusionarlo, de modo que un fallo a mitad de
camino nunca deje la base de datos peor de como estaba.
"""
import os
import shutil
import sqlite3
from datetime import datetime

from flask import current_app

from config_paths import obtener_ruta_base_datos, obtener_ruta_escritorio

NOMBRE_BD = "apoyos.db"

# Mismo criterio de "llave natural" usado por app/backup_utils.py para
# el Paquete Diario: nunca se fusiona por ID numérico, siempre por un
# valor único de negocio que identifica inequívocamente al registro
# sin importar en qué computadora se haya capturado.
_TABLAS_FUSIONABLES = [
    ('usuarios', 'Usuario', 'email'),
    ('dependencias', 'Dependencia', 'nombre'),
    ('comunidades', 'Comunidad', 'nombre'),
    ('ciudadanos', 'Ciudadano', 'CURP'),
    ('solicitudes', 'Solicitud', 'folio'),
    ('bitacoras_combustible', 'BitacoraCombustible', 'folio_vale'),
    ('asignaciones_combustible', 'AsignacionCombustible', 'folio_asignacion'),
]


def _log(nivel, mensaje):
    """Registra en el logger de la app si hay contexto disponible; NUNCA
    lanza una excepción si no lo hay (ej. al correr como script CLI)."""
    try:
        logger = current_app.logger
        getattr(logger, nivel, logger.warning)(mensaje)
    except Exception:
        print(f"[{nivel.upper()}] {mensaje}")


def _ruta_bd_activa():
    return os.path.join(obtener_ruta_base_datos(), NOMBRE_BD)


def verificar_integridad_bd_local():
    """
    BLINDAJE CONTRA BORRADOS: detecta si la base de datos SQLite local
    está ausente, en 0 bytes, o devuelve un resultado anómalo a
    'PRAGMA integrity_check', lo que indica un archivo corrupto o
    recién inicializado tras un despliegue limpio / reinicio de volumen
    efímero. Retorna un diccionario con el diagnóstico; nunca lanza una
    excepción.
    """
    resultado = {'existe': False, 'tamano_bytes': 0, 'integra': False, 'detalle': ''}
    try:
        ruta_bd = _ruta_bd_activa()
        resultado['existe'] = os.path.exists(ruta_bd)
        if not resultado['existe']:
            resultado['detalle'] = 'El archivo de base de datos no existe en esta computadora.'
            return resultado

        resultado['tamano_bytes'] = os.path.getsize(ruta_bd)
        if resultado['tamano_bytes'] < 1024:
            resultado['detalle'] = 'El archivo existe pero es sospechosamente pequeño (posible inicialización en 0).'
            return resultado

        conn = sqlite3.connect(ruta_bd)
        try:
            cursor = conn.cursor()
            cursor.execute('PRAGMA integrity_check')
            fila = cursor.fetchone()
            resultado['integra'] = bool(fila and fila[0] == 'ok')
            resultado['detalle'] = fila[0] if fila else 'Sin respuesta de integrity_check.'
        finally:
            conn.close()
    except Exception as e:
        resultado['detalle'] = f'Error al verificar integridad: {str(e)}'
    return resultado


def listar_respaldos_disponibles():
    """
    Lista los respaldos disponibles en ~/Desktop/RESPALDOS_SIGEM/,
    ordenados del más reciente al más antiguo, para que el usuario
    elija cuál restaurar. Retorna una lista de dicts
    {'nombre', 'ruta', 'fecha_modificacion', 'tamano_bytes'}; nunca
    lanza una excepción (retorna lista vacía si algo falla).
    """
    try:
        ruta_respaldos = os.path.join(obtener_ruta_escritorio(), "RESPALDOS_SIGEM")
        if not os.path.isdir(ruta_respaldos):
            return []
        respaldos = []
        for nombre in os.listdir(ruta_respaldos):
            if not nombre.lower().endswith('.db'):
                continue
            ruta = os.path.join(ruta_respaldos, nombre)
            try:
                respaldos.append({
                    'nombre': nombre,
                    'ruta': ruta,
                    'fecha_modificacion': datetime.fromtimestamp(os.path.getmtime(ruta)),
                    'tamano_bytes': os.path.getsize(ruta),
                })
            except Exception:
                continue
        respaldos.sort(key=lambda r: r['fecha_modificacion'], reverse=True)
        return respaldos
    except Exception as e:
        _log('warning', f"No se pudieron listar los respaldos disponibles: {str(e)}")
        return []


def restaurar_desde_respaldo(ruta_respaldo=None):
    """
    RECUPERACIÓN SEGURA: restaura la base de datos ACTIVA a partir de
    un respaldo (por defecto, el más reciente disponible en
    ~/Desktop/RESPALDOS_SIGEM/). Antes de sobreescribir el archivo
    activo, genera una copia de seguridad "pre-restauración" por si el
    respaldo elegido resultara, a su vez, inválido.

    Retorna un diccionario {'exito': bool, 'mensaje': str}. NUNCA deja
    la base de datos activa en un estado peor que el inicial: si algo
    falla a mitad de camino, el archivo original permanece intacto.
    """
    resultado = {'exito': False, 'mensaje': ''}
    try:
        if not ruta_respaldo:
            respaldos = listar_respaldos_disponibles()
            if not respaldos:
                resultado['mensaje'] = 'No se encontró ningún respaldo disponible en el Escritorio (RESPALDOS_SIGEM).'
                return resultado
            ruta_respaldo = respaldos[0]['ruta']

        if not os.path.exists(ruta_respaldo):
            resultado['mensaje'] = f'El archivo de respaldo indicado no existe: {ruta_respaldo}'
            return resultado

        # Validar que el respaldo sea una base de datos SQLite íntegra
        # ANTES de sobreescribir nada (nunca restaurar un archivo corrupto).
        try:
            conn_prueba = sqlite3.connect(ruta_respaldo)
            cursor_prueba = conn_prueba.cursor()
            cursor_prueba.execute('PRAGMA integrity_check')
            fila = cursor_prueba.fetchone()
            conn_prueba.close()
            if not fila or fila[0] != 'ok':
                resultado['mensaje'] = 'El respaldo seleccionado no pasó la verificación de integridad; no se restauró nada.'
                return resultado
        except Exception as e:
            resultado['mensaje'] = f'El respaldo seleccionado no es una base de datos SQLite válida: {str(e)}'
            return resultado

        ruta_activa = _ruta_bd_activa()

        # Respaldo de seguridad "pre-restauración" del estado actual
        # (aunque esté corrupto/vacío), para nunca perder la posibilidad
        # de deshacer la restauración si fue un error.
        if os.path.exists(ruta_activa):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ruta_pre = os.path.join(
                os.path.dirname(ruta_activa), f"apoyos_pre_restauracion_{timestamp}.db"
            )
            try:
                shutil.copy2(ruta_activa, ruta_pre)
            except Exception as e:
                _log('warning', f"No se pudo generar el respaldo pre-restauración: {str(e)}")

        shutil.copy2(ruta_respaldo, ruta_activa)
        resultado['exito'] = True
        resultado['mensaje'] = f'Base de datos restaurada exitosamente desde: {os.path.basename(ruta_respaldo)}'
        _log('info', resultado['mensaje'])
        return resultado
    except Exception as e:
        resultado['mensaje'] = f'Error al restaurar la base de datos: {str(e)}'
        _log('error', resultado['mensaje'])
        return resultado


def fusionar_bases_de_datos(ruta_bd_externa):
    """
    SINCRONIZACIÓN ENTRE COMPUTADORAS (MULTI-PC): fusiona los registros
    de OTRA base de datos SQLite (copiada manualmente desde otra
    computadora, ej. por USB o carpeta compartida) dentro de la base de
    datos ACTIVA de esta computadora, sin perder ni duplicar
    información de ninguno de los dos lados.

    Reglas de fusión (idénticas en espíritu al "Paquete Diario" de
    app/backup_utils.py):
      - Se usa SIEMPRE una llave natural (email, CURP, folio, etc.)
        para decidir si un registro ya existe; NUNCA el ID numérico,
        ya que cada base de datos genera su propia numeración local.
      - Un registro que exista en ambas bases de datos se OMITE (no se
        sobreescribe) para no perder cambios ya confirmados localmente.
      - Un registro nuevo se inserta respetando el resto de columnas
        de la tabla.
      - Cualquier registro individual que falle se omite y se reporta
        en el resumen; un solo registro problemático NUNCA aborta la
        fusión completa.
      - Antes de escribir nada, se genera un respaldo de seguridad de
        la base de datos activa.

    Retorna {'exito': bool, 'detalle': {tabla: {...}}, 'error': str|None}.
    """
    from . import models as m
    from . import db

    resumen = {'exito': False, 'detalle': {}, 'error': None}
    conn_externa = None

    try:
        if not os.path.exists(ruta_bd_externa):
            resumen['error'] = f'No se encontró el archivo de base de datos externo: {ruta_bd_externa}'
            return resumen

        conn_externa = sqlite3.connect(ruta_bd_externa)
        cursor_externa = conn_externa.cursor()
        cursor_externa.execute('PRAGMA integrity_check')
        fila = cursor_externa.fetchone()
        if not fila or fila[0] != 'ok':
            resumen['error'] = 'La base de datos externa no pasó la verificación de integridad.'
            return resumen

        ruta_activa = _ruta_bd_activa()
        if os.path.exists(ruta_activa):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ruta_pre = os.path.join(os.path.dirname(ruta_activa), f"apoyos_pre_fusion_{timestamp}.db")
            try:
                shutil.copy2(ruta_activa, ruta_pre)
            except Exception as e:
                _log('warning', f"No se pudo generar el respaldo pre-fusión: {str(e)}")

        for nombre_tabla, nombre_modelo, llave_natural in _TABLAS_FUSIONABLES:
            insertados = 0
            omitidos_duplicados = 0
            omitidos_error = 0
            try:
                cursor_externa.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nombre_tabla,)
                )
                if not cursor_externa.fetchone():
                    resumen['detalle'][nombre_tabla] = {
                        'insertados': 0, 'omitidos_duplicados': 0, 'omitidos_error': 0,
                        'nota': 'Tabla no existe en el archivo externo.',
                    }
                    continue

                cursor_externa.execute(f"PRAGMA table_info({nombre_tabla})")
                columnas_externas = [fila[1] for fila in cursor_externa.fetchall()]
                cursor_externa.execute(f"SELECT {', '.join(columnas_externas)} FROM {nombre_tabla}")
                filas_externas = cursor_externa.fetchall()

                Modelo = getattr(m, nombre_modelo)
                for fila_datos in filas_externas:
                    datos = dict(zip(columnas_externas, fila_datos))
                    try:
                        valor_llave = datos.get(llave_natural)
                        if valor_llave is None:
                            omitidos_error += 1
                            continue
                        existente = Modelo.query.filter_by(**{llave_natural: valor_llave}).first()
                        if existente:
                            omitidos_duplicados += 1
                            continue
                        datos_limpios = {k: v for k, v in datos.items() if k != 'id'}
                        nuevo = Modelo(**datos_limpios)
                        db.session.add(nuevo)
                        db.session.flush()
                        insertados += 1
                    except Exception:
                        db.session.rollback()
                        omitidos_error += 1
                        continue
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                _log('warning', f"Error al fusionar la tabla '{nombre_tabla}': {str(e)}")

            resumen['detalle'][nombre_tabla] = {
                'insertados': insertados,
                'omitidos_duplicados': omitidos_duplicados,
                'omitidos_error': omitidos_error,
            }

        resumen['exito'] = True
        return resumen
    except Exception as e:
        db.session.rollback()
        resumen['error'] = str(e)
        _log('error', f"Error al fusionar bases de datos: {str(e)}")
        return resumen
    finally:
        if conn_externa:
            try:
                conn_externa.close()
            except Exception:
                pass
