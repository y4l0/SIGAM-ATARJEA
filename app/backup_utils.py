# -*- coding: utf-8 -*-
"""
app/backup_utils.py

MÓDULO PORTABLE Y RESPALDO AUTOMÁTICO EN ESCRITORIO (ORDEN TÉCNICA
MAESTRA - BLINDAJE DE ROBLE).

SIGEM Atarjea no depende de un servidor central: cada Director o el
Alcalde puede operar el sistema desde su propia computadora con su
propia base de datos SQLite local. Este módulo resuelve dos problemas:

1. RESPALDO AUTOMÁTICO LOCAL: cada vez que se registra o autoriza una
   acción crítica (nueva solicitud, cambio de estatus, vale de
   combustible, asignación, cierre de ejercicio, etc.) se actualiza de
   forma silenciosa una copia de la base de datos en el Escritorio del
   usuario actual (~/Desktop/RESPALDOS_SIGEM/), sin bloquear NUNCA la
   operación que lo originó (si el respaldo falla, solo se registra en
   el log; el usuario jamás ve un error).

2. SINCRONIZACIÓN ASÍNCRONA ENTRE COMPUTADORAS ("Exportar Paquete
   Diario" / "Importar Paquete de Director"): genera y consume un
   archivo .json portable con los datos operativos clave del sistema,
   para que el Alcalde pueda consolidar manualmente (por USB, correo o
   carpeta compartida) la información capturada en las distintas
   computadoras/módems de Atarjea, sin necesidad de una red fija ni de
   un servidor central.

CERO BLOQUEOS: absolutamente ninguna función de este módulo debe
interrumpir el flujo normal del sistema. Todo error se captura,
se registra en el log y la función retorna un valor neutro (None /
False / un diccionario con 'exito': False).
"""
import os
import json
import shutil
from datetime import datetime
from decimal import Decimal

from flask import current_app

from config_paths import obtener_ruta_escritorio, obtener_ruta_base_datos

NOMBRE_CARPETA_RESPALDOS = "RESPALDOS_SIGEM"
NOMBRE_BD = "apoyos.db"


def _log(nivel, mensaje):
    """Registra en el logger de la app si hay contexto disponible; si
    no, simplemente no hace nada. NUNCA lanza una excepción."""
    try:
        logger = current_app.logger
        getattr(logger, nivel, logger.warning)(mensaje)
    except Exception:
        pass


def obtener_ruta_respaldos_escritorio():
    """
    Devuelve (y crea si no existe) la carpeta de respaldos portables en
    el Escritorio del usuario actual: ~/Desktop/RESPALDOS_SIGEM/.
    Funciona igual en desarrollo y en el ejecutable PyInstaller, ya que
    usa config_paths.obtener_ruta_escritorio() (100% portable).
    """
    try:
        ruta = os.path.join(obtener_ruta_escritorio(), NOMBRE_CARPETA_RESPALDOS)
        os.makedirs(ruta, exist_ok=True)
        return ruta
    except Exception as e:
        _log('warning', f"No se pudo preparar la carpeta de respaldos del Escritorio: {str(e)}")
        return None


def respaldar_en_escritorio(motivo=None, usuario_nombre=None):
    """
    ORDEN TÉCNICA MAESTRA - RESPALDO AUTOMÁTICO: copia la base de datos
    SQLite activa hacia ~/Desktop/RESPALDOS_SIGEM/, generando:
      1. Una copia "viva" (siempre la más reciente): SIGEM_respaldo_actual.db
      2. Una copia con fecha DIARIA (una por día, se sobrescribe si ya
         se generó hoy): SIGEM_respaldo_YYYY-MM-DD.db
         Esto evita llenar el disco del usuario tras un año de uso
         diario continuo (máximo 365 copias/año, una por día).

    CERO BLOQUEOS: se ejecuta en segundo plano lógico (nunca lanza una
    excepción hacia la ruta que la invoca); cualquier falla solo se
    registra en el log y la función retorna False.
    """
    try:
        ruta_respaldos = obtener_ruta_respaldos_escritorio()
        if not ruta_respaldos:
            return False

        ruta_bd_origen = os.path.join(obtener_ruta_base_datos(), NOMBRE_BD)
        if not os.path.exists(ruta_bd_origen):
            _log('warning', "Respaldo automático omitido: no se encontró la base de datos activa.")
            return False

        # 1. Copia "viva" (siempre la más reciente)
        ruta_actual = os.path.join(ruta_respaldos, "SIGEM_respaldo_actual.db")
        shutil.copy2(ruta_bd_origen, ruta_actual)

        # 2. Copia diaria (una por día natural)
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        ruta_diaria = os.path.join(ruta_respaldos, f"SIGEM_respaldo_{hoy_str}.db")
        shutil.copy2(ruta_bd_origen, ruta_diaria)

        # Bitácora simple de texto (auditable, no requiere abrir la BD)
        try:
            ruta_log = os.path.join(ruta_respaldos, "bitacora_respaldos.log")
            with open(ruta_log, 'a', encoding='utf-8') as f:
                f.write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"Usuario: {usuario_nombre or 'Sistema'} | "
                    f"Motivo: {motivo or 'Respaldo automático'}\n"
                )
        except Exception:
            pass

        return True
    except Exception as e:
        _log('warning', f"No se pudo generar el respaldo automático en el Escritorio: {str(e)}")
        return False


def _valor_serializable(valor):
    """Convierte tipos no nativos de JSON (Decimal, datetime, date) a
    representaciones seguras. Cualquier tipo desconocido se convierte
    a texto como última instancia, nunca lanza una excepción."""
    try:
        if valor is None or isinstance(valor, (str, int, float, bool)):
            return valor
        if isinstance(valor, Decimal):
            return float(valor)
        if hasattr(valor, 'isoformat'):  # datetime/date/time
            return valor.isoformat()
        return str(valor)
    except Exception:
        return None


def _serializar_modelo(instancia):
    """
    Convierte CUALQUIER instancia de modelo SQLAlchemy a un diccionario
    plano usando introspección de columnas (__table__.columns), sin
    necesidad de mantener un mapeo manual por cada modelo (regla de
    "Cero Redundancia"). Ignora relaciones; solo exporta columnas reales.
    """
    try:
        datos = {}
        for columna in instancia.__table__.columns:
            datos[columna.name] = _valor_serializable(getattr(instancia, columna.name, None))
        return datos
    except Exception:
        return {}


# Tablas incluidas en el Paquete Diario y su llave natural usada para
# evitar duplicados al importar en otra computadora (merge seguro sin
# depender de que los IDs numéricos coincidan entre bases de datos
# independientes).
_TABLAS_PAQUETE_DIARIO = [
    ('usuarios', 'Usuario', 'email'),
    ('dependencias', 'Dependencia', 'nombre'),
    ('comunidades', 'Comunidad', 'nombre'),
    ('ciudadanos', 'Ciudadano', 'CURP'),
    ('solicitudes', 'Solicitud', 'folio'),
    ('bitacoras_combustible', 'BitacoraCombustible', 'folio_vale'),
    ('asignaciones_combustible', 'AsignacionCombustible', 'folio_asignacion'),
]


def generar_paquete_diario_json():
    """
    Genera el "Paquete Diario" (.json) con los datos operativos clave
    del sistema: usuarios, dependencias, comunidades, ciudadanos,
    solicitudes de apoyo y los registros del Módulo de Servicios
    Públicos (combustible). Usado por el botón "Exportar Paquete
    Diario" del Alcalde/Directores para consolidar manualmente la
    información capturada en distintas computadoras sin depender de
    una red fija.

    Retorna una tupla (nombre_archivo, contenido_json_en_texto) o
    (None, None) si algo falla (CERO BLOQUEOS).
    """
    try:
        from . import models as m

        paquete = {
            'version_formato': 1,
            'sistema': 'SIGEM Atarjea',
            'fecha_generacion': datetime.now().isoformat(),
            'tablas': {},
        }

        for nombre_tabla, nombre_modelo, _llave in _TABLAS_PAQUETE_DIARIO:
            try:
                Modelo = getattr(m, nombre_modelo)
                registros = Modelo.query.all()
                paquete['tablas'][nombre_tabla] = [_serializar_modelo(r) for r in registros]
            except Exception as e:
                _log('warning', f"No se pudo incluir la tabla '{nombre_tabla}' en el paquete diario: {str(e)}")
                paquete['tablas'][nombre_tabla] = []

        contenido = json.dumps(paquete, ensure_ascii=False, indent=2)
        nombre_archivo = f"SIGEM_paquete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sigem.json"
        return nombre_archivo, contenido
    except Exception as e:
        _log('error', f"Error al generar el Paquete Diario: {str(e)}")
        return None, None


def importar_paquete_json(contenido_texto):
    """
    Importa un "Paquete de Director" (.sigem.json) generado por
    generar_paquete_diario_json() en OTRA computadora, fusionando los
    datos en la base de datos LOCAL sin duplicar registros ya
    existentes (comparación por llave natural: email, CURP, folio,
    etc., nunca por ID numérico, ya que cada computadora genera sus
    propios IDs de forma independiente).

    CERO BLOQUEOS: cualquier registro individual que falle al
    importarse se omite y se reporta en el resumen; el proceso
    completo nunca se interrumpe por un solo registro problemático.

    Retorna un diccionario con el resumen de la importación:
        {'exito': bool, 'detalle': {...}, 'error': str|None}
    """
    from . import models as m
    from . import db

    resumen = {'exito': False, 'detalle': {}, 'error': None}

    try:
        paquete = json.loads(contenido_texto)
        tablas = paquete.get('tablas', {})

        for nombre_tabla, nombre_modelo, llave_natural in _TABLAS_PAQUETE_DIARIO:
            insertados = 0
            omitidos_duplicados = 0
            omitidos_error = 0

            try:
                Modelo = getattr(m, nombre_modelo)
                registros_entrantes = tablas.get(nombre_tabla, [])

                for datos in registros_entrantes:
                    try:
                        valor_llave = datos.get(llave_natural)
                        if valor_llave is None:
                            omitidos_error += 1
                            continue

                        existente = Modelo.query.filter_by(**{llave_natural: valor_llave}).first()
                        if existente:
                            omitidos_duplicados += 1
                            continue

                        # No se importa el ID original (cada BD maneja
                        # su propia numeración autoincremental local).
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
                _log('warning', f"Error al importar la tabla '{nombre_tabla}': {str(e)}")

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
        _log('error', f"Error al importar el Paquete de Director: {str(e)}")
        return resumen
