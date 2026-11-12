#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_paths.py
Módulo de detección automática de rutas del sistema de archivos.

Este módulo garantiza que el Sistema Integral de Gestión Municipal (SIGEM)
funcione correctamente en CUALQUIER computadora, sin necesidad de cambios
manuales en las rutas, ya sea ejecutado como script de Python o como
ejecutable empaquetado (PyInstaller).

Uso:
    from config_paths import obtener_ruta_escritorio, obtener_ruta_base_app

    directorio_reporte = os.path.join(obtener_ruta_escritorio(), "Expediente_Auditoria_SIGMA")
"""

import os
import sys


def obtener_ruta_base_app():
    """
    Detecta la ruta base de la aplicación, ya sea ejecutándose como script
    de Python normal o como ejecutable empaquetado con PyInstaller.

    Cuando PyInstaller empaqueta la aplicación en modo --onefile, los
    archivos temporales se extraen a sys._MEIPASS. En modo --onedir o al
    ejecutarse como script normal, se usa la ruta del propio archivo.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Ejecutable PyInstaller (modo --onefile)
        return sys._MEIPASS
    elif getattr(sys, 'frozen', False):
        # Ejecutable PyInstaller (modo --onedir) u otro empaquetador
        return os.path.dirname(sys.executable)
    else:
        # Ejecución normal como script de Python
        return os.path.dirname(os.path.abspath(__file__))


def obtener_ruta_escritorio():
    """
    Devuelve la ruta al escritorio del usuario actual, sin importar el
    sistema operativo o el nombre de usuario. Funciona en Windows, macOS
    y Linux gracias a os.path.expanduser("~").
    """
    escritorio = os.path.join(os.path.expanduser("~"), "Desktop")

    # En algunos sistemas en español, la carpeta puede llamarse "Escritorio"
    if not os.path.exists(escritorio):
        escritorio_alt = os.path.join(os.path.expanduser("~"), "Escritorio")
        if os.path.exists(escritorio_alt):
            escritorio = escritorio_alt

    return escritorio


def obtener_ruta_persistente():
    """
    Devuelve la carpeta donde deben guardarse los datos PERSISTENTES del
    sistema (base de datos, uploads, logs, backups).

    IMPORTANTE: Cuando la aplicación corre como ejecutable PyInstaller
    en modo --onefile, sys._MEIPASS apunta a una carpeta TEMPORAL que se
    borra al cerrar el programa. Si la base de datos se guardara ahí,
    se perdería toda la información cada vez que se cierre el .exe.

    Por eso, para datos persistentes SIEMPRE se usa la carpeta donde
    físicamente reside el archivo .exe (no la carpeta temporal de
    extracción), garantizando que la información sobreviva entre
    ejecuciones.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def obtener_ruta_expedientes():

    """
    Devuelve (y crea si no existe) la carpeta de expedientes de auditoría
    en el escritorio del usuario actual. Ruta 100% portable.

    Funciona igual ejecutándose como script de Python o como ejecutable
    compilado con PyInstaller (--onefile), ya que siempre resuelve la
    ruta real del Escritorio del usuario del sistema operativo, nunca
    una ruta relativa al .exe.
    """
    ruta = os.path.join(obtener_ruta_escritorio(), "Expedientes_SIGMA")
    os.makedirs(ruta, exist_ok=True)
    return ruta



def obtener_ruta_base_datos():
    """
    Devuelve la ruta a la carpeta 'database' dentro de la instalación
    del sistema. Funciona tanto en desarrollo como en el ejecutable.

    Usa obtener_ruta_persistente() (carpeta del .exe) y NO
    obtener_ruta_base_app() (que en modo --onefile sería la carpeta
    temporal _MEIPASS que se borra al cerrar el programa).

    SOPORTE DE RUTA CENTRALIZADA (MULTI-PC): si existe la variable de
    entorno SIGEM_DB_FOLDER, se usa esa ruta en su lugar. Esto permite
    que varias computadoras de la misma área (ej. en una carpeta de red
    compartida o una unidad mapeada) apunten al MISMO archivo
    database/apoyos.db, evitando el escenario típico de "en mi PC sí se
    ven los registros y en la otra PC se ven en ceros" (cada equipo
    tenía su propio archivo SQLite local independiente). Si la ruta no
    existe o no es accesible (ej. la unidad de red está desconectada),
    se crea/usa normalmente la ruta local persistente, para que el
    sistema NUNCA deje de arrancar por un recurso de red caído.
    """
    ruta_centralizada = os.environ.get("SIGEM_DB_FOLDER", "").strip()
    if ruta_centralizada:
        try:
            os.makedirs(ruta_centralizada, exist_ok=True)
            return ruta_centralizada
        except Exception:
            # Recurso de red/ruta inaccesible: se recurre a la ruta local
            # persistente para que el sistema jamás deje de arrancar.
            pass

    ruta = os.path.join(obtener_ruta_persistente(), "database")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def obtener_ruta_uploads():
    """
    Devuelve la ruta a la carpeta de archivos subidos (static/uploads).
    Usa la ruta persistente para que los archivos no se pierdan al
    cerrar el ejecutable.
    """
    ruta = os.path.join(obtener_ruta_persistente(), "static", "uploads")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def obtener_ruta_logs():
    """
    Devuelve la ruta a la carpeta de logs del sistema.
    Usa la ruta persistente para que los logs no se pierdan al cerrar
    el ejecutable.
    """
    ruta = os.path.join(obtener_ruta_persistente(), "logs")
    os.makedirs(ruta, exist_ok=True)
    return ruta



if __name__ == "__main__":
    # Prueba rápida de diagnóstico de rutas
    print("=== DIAGNÓSTICO DE RUTAS PORTABLES (SIGEM) ===")
    print(f"Ruta base de la app:      {obtener_ruta_base_app()}")
    print(f"Ruta del escritorio:      {obtener_ruta_escritorio()}")
    print(f"Ruta de expedientes:      {obtener_ruta_expedientes()}")
    print(f"Ruta de base de datos:    {obtener_ruta_base_datos()}")
    print(f"Ruta de uploads:          {obtener_ruta_uploads()}")
    print(f"Ruta de logs:             {obtener_ruta_logs()}")
