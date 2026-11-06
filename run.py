#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sistema Integral de Gestión Municipal - Servidor de Producción
Municipio de Atarjea, Guanajuato
"""
import os
import sys
import logging
import threading
import webbrowser
from app import create_app
from app.logger_config import app_logger
from config_paths import obtener_ruta_persistente, obtener_ruta_base_datos, obtener_ruta_uploads, obtener_ruta_logs


# Crear la instancia de la aplicación
app = create_app()

def verificar_estructura_sistema():
    """Verifica y crea la estructura de directorios del sistema (rutas
    portables: funcionan tanto en desarrollo como en el ejecutable .exe)"""
    base = obtener_ruta_persistente()
    directorios_requeridos = [
        obtener_ruta_base_datos(),
        obtener_ruta_logs(),
        os.path.join(base, 'static', 'img'),
        os.path.join(obtener_ruta_uploads(), 'identificaciones'),
        os.path.join(obtener_ruta_uploads(), 'comprobantes'),
        os.path.join(obtener_ruta_uploads(), 'evidencias'),
        os.path.join(base, 'backups'),
    ]
    
    for directorio in directorios_requeridos:
        if not os.path.exists(directorio):
            os.makedirs(directorio, exist_ok=True)
            app_logger.info(f"Directorio creado: {directorio}")

def verificar_integridad_base_datos():
    """Verifica la existencia e integridad de la base de datos"""
    ruta_db = os.path.join(obtener_ruta_base_datos(), 'apoyos.db')
    
    if not os.path.exists(ruta_db):

        app_logger.critical("Base de datos no encontrada. Ejecute 'python inicializar_sistema.py'")
        print("[ALERTA] Base de datos no encontrada.")
        print("   Ejecute el comando: python inicializar_sistema.py")
        return False
    
    # Verificar tamaño mínimo de la base de datos
    tamano_db = os.path.getsize(ruta_db)
    if tamano_db < 1024:  # Menos de 1KB
        app_logger.warning(f"Base de datos sospechosamente pequeña: {tamano_db} bytes")
        print("[ADVERTENCIA] Base de datos puede estar corrupta.")
    
    return True

def inicializar_usuarios_y_dependencias():
    """Inicializa usuarios y dependencias si están vacíos"""
    from app.models import Usuario, Dependencia
    from werkzeug.security import generate_password_hash
    from app import db
    from sqlalchemy.exc import OperationalError
    
    # Migrar columnas nuevas en tablas EXISTENTES antes de create_all(),
    # ya que create_all() nunca modifica tablas que ya existen.
    try:
        migrar_columnas_combustible()
    except Exception as e:
        app_logger.warning(f"Error al migrar columnas de combustible: {str(e)}")

    # Crear tablas nuevas que no existan (ej. cierres_ejercicio) sin afectar datos existentes
    try:
        db.create_all()
    except Exception as e:
        app_logger.warning(f"Error al verificar/crear tablas: {str(e)}")
    
    try:

        # Verificar si la tabla Dependencia existe
        Dependencia.query.first()
        tabla_dependencias_existe = True
    except OperationalError:
        tabla_dependencias_existe = False
        app_logger.warning("Tabla 'dependencias' no existe, omitiendo creación de dependencias")
    
    # 1. Crear dependencias oficiales si no existen (6 opciones)
    if tabla_dependencias_existe:
        dependencias_oficiales = [
            "DIF Municipal",
            "Dirección de Deportes",
            "Dirección de Servicios Públicos Municipales",
            "Presidencia Municipal",
            "Dirección de Desarrollo Social",
            "Dirección de Desarrollo Rural y Económico"
        ]
        
        for nombre in dependencias_oficiales:
            dependencia = Dependencia.query.filter_by(nombre=nombre).first()
            if not dependencia:
                dependencia = Dependencia(nombre=nombre)
                db.session.add(dependencia)
                app_logger.info(f"Dependencia creada: {nombre}")
    
    # 2. CORRECCIÓN CRÍTICA DE AUTENTICACIÓN: la cuenta OFICIAL de
    # Presidencia Municipal / Alcalde (con permisos de Administración
    # completos: Panel Ejecutivo Maestro, gestión de usuarios, cierre
    # de ejercicio, etc.) DEBE poder acceder SIEMPRE con la credencial
    # admin@atarjea.gob.mx / admin, sin importar si el usuario ya
    # existía con una contraseña distinta de una ejecución anterior
    # (bug reportado: "usuarios borrados"/contraseñas desincronizadas).
    # Por eso aquí se GARANTIZA (crea o resetea) esta cuenta en cada
    # arranque, en vez de solo crearla si no existe.
    admin_email = "admin@atarjea.gob.mx"
    admin_password = generate_password_hash("admin")

    admin = Usuario.query.filter_by(email=admin_email).first()
    if not admin:
        admin = Usuario(
            nombre="Alcalde - Presidencia Municipal",
            email=admin_email,
            password=admin_password,
            rol="admin",
            activo=True
        )
        db.session.add(admin)
        app_logger.info(f"Cuenta oficial de Presidencia Municipal/Alcalde creada: {admin_email}")
    else:
        # Garantiza acceso: restablece la contraseña oficial y reactiva
        # la cuenta si por cualquier motivo quedó inactiva o con un
        # hash corrupto/desincronizado. También actualiza el nombre
        # visible para reflejar que es la cuenta oficial del Alcalde.
        admin.password = admin_password
        admin.activo = True
        if not admin.rol:
            admin.rol = "admin"
        if admin.nombre in (None, '', 'Administrador Principal'):
            admin.nombre = "Alcalde - Presidencia Municipal"
        app_logger.info(f"Credenciales de la cuenta de Presidencia Municipal/Alcalde garantizadas: {admin_email}")
    
    # 3. Crear usuario director de prueba si no existe
    director_email = "director@atarjea.gob.mx"
    director_password = generate_password_hash("Director2026")
    
    director = Usuario.query.filter_by(email=director_email).first()
    if not director:
        primera_dependencia = Dependencia.query.first() if tabla_dependencias_existe else None
        
        director = Usuario(
            nombre="Director de Prueba",
            email=director_email,
            password=director_password,
            rol="director",
            dependencia_id=primera_dependencia.id if primera_dependencia else None,
            activo=True
        )
        db.session.add(director)
        app_logger.info(f"Usuario director creado: {director_email}")
    
    # 4. Crear usuario operador si no existe
    operador_email = "operador@atarjea.gob.mx"
    operador_password = generate_password_hash("Operador2026")
    
    operador = Usuario.query.filter_by(email=operador_email).first()
    if not operador:
        segunda_dependencia = Dependencia.query.get(2) if tabla_dependencias_existe and Dependencia.query.count() >= 2 else None
        
        operador = Usuario(
            nombre="Operador Municipal",
            email=operador_email,
            password=operador_password,
            rol="operador",
            dependencia_id=segunda_dependencia.id if segunda_dependencia else None,
            activo=True
        )
        db.session.add(operador)
        app_logger.info(f"Usuario operador creado: {operador_email}")
    
    # 5. Crear usuario Presidente Municipal de prueba si no existe (único que puede cerrar ejercicio)
    presidente_email = "presidente@atarjea.gob.mx"
    presidente_password = generate_password_hash("Presidente2026")
    
    presidente = Usuario.query.filter_by(email=presidente_email).first()
    if not presidente:
        presidente = Usuario(
            nombre="Presidente Municipal",
            email=presidente_email,
            password=presidente_password,
            rol="Presidente",
            activo=True
        )
        db.session.add(presidente)
        app_logger.info(f"Usuario Presidente Municipal creado: {presidente_email}")

    # 6. CORRECCIÓN CRÍTICA DE AUTENTICACIÓN: el usuario de Servicios
    # Públicos (Control de Combustible) DEBE poder acceder SIEMPRE con
    # la credencial oficial serviciospublicosAtarjea@gmail.com /
    # serviciospublicos. Acceso exclusivo a su Dashboard de Combustible,
    # sin visibilidad a otras áreas sociales del municipio. Se GARANTIZA
    # (crea o resetea) esta cuenta en cada arranque por la misma razón
    # que el administrador principal.
    servicios_publicos_email = "serviciospublicosAtarjea@gmail.com"
    servicios_publicos_password = generate_password_hash("serviciospublicos")

    usuario_servicios_publicos = Usuario.query.filter_by(email=servicios_publicos_email).first()
    if not usuario_servicios_publicos:
        usuario_servicios_publicos = Usuario(
            nombre="Encargada de Servicios Públicos",
            email=servicios_publicos_email,
            password=servicios_publicos_password,
            rol="ServiciosPublicos",
            activo=True
        )
        db.session.add(usuario_servicios_publicos)
        app_logger.info(f"Usuario de Servicios Públicos creado: {servicios_publicos_email}")
    else:
        usuario_servicios_publicos.password = servicios_publicos_password
        usuario_servicios_publicos.activo = True
        if not usuario_servicios_publicos.rol:
            usuario_servicios_publicos.rol = "ServiciosPublicos"
        app_logger.info(f"Credenciales de Servicios Públicos garantizadas: {servicios_publicos_email}")

    db.session.commit()
    return True


def migrar_columnas_combustible():
    """
    Agrega a la tabla 'bitacoras_combustible' (ya existente en bases de
    datos previas al módulo financiero) las columnas nuevas mediante
    ALTER TABLE, ya que db.create_all() NO modifica tablas existentes.
    Es seguro ejecutar esta función múltiples veces: solo agrega las
    columnas que todavía no existan.
    """
    import sqlite3
    from config_paths import obtener_ruta_base_datos

    ruta_db = os.path.join(obtener_ruta_base_datos(), 'apoyos.db')
    if not os.path.exists(ruta_db):
        return

    columnas_nuevas = {
        'vehiculo_id': 'INTEGER',
        'operador_id': 'INTEGER',
        'costo_litro_aplicado': 'NUMERIC(10, 2)',
        'costo_total': 'NUMERIC(10, 2)',
        # FASE 2: bloque común
        'hora': 'VARCHAR(10)',
        'area_solicitante': 'VARCHAR(150)',
        'motivo': 'VARCHAR(150)',
        'tipo_combustible': 'VARCHAR(20)',
        'autoriza_id': 'INTEGER',
        'despacha_id': 'INTEGER',
        'es_emergencia': 'BOOLEAN DEFAULT 0',
        'es_captura_posterior': 'BOOLEAN DEFAULT 0',
        'observaciones': 'TEXT',
        'capturado_por': 'VARCHAR(150)',
        'capturado_en': 'DATETIME',
        'estatus': "VARCHAR(20) DEFAULT 'ACTIVO'",
        'motivo_cancelacion': 'TEXT',
        'es_demo': 'BOOLEAN DEFAULT 0',
        'hash_registro': 'VARCHAR(64)',
        # FASE 2: catálogos Unidad/Equipo/Conductor
        'unidad_id': 'INTEGER',
        'equipo_id': 'INTEGER',
        'conductor_id': 'INTEGER',
        # FASE 2: OFICIAL
        'km_anterior': 'FLOAT',
        'km_actual': 'FLOAT',
        'km_recorridos': 'FLOAT',
        'tanque_lleno': 'BOOLEAN',
        'folio_solicitud': 'VARCHAR(50)',
        'km_estimados_ruta': 'FLOAT',
        # FASE 2: MAQUINARIA
        'horometro_anterior': 'FLOAT',
        'horometro_actual': 'FLOAT',
        'actividad': 'VARCHAR(200)',
        'ubicacion_obra': 'VARCHAR(200)',
        'foto_horometro': 'VARCHAR(500)',
        # FASE 2: EXTERNO
        'vehiculo_descripcion': 'VARCHAR(200)',
        'dependencia_propietaria': 'VARCHAR(150)',
        'motivo_apoyo': 'VARCHAR(200)',
        'solicitante_nombre': 'VARCHAR(150)',
        'oficio_autorizacion': 'VARCHAR(100)',
        # FASE 2: FORANEA
        'fecha_salida': 'DATETIME',
        'fecha_regreso': 'DATETIME',
        'km_salida': 'FLOAT',
        'km_regreso': 'FLOAT',
        'gasolinera': 'VARCHAR(150)',
        'monto_pesos': 'NUMERIC(10, 2)',
        'precio_por_litro': 'NUMERIC(10, 2)',
        'tiene_factura': 'VARCHAR(20)',
        'foto_ticket': 'VARCHAR(500)',
        # FASE 2: CIUDADANO
        'beneficiario_nombre': 'VARCHAR(150)',
        'beneficiario_curp': 'VARCHAR(18)',
        'telefono': 'VARCHAR(20)',
        'descripcion_breve': 'VARCHAR(200)',
        'apoyo_previo': 'BOOLEAN',
        'foto_solicitud': 'VARCHAR(500)',
        'foto_identificacion': 'VARCHAR(500)',
    }

    # FORMULARIO N° 10: columnas nuevas en catálogos EXISTENTES
    columnas_nuevas_unidad = {
        'rendimiento_base': 'FLOAT DEFAULT 10.0',
        # PADRÓN REAL DEL PARQUE VEHICULAR (importado del Excel oficial)
        'area': 'VARCHAR(150)',
        'marca': 'VARCHAR(80)',
        'tipo': 'VARCHAR(80)',
        'clase': 'VARCHAR(80)',
        'linea': 'VARCHAR(80)',
        'serie': 'VARCHAR(50)',
    }
    columnas_nuevas_conductor = {'licencia_numero': 'VARCHAR(50)', 'licencia_vigencia': 'DATE'}
    columnas_nuevas_equipo = {'rendimiento_base_horas': 'FLOAT DEFAULT 8.0'}
    # FORMULARIO N° 10 (rediseño oficial): columnas nuevas en asignaciones_combustible
    columnas_nuevas_asignacion = {
        'fecha_solicitud': 'DATETIME',
        'tipo_recorrido': 'VARCHAR(30)',
        'actividades': 'TEXT',
        'director_area': 'VARCHAR(150)',
        'quien_autoriza': 'VARCHAR(150)',
        'subtipo_asignacion': 'VARCHAR(40)',
        'horometro_inicial': 'FLOAT',
        'horometro_final': 'FLOAT',
        'destino_apoyo_agua': 'VARCHAR(40)',
        'equipo_id': 'INTEGER',
        'motivo_cancelacion': 'TEXT',
    }

    def _migrar_tabla(cursor, nombre_tabla, columnas):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nombre_tabla,))
        if not cursor.fetchone():
            return  # La tabla se creará desde cero con db.create_all()
        cursor.execute(f"PRAGMA table_info({nombre_tabla})")
        existentes = {fila[1] for fila in cursor.fetchall()}
        for columna, tipo in columnas.items():
            if columna not in existentes:
                cursor.execute(f"ALTER TABLE {nombre_tabla} ADD COLUMN {columna} {tipo}")
                app_logger.info(f"Columna '{columna}' agregada a {nombre_tabla}")

    conn = sqlite3.connect(ruta_db)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bitacoras_combustible'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(bitacoras_combustible)")
            columnas_existentes = {fila[1] for fila in cursor.fetchall()}

            for columna, tipo in columnas_nuevas.items():
                if columna not in columnas_existentes:
                    cursor.execute(f"ALTER TABLE bitacoras_combustible ADD COLUMN {columna} {tipo}")
                    app_logger.info(f"Columna '{columna}' agregada a bitacoras_combustible")

        _migrar_tabla(cursor, 'catalogo_unidades', columnas_nuevas_unidad)
        _migrar_tabla(cursor, 'catalogo_conductores', columnas_nuevas_conductor)
        _migrar_tabla(cursor, 'catalogo_equipos', columnas_nuevas_equipo)
        _migrar_tabla(cursor, 'asignaciones_combustible', columnas_nuevas_asignacion)

        # ORDEN TÉCNICA MAESTRA - TANQUE SECUENCIAL AUTOMÁTICO: agrega la
        # columna 'es_principal' a la tabla de configuración de tanques
        # (ya existente en ejecuciones previas del módulo Multitanque) y
        # garantiza que, por defecto, el Tanque 1 de cada fluido quede
        # marcado como Principal si ningún tanque lo era todavía.
        _migrar_tabla(cursor, 'configuracion_tanques', {'es_principal': 'BOOLEAN DEFAULT 0'})
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='configuracion_tanques'")
        if cursor.fetchone():
            cursor.execute("SELECT DISTINCT tipo_fluido FROM configuracion_tanques")
            fluidos_existentes = [fila[0] for fila in cursor.fetchall()]
            for fluido in fluidos_existentes:
                cursor.execute(
                    "SELECT COUNT(*) FROM configuracion_tanques WHERE tipo_fluido=? AND es_principal=1",
                    (fluido,)
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "UPDATE configuracion_tanques SET es_principal=1 WHERE tipo_fluido=? AND numero_tanque=1",
                        (fluido,)
                    )
                    app_logger.info(f"Tanque 1 de {fluido} marcado como Principal por defecto (migración).")

        # ORDEN TÉCNICA MAESTRA: simplificación de estados del Formulario
        # N° 10 a únicamente 3 etapas visibles (Autorizado / En Proceso /
        # Revisión) + Cancelada. Traduce cualquier valor LEGADO que ya
        # existiera en la base de datos (EMITIDA/ENTREGADA/COMPROBADA/
        # VENCIDA) a su equivalente nuevo, para que ningún registro
        # histórico quede con un estatus obsoleto que ya no reconoce la
        # interfaz.
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='asignaciones_combustible'")
        if cursor.fetchone():
            mapa_estatus_legado = {
                'EMITIDA': 'Autorizado',
                'ENTREGADA': 'En Proceso',
                'COMPROBADA': 'Revisión',
                'VENCIDA': 'En Proceso',
                'CANCELADA': 'Cancelada',
            }
            for valor_legado, valor_nuevo in mapa_estatus_legado.items():
                cursor.execute(
                    "UPDATE asignaciones_combustible SET estatus = ? WHERE estatus = ?",
                    (valor_nuevo, valor_legado)
                )

            # ORDEN TÉCNICA MAESTRA: INTEGRACIÓN DE LAS 10 PLANTILLAS
            # OFICIALES. "Equipo Ligero" se renombró a "Equipo Menor" y
            # "Pipa" (antes subtipo dentro de Maquinaria) se promovió a
            # bitácora propia. Traduce cualquier registro histórico que
            # ya existiera con las claves viejas.
            mapa_tipo_asignacion_legado = {
                'EQUIPO_LIGERO': 'EQUIPO_MENOR',
            }
            for valor_legado, valor_nuevo in mapa_tipo_asignacion_legado.items():
                cursor.execute(
                    "UPDATE asignaciones_combustible SET tipo_asignacion = ? WHERE tipo_asignacion = ?",
                    (valor_nuevo, valor_legado)
                )
            # Las asignaciones de MAQUINARIA con subtipo_asignacion='PIPA'
            # pasan a ser bitácora PIPA propia (ya no un subtipo).
            cursor.execute(
                "UPDATE asignaciones_combustible SET tipo_asignacion = 'PIPA', subtipo_asignacion = NULL "
                "WHERE tipo_asignacion = 'MAQUINARIA' AND subtipo_asignacion = 'PIPA'"
            )
            # ORDEN TÉCNICA MAESTRA (sincronización de catálogo Excel):
            # Camión de Basura (antes subtipo_asignacion='CAMION_BASURA'
            # dentro de MAQUINARIA) se PROMUEVE a bitácora propia, ya que
            # ahora tiene su propia plantilla oficial
            # "BITACORA_CAMION_BASURA.xlsx". Conserva subtipo_asignacion
            # como marca de compatibilidad (nunca se borra, por inmutabilidad).
            cursor.execute(
                "UPDATE asignaciones_combustible SET tipo_asignacion = 'CAMION_BASURA' "
                "WHERE tipo_asignacion = 'MAQUINARIA' AND subtipo_asignacion = 'CAMION_BASURA'"
            )

        conn.commit()
    except Exception as e:
        app_logger.warning(f"Error al migrar columnas de combustible/Formulario 10: {str(e)}")
    finally:
        conn.close()


def poblar_catalogo_combustible():
    """
    Establece el costo inicial vigente del litro de combustible.

    NOTA DE LIMPIEZA: este catálogo legado (VehiculoMunicipal/
    OperadorMunicipal) ya NO se siembra con datos genéricos/inventados;
    el sistema de bitácoras físicas por tipo fue superado por el
    Formulario N° 10 (AsignacionCombustible), que usa el padrón real
    de Unidad/Equipo/Conductor importado desde el Excel oficial.
    """
    from app.models import ConfiguracionCombustible
    from app import db

    if not ConfiguracionCombustible.query.first():
        db.session.add(ConfiguracionCombustible(costo_litro=24.50))
        app_logger.info("Costo inicial de combustible configurado: $24.50 MXN/L")

    db.session.commit()

    # Recalcular el costo monetario de registros existentes que aún no lo
    # tengan calculado (ej. capturados antes de habilitar el módulo
    # financiero), para que el Balance Financiero refleje datos reales.
    from app.models import BitacoraCombustible
    registros_sin_costo = BitacoraCombustible.query.filter(
        BitacoraCombustible.costo_total.is_(None)
    ).all()
    if registros_sin_costo:
        for registro in registros_sin_costo:
            registro.calcular_costo()
        db.session.commit()
        app_logger.info(f"Costo financiero recalculado para {len(registros_sin_costo)} registro(s) existentes.")

    # Marcar como es_demo=True los registros LEGADOS (creados antes de la
    # Fase 2, por lo que nunca tuvieron 'capturado_en' ni 'estatus').
    # Se usa 'capturado_en IS NULL' como indicador de registro legado, para
    # NO marcar por error registros reales futuros que tengan es_demo=False.
    registros_legado = BitacoraCombustible.query.filter(
        BitacoraCombustible.capturado_en.is_(None)
    ).all()
    if registros_legado:
        for r in registros_legado:
            r.es_demo = True
            r.estatus = r.estatus or 'ACTIVO'
            r.capturado_por = r.capturado_por or r.responsable_nombre
            r.capturado_en = r.fecha
            r.generar_hash()
        db.session.commit()
        app_logger.info(f"{len(registros_legado)} registro(s) demo preexistentes (legados) marcados con es_demo=True.")


def limpiar_catalogos_genericos():
    """
    LIMPIEZA TOTAL DE DATOS DE PRUEBA (ORDEN TÉCNICA MAESTRA, punto 4):
    elimina permanentemente cualquier vehículo, maquinaria, bitácora o
    asignación GENÉRICA/INVENTADA creada por versiones anteriores del
    sistema de demostración, dejando como única fuente de verdad del
    parque vehicular el padrón oficial real importado por
    importar_flota_real() desde "PARQUE VEHICULARCORREGIDO.xlsx".

    Es seguro ejecutar esta función en cada arranque: solo borra
    registros que coinciden exactamente con los nombres/placas genéricos
    conocidos de las versiones de demostración previas (ATJ-101..104,
    MAQ-201..203, catálogo legado VehiculoMunicipal/OperadorMunicipal) y
    cualquier BitacoraCombustible/AsignacionCombustible marcada es_demo=True.
    Nunca toca datos reales capturados por el usuario (es_demo=False).
    """
    from app.models import (Unidad, Equipo, VehiculoMunicipal, OperadorMunicipal,
                             BitacoraCombustible, AsignacionCombustible)
    from app import db

    placas_genericas = {'ATJ-101', 'ATJ-102', 'ATJ-103', 'ATJ-104'}
    nombres_equipo_genericos = {'Retroexcavadora CAT 420', 'Camión Recolector de Basura', 'Motoconformadora Municipal'}
    economicos_equipo_genericos = {'MAQ-201', 'MAQ-202', 'MAQ-203'}

    eliminados = 0

    # 1. Unidades genéricas/inventadas (parque vehicular demo de versiones previas)
    for unidad in Unidad.query.filter(Unidad.placa.in_(placas_genericas)).all():
        # Solo se eliminan si NO tienen marca/serie reales (es decir, nunca
        # fueron sobrescritas por el padrón oficial, que sí trae VIN real).
        if not unidad.serie:
            db.session.delete(unidad)
            eliminados += 1

    # 2. Equipos (maquinaria por horómetro) genéricos/inventados
    for equipo in Equipo.query.filter(
        db.or_(Equipo.nombre.in_(nombres_equipo_genericos), Equipo.num_economico.in_(economicos_equipo_genericos))
    ).all():
        db.session.delete(equipo)
        eliminados += 1

    # 3. Catálogo legado (VehiculoMunicipal/OperadorMunicipal): sistema de
    # bitácoras físicas superado por el Formulario N° 10; se elimina por
    # completo para no dejar referencias a vehículos inventados.
    for v in VehiculoMunicipal.query.all():
        db.session.delete(v)
        eliminados += 1
    for o in OperadorMunicipal.query.all():
        db.session.delete(o)
        eliminados += 1

    # 4. Bitácoras físicas legadas marcadas como demo (datos de prueba)
    for b in BitacoraCombustible.query.filter_by(es_demo=True).all():
        db.session.delete(b)
        eliminados += 1

    # 5. Asignaciones de combustible (Formulario N° 10) marcadas como demo
    for a in AsignacionCombustible.query.filter_by(es_demo=True).all():
        db.session.delete(a)
        eliminados += 1

    if eliminados:
        db.session.commit()
        app_logger.info(f"Limpieza de datos genéricos/inventados: {eliminados} registro(s) eliminados permanentemente.")


def poblar_catalogo_fase2():
    """
    FASE 2 - Inserta los catálogos nuevos (Unidad, Equipo, Conductor,
    Autorizador, Despachador, Motivo, Area, Gasolinera) y la configuración
    de umbrales por defecto. Solo se ejecuta si cada catálogo está vacío.
    """
    from app.models import (Unidad, Equipo, Conductor, Autorizador, Despachador,
                             Motivo, Area, Gasolinera, ConfiguracionUmbrales)
    from app import db

    # NOTA DE LIMPIEZA: el catálogo de Unidades ya NO se siembra con
    # vehículos genéricos/inventados (ATJ-101..104). El único origen de
    # datos del parque vehicular es el padrón oficial real importado por
    # importar_flota_real() desde "PARQUE VEHICULARCORREGIDO.xlsx". Los
    # registros genéricos preexistentes se eliminan en limpiar_catalogos_genericos().

    if not Equipo.query.first():
        # CATÁLOGO DE MAQUINARIA POR HORÓMETRO (Equipo): construido a
        # partir de la maquinaria REAL del padrón oficial (Unidad con
        # tipo RETROEXCABADORA/MOTONIVELADORA/CAMION COMPACTADOR), no de
        # nombres inventados. Si el padrón real aún no se ha importado
        # (primera ejecución, antes de importar_flota_real()), se omite
        # y se reintenta en el siguiente arranque sin bloquear nada.
        maquinaria_real = Unidad.query.filter(
            Unidad.tipo.in_(['RETROEXCABADORA', 'MOTONIVELADORA', 'CAMION COMPACTADOR'])
        ).all()
        for m in maquinaria_real:
            nombre_equipo = f"{m.marca or ''} {m.tipo or ''}".strip() or m.nombre
            ya_existe = Equipo.query.filter_by(nombre=nombre_equipo).first()
            if not ya_existe:
                db.session.add(Equipo(
                    num_economico=m.placa or m.serie,
                    nombre=nombre_equipo,
                    tipo_combustible=m.tipo_combustible or 'Diésel',
                    capacidad_tanque=m.capacidad_tanque or 150.0,
                    ultimo_horometro=0.0,
                    rendimiento_base_horas=8.0,
                ))
        if maquinaria_real:
            app_logger.info("Catálogo de Equipos (por Horómetro) poblado desde el padrón real de maquinaria.")

    if not Conductor.query.first():
        from datetime import date, timedelta
        hoy = date.today()
        conductores_demo = [
            ('Juan Pérez López', 'Chofer', 'LIC-001-GTO', hoy + timedelta(days=365)),
            ('María Hernández Cruz', 'Chofer', 'LIC-002-GTO', hoy + timedelta(days=180)),
            ('Carlos Ramírez Soto', 'Chofer', 'LIC-003-GTO', hoy - timedelta(days=15)),  # vencida (demo de alerta)
            ('Felipe Soto García', 'Operador de Maquinaria', 'LIC-004-GTO', hoy + timedelta(days=300)),
            ('Ricardo López Vega', 'Operador de Maquinaria', 'LIC-005-GTO', hoy + timedelta(days=90)),
        ]
        for nombre, puesto, licencia_numero, licencia_vigencia in conductores_demo:
            db.session.add(Conductor(nombre=nombre, puesto=puesto, licencia_numero=licencia_numero, licencia_vigencia=licencia_vigencia))
        app_logger.info("Catálogo de Conductores (Fase 2) insertado.")
    else:
        # RETROFIT: si los conductores ya existían de una ejecución previa
        # (antes de agregar 'licencia_numero'/'licencia_vigencia'), se
        # completan esos datos para que el demo de alertas funcione.
        from datetime import date, timedelta
        hoy = date.today()
        licencias_referencia = {
            'Juan Pérez López': ('LIC-001-GTO', hoy + timedelta(days=365)),
            'María Hernández Cruz': ('LIC-002-GTO', hoy + timedelta(days=180)),
            'Carlos Ramírez Soto': ('LIC-003-GTO', hoy - timedelta(days=15)),
            'Felipe Soto García': ('LIC-004-GTO', hoy + timedelta(days=300)),
            'Ricardo López Vega': ('LIC-005-GTO', hoy + timedelta(days=90)),
        }
        for conductor in Conductor.query.filter_by(licencia_vigencia=None).all():
            if conductor.nombre in licencias_referencia:
                numero, vigencia = licencias_referencia[conductor.nombre]
                conductor.licencia_numero = numero
                conductor.licencia_vigencia = vigencia

    if not Autorizador.query.first():
        autorizadores_demo = [
            ('Presidente Municipal', 'Presidente Municipal'),
            ('Secretario Particular', 'Secretario Particular'),
            ('Director de Servicios Públicos', 'Director de Área'),
            ('Director de Obras Públicas', 'Director de Área'),
            ('Encargada de Servicios Públicos', 'Encargada'),
        ]
        for nombre, puesto in autorizadores_demo:
            db.session.add(Autorizador(nombre=nombre, puesto=puesto))
        app_logger.info("Catálogo de Autorizadores (Fase 2, roles ampliados) insertado.")
    else:
        # RETROFIT: agrega los nuevos roles de autorización (Secretario
        # Particular, Director de Área genérico) si el catálogo ya
        # existía de una ejecución previa sin estos roles.
        nombres_existentes = {a.nombre for a in Autorizador.query.all()}
        faltantes = [
            ('Secretario Particular', 'Secretario Particular'),
            ('Director de Servicios Públicos', 'Director de Área'),
            ('Director de Obras Públicas', 'Director de Área'),
        ]
        for nombre, puesto in faltantes:
            if nombre not in nombres_existentes:
                db.session.add(Autorizador(nombre=nombre, puesto=puesto))

    if not Despachador.query.first():
        for nombre in ['Encargada de Servicios Públicos', 'Auxiliar de Combustible']:
            db.session.add(Despachador(nombre=nombre))
        app_logger.info("Catálogo de Despachadores (Fase 2) insertado.")

    if not Motivo.query.first():
        motivos_demo = [
            ('OFICIAL', 'Comisión Administrativa'), ('OFICIAL', 'Supervisión de Obra'),
            ('MAQUINARIA', 'Bacheo de Calles'), ('MAQUINARIA', 'Recolección de Basura'),
            ('EXTERNO', 'Apoyo a Dependencia Externa'),
            ('FORANEA', 'Trámite ante Gobierno del Estado'), ('FORANEA', 'Capacitación'),
            ('CIUDADANO', 'Traslado Médico de Emergencia'), ('CIUDADANO', 'Apoyo Funerario'),
        ]
        for tipo, nombre in motivos_demo:
            db.session.add(Motivo(tipo_bitacora=tipo, nombre=nombre))
        app_logger.info("Catálogo de Motivos (Fase 2) insertado.")

    if not Area.query.first():
        for nombre in ['Presidencia Municipal', 'Dirección de Servicios Públicos', 'DIF Municipal', 'Dirección de Obras Públicas']:
            db.session.add(Area(nombre=nombre))
        app_logger.info("Catálogo de Áreas (Fase 2) insertado.")

    if not Gasolinera.query.first():
        for nombre, ubicacion in [('Gasolinera Pemex Atarjea', 'Carretera Atarjea'), ('Gasolinera San Luis de la Paz', 'San Luis de la Paz, Gto.')]:
            db.session.add(Gasolinera(nombre=nombre, ubicacion=ubicacion))
        app_logger.info("Catálogo de Gasolineras (Fase 2) insertado.")

    if not ConfiguracionUmbrales.query.first():
        db.session.add(ConfiguracionUmbrales())
        app_logger.info("Configuración de umbrales por defecto (Fase 2) insertada.")

    db.session.commit()


def importar_flota_real():
    """
    Importa el PADRÓN REAL del parque vehicular municipal desde el archivo
    oficial "PARQUE VEHICULARCORREGIDO.xlsx" (ya procesado como
    'data_flota_municipal.json' en la raíz del proyecto), agregando cada
    vehículo al catálogo de Unidades.

    CERO BLOQUEOS: es idempotente (no duplica por PLACA) y se ejecuta
    cada arranque; si el archivo de datos no existe o ya se importó todo,
    simplemente no hace nada. Nunca interrumpe el arranque del sistema.
    """
    import json
    from app.models import Unidad
    from app import db
    from config_paths import obtener_ruta_base_app

    ruta_json = os.path.join(obtener_ruta_base_app(), 'data_flota_municipal.json')
    if not os.path.exists(ruta_json):
        return

    try:
        with open(ruta_json, 'r', encoding='utf-8') as f:
            flota = json.load(f)
    except Exception as e:
        app_logger.warning(f"No se pudo leer el padrón real de flota: {str(e)}")
        return

    placas_existentes = {
        (u.placa or '').strip().upper()
        for u in Unidad.query.filter(Unidad.placa.isnot(None)).all()
    }
    # Para unidades SIN placa (S/P), la deduplicación persistente se hace
    # por número de serie (VIN), que sí es único por vehículo real.
    series_existentes = {
        (u.serie or '').strip()
        for u in Unidad.query.filter(Unidad.serie.isnot(None)).all()
    }

    # Heurística simple: unidades pesadas/maquinaria suelen usar Diésel;
    # el resto (sedanes, camionetas ligeras, motos) usan Gasolina. Es
    # solo un valor de referencia inicial: el usuario puede corregirlo
    # desde el catálogo en cualquier momento.
    tipos_diesel = {'RETROEXCABADORA', 'MOTONIVELADORA', 'CAMION COMPACTADOR', 'VOLTEO', 'PIPA', 'AUTOBUS', 'OMNIBUS'}

    nuevas = 0
    vistas_en_archivo = set()
    for registro in flota:
        placa = (registro.get('placa') or '').strip().upper()
        serie = (registro.get('serie') or '').strip() or None

        # Evita duplicar la misma placa real dentro del propio archivo
        # (p. ej. "S/P" se repite legítimamente en varias unidades sin
        # placa asignada, así que esas sí se permiten varias veces).
        clave_duplicado = placa if placa and placa != 'S/P' else serie
        if clave_duplicado and clave_duplicado in vistas_en_archivo:
            continue
        if clave_duplicado:
            vistas_en_archivo.add(clave_duplicado)

        if placa and placa != 'S/P' and placa in placas_existentes:
            continue  # ya importada en una ejecución anterior (deduplicado por placa)
        if (not placa or placa == 'S/P') and serie and serie in series_existentes:
            continue  # ya importada en una ejecución anterior (deduplicado por serie/VIN)

        marca = registro.get('marca') or ''
        tipo = registro.get('tipo') or ''
        clase = registro.get('clase') or ''
        linea = registro.get('linea') or ''

        nombre_partes = [p for p in [marca, tipo or linea] if p]
        nombre = ' '.join(nombre_partes).strip() or f"Unidad {placa or serie or 'S/P'}"

        es_diesel = tipo.upper() in tipos_diesel or clase.upper() == 'MAQUINARIA' or clase.upper() == 'AUTOBUS'

        nueva_unidad = Unidad(
            num_economico=None,
            placa=placa if placa and placa != 'S/P' else None,
            nombre=nombre,
            modelo=registro.get('modelo'),
            color=registro.get('color'),
            tipo_combustible='Diésel' if es_diesel else 'Gasolina',
            capacidad_tanque=150.0 if es_diesel else 60.0,
            tipo_medicion='KM',
            ultimo_km=0.0,
            rendimiento_base=6.0 if es_diesel else 10.0,
            activa=True,
            area=registro.get('area'),
            marca=marca or None,
            tipo=tipo or None,
            clase=clase or None,
            linea=linea or None,
            serie=serie,
        )
        db.session.add(nueva_unidad)
        nuevas += 1
        if placa and placa != 'S/P':
            placas_existentes.add(placa)
        if serie:
            series_existentes.add(serie)

    if nuevas:
        db.session.commit()
        app_logger.info(f"Padrón real del parque vehicular: {nuevas} unidad(es) importada(s) desde el Excel oficial.")


def generar_folio_asignacion():
    """Genera un folio consecutivo tipo ASIG-2026-XXXX para el Formulario N° 10."""
    from app.models import AsignacionCombustible
    from datetime import datetime
    anio = datetime.utcnow().year
    prefijo = f"ASIG-{anio}-"
    ultima = AsignacionCombustible.query.filter(
        AsignacionCombustible.folio_asignacion.like(f"{prefijo}%")
    ).order_by(AsignacionCombustible.id.desc()).first()

    if ultima and ultima.folio_asignacion:
        try:
            numero = int(ultima.folio_asignacion.replace(prefijo, '')) + 1
        except (ValueError, TypeError):
            numero = 1
    else:
        numero = 1

    return f"{prefijo}{numero:04d}"


def poblar_datos_demo_asignaciones():
    """
    [OBSOLETA / YA NO SE LLAMA DESDE main()] ORDEN TÉCNICA MAESTRA -
    VACIADO A CEROS: esta función creaba automáticamente una Asignación
    de Combustible "de ejemplo" vinculada a la primera unidad oficial
    del padrón. Se conserva el código por trazabilidad histórica, pero
    NO debe invocarse de nuevo en el arranque: los vales/autorizaciones
    deben permanecer en cero absoluto hasta la primera operación real
    capturada por el personal durante las pruebas de campo.
    """
    from app.models import AsignacionCombustible, Unidad, Conductor
    from app import db
    from datetime import datetime, timedelta

    if AsignacionCombustible.query.first():
        return  # Ya existen asignaciones reales; nunca se sobrescriben

    # LIMPIEZA TOTAL DE DATOS DE PRUEBA (ORDEN TÉCNICA MAESTRA, punto 4):
    # ya NO se insertan 5 asignaciones ficticias con choferes/unidades
    # inventados. Se deja únicamente 1 asignación REAL de ejemplo,
    # conectada a una unidad oficial verdadera del padrón importado
    # (si ya existe alguna), para que la tabla no se vea vacía sin
    # perder la trazabilidad con vehículos reales. Si el padrón real
    # aún no se ha importado, no se crea ningún registro.
    unidad_real = Unidad.query.filter(Unidad.area.isnot(None)).order_by(Unidad.id.asc()).first()
    if not unidad_real:
        return

    ahora = datetime.utcnow()
    folio_ejemplo = generar_folio_asignacion()

    db.session.add(AsignacionCombustible(
        es_demo=False,
        folio_asignacion=folio_ejemplo,
        unidad_organizacional=unidad_real.area or 'Dirección de Servicios Públicos',
        tipo_asignacion='OFICIAL',
        itinerario_destino='Comisión oficial de ejemplo (registro real inicial)',
        fecha_inicio=ahora,
        fecha_fin=ahora,
        responsable_nombre='Encargada de Servicios Públicos',
        vehiculo_id=unidad_real.id,
        litros_asignados=0.0,
        estatus='Autorizado',
        km_inicial=unidad_real.ultimo_km or 0,
    ))

    db.session.commit()
    app_logger.info(f"Asignación real inicial de ejemplo creada (Folio {folio_ejemplo}) vinculada a la unidad oficial '{unidad_real.nombre}'.")


def poblar_abasto_inicial():
    """
    [OBSOLETA / YA NO SE LLAMA DESDE main()] ORDEN TÉCNICA MAESTRA -
    VACIADO A CEROS: esta función reponía automáticamente 1,000 L cada
    vez que la tabla RegistroAbasto quedaba vacía, revirtiendo cualquier
    vaciado intencional del Tanque Principal. Se conserva el código por
    trazabilidad histórica, pero NO debe invocarse de nuevo en el
    arranque: el inventario debe permanecer en 0.0 L hasta que el
    personal de Servicios Públicos registre el primer abasto real
    durante las pruebas de campo.
    """
    from app.models import RegistroAbasto, Usuario
    from app import db
    from datetime import datetime

    if RegistroAbasto.query.first():
        return  # Ya existen registros de abasto (reales o iniciales); no duplicar

    usuario_sp = Usuario.query.filter_by(email="serviciospublicosAtarjea@gmail.com").first()
    usuario_id = usuario_sp.id if usuario_sp else None

    abasto_inicial = RegistroAbasto(
        fecha=datetime.utcnow(),
        proveedor='Carga Inicial del Tanque Municipal',
        municipio_origen='Atarjea, Gto.',
        litros_recibidos=1000.0,
        documento='NINGUNO',
        numero='CARGA-INICIAL-001',
        recibe='Encargada de Servicios Públicos',
        usuario_id=usuario_id,
        es_demo=False
    )
    db.session.add(abasto_inicial)
    db.session.commit()
    app_logger.info("Abasto inicial de 1,000 L registrado automáticamente (tanque municipal).")


def poblar_datos_demo_combustible():
    """
    Inserta datos de demostración (dummy) para el Módulo de Servicios
    Públicos - Control de Combustible, con al menos 15 registros
    distribuidos entre las 5 bitácoras oficiales del municipio, usando
    comunidades reales de Atarjea. Incluye 2-3 registros con desviación
    de rendimiento para que el semáforo de alertas se aprecie funcionando.
    Solo se ejecuta si la tabla está vacía (no duplica datos reales).
    """
    from app.models import BitacoraCombustible, Usuario
    from app import db
    from datetime import datetime, timedelta

    if BitacoraCombustible.query.first():
        return  # Ya existen datos (reales o de demo previos); no duplicar

    usuario_sp = Usuario.query.filter_by(email="serviciospublicosAtarjea@gmail.com").first()
    usuario_id = usuario_sp.id if usuario_sp else None

    ahora = datetime.utcnow()

    registros_demo = [
        # --- OFICIAL (vehículos oficiales): normales ---
        dict(tipo='OFICIAL', folio='00101', vehiculo='Camioneta Pickup Ford', color='Blanco', modelo='2019',
             placa='ATJ-101', km_i=45000, km_f=45080, litros=8.0, resp='Juan Pérez López', dias=1),
        dict(tipo='OFICIAL', folio='00102', vehiculo='Sedán Nissan Versa', color='Gris', modelo='2021',
             placa='ATJ-102', km_i=22000, km_f=22090, litros=9.5, resp='María Hernández Cruz', dias=2),
        dict(tipo='OFICIAL', folio='00103', vehiculo='Camioneta Chevrolet Silverado', color='Rojo', modelo='2018',
             placa='ATJ-103', km_i=78000, km_f=78060, litros=14.0, resp='Carlos Ramírez Soto', dias=3),
        # --- OFICIAL con alerta de rendimiento (muy pocos km con muchos litros) ---
        dict(tipo='OFICIAL', folio='00104', vehiculo='Camioneta Ford Lobo', color='Azul', modelo='2017',
             placa='ATJ-104', km_i=90000, km_f=90020, litros=25.0, resp='Juan Pérez López', dias=4, alerta=True),

        # --- MAQUINARIA: normales ---
        dict(tipo='MAQUINARIA', folio='00201', vehiculo='Retroexcavadora CAT 420', litros=45.0, horas=5.0,
             resp='Felipe Soto García', dias=1),
        dict(tipo='MAQUINARIA', folio='00202', vehiculo='Camión Recolector de Basura', litros=60.0, horas=8.0,
             resp='Ricardo López Vega', dias=2),
        dict(tipo='MAQUINARIA', folio='00203', vehiculo='Motoconformadora Municipal', litros=38.0, horas=6.5,
             resp='Felipe Soto García', dias=5),
        # --- MAQUINARIA con alerta (muy pocas horas con muchos litros) ---
        dict(tipo='MAQUINARIA', folio='00204', vehiculo='Retroexcavadora CAT 420', litros=70.0, horas=2.0,
             resp='Ricardo López Vega', dias=6, alerta=True),

        # --- EXTERNO: vehículos externos apoyando al municipio ---
        dict(tipo='EXTERNO', folio='00301', vehiculo='Camioneta Particular', placa='GTO-5521', litros=10.0,
             resp='Jorge Aguilar Mendoza', dias=1),
        dict(tipo='EXTERNO', folio='00302', vehiculo='Taxi Local', placa='GTO-3310', litros=7.5,
             resp='Salvador Núñez Ríos', dias=3),
        dict(tipo='EXTERNO', folio='00303', vehiculo='Camión de Carga Rentado', placa='GTO-8842', litros=22.0,
             resp='Jorge Aguilar Mendoza', dias=7),

        # --- FORANEA: cargas foráneas (viajes a otros municipios/capital) ---
        dict(tipo='FORANEA', folio='00401', destino='San Luis de la Paz, Gto.', vehiculo='Camioneta Oficial',
             placa='ATJ-101', litros=18.0, resp='María Hernández Cruz', dias=2),
        dict(tipo='FORANEA', folio='00402', destino='Querétaro, Qro. (Capital)', vehiculo='Sedán Nissan Versa',
             placa='ATJ-102', litros=24.0, resp='Carlos Ramírez Soto', dias=4),
        dict(tipo='FORANEA', folio='00403', destino='Xichú, Gto.', vehiculo='Camioneta Chevrolet Silverado',
             placa='ATJ-103', litros=16.0, resp='Juan Pérez López', dias=8),

        # --- CIUDADANO: apoyos a comunidades reales de Atarjea ---
        dict(tipo='CIUDADANO', folio='00501', comunidad='Amos', vehiculo='Camioneta Oficial', placa='ATJ-101',
             litros=12.0, resp='María Hernández Cruz', dias=1),
        dict(tipo='CIUDADANO', folio='00502', comunidad='El Carricillo', vehiculo='Camión Recolector de Basura',
             placa='ATJ-201', litros=15.0, resp='Ricardo López Vega', dias=2),
        dict(tipo='CIUDADANO', folio='00503', comunidad='Mangas Cuatas', vehiculo='Camioneta Chevrolet Silverado',
             placa='ATJ-103', litros=20.0, resp='Carlos Ramírez Soto', dias=5),
        dict(tipo='CIUDADANO', folio='00504', comunidad='El Lindero', vehiculo='Camioneta Pickup Ford',
             placa='ATJ-101', litros=13.5, resp='Juan Pérez López', dias=9),
    ]

    for r in registros_demo:
        registro = BitacoraCombustible(
            tipo_bitacora=r['tipo'],
            fecha=ahora - timedelta(days=r['dias']),
            folio_vale=r['folio'],
            destino_comision=r.get('destino'),
            vehiculo_nombre=r.get('vehiculo'),
            color=r.get('color'),
            modelo=r.get('modelo'),
            placa=r.get('placa'),
            km_inicial=r.get('km_i'),
            km_final=r.get('km_f'),
            horas_trabajo=r.get('horas'),
            litros=r['litros'],
            comunidad=r.get('comunidad'),
            responsable_nombre=r['resp'],
            usuario_id=usuario_id,
            es_demo=True,
            estatus='ACTIVO',
            capturado_por=r['resp'],
            capturado_en=ahora - timedelta(days=r['dias'])
        )
        registro.calcular_rendimiento()
        registro.calcular_costo()
        registro.generar_hash()
        db.session.add(registro)

    db.session.commit()
    app_logger.info("Datos de demostración de Servicios Públicos (Combustible) insertados.")


def configurar_entorno_produccion():
    """Configura el entorno para producción"""
    # Obtener configuración de variables de entorno
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    
    # Determinar modo de operación
    entorno = os.environ.get('FLASK_ENV', 'production')
    modo_depuracion = entorno.lower() == 'development'
    
    # Configurar logging según entorno
    if modo_depuracion:
        app.logger.setLevel(logging.DEBUG)
        nivel_log = "DEPURACIÓN"
    else:
        app.logger.setLevel(logging.WARNING)
        nivel_log = "PRODUCCIÓN"
    
    return host, port, modo_depuracion, nivel_log

def main():
    """Punto de entrada principal del sistema"""
    print("========================================================")
    print("  SISTEMA INTEGRAL DE GESTIÓN MUNICIPAL - ATARJEA    ")
    print("  Dirección de Desarrollo Social y Económico         ")
    print("========================================================")
    
    # Verificar estructura del sistema
    verificar_estructura_sistema()
    
    # Verificar integridad de base de datos
    if not verificar_integridad_base_datos():
        return 1
    
    # Inicializar usuarios y dependencias automáticamente
    with app.app_context():
        try:
            inicializar_usuarios_y_dependencias()
            print("[INFO] Usuarios y dependencias verificados/creados automáticamente")
        except Exception as e:
            app_logger.error(f"Error al inicializar usuarios: {str(e)}")
            print(f"[ADVERTENCIA] Error al inicializar usuarios: {str(e)}")

        try:
            poblar_catalogo_combustible()
            print("[INFO] Catálogo de vehículos/operadores y costo de combustible verificados/creados")
        except Exception as e:
            app_logger.error(f"Error al poblar catálogo de combustible: {str(e)}")
            print(f"[ADVERTENCIA] Error al poblar catálogo de combustible: {str(e)}")

        try:
            limpiar_catalogos_genericos()
            print("[INFO] Vehículos genéricos/inventados de pruebas anteriores depurados (si existían)")
        except Exception as e:
            app_logger.error(f"Error al limpiar catálogos genéricos: {str(e)}")
            print(f"[ADVERTENCIA] Error al limpiar catálogos genéricos: {str(e)}")

        try:
            importar_flota_real()
            print("[INFO] Padrón real del parque vehicular municipal verificado/importado")
        except Exception as e:
            app_logger.error(f"Error al importar el padrón real de la flota: {str(e)}")
            print(f"[ADVERTENCIA] Error al importar el padrón real de la flota: {str(e)}")

        try:
            poblar_catalogo_fase2()
            print("[INFO] Catálogos FASE 2 (Equipo por Horómetro desde padrón real, Conductor, Motivo, Área, Gasolinera) verificados/creados")
        except Exception as e:
            app_logger.error(f"Error al poblar catálogos Fase 2: {str(e)}")
            print(f"[ADVERTENCIA] Error al poblar catálogos Fase 2: {str(e)}")

        # ORDEN TÉCNICA MAESTRA (VACIADO A CEROS PARA OPERACIÓN MUNICIPAL
        # LIMPIA): ya NO se ejecuta poblar_abasto_inicial() en el arranque.
        # Esa función reponía automáticamente 1,000 L cada vez que la
        # tabla de abastos quedaba vacía, lo cual revertía cualquier
        # vaciado intencional a 0 L. El Tanque Principal (Gasolina,
        # Diésel y Urea) debe permanecer en 0.0 L hasta que el personal
        # de Servicios Públicos registre un abasto REAL desde el panel.
        print("[INFO] Tanque Principal (Gasolina/Diésel/Urea) en 0.0 L: auto-relleno deshabilitado, operación municipal limpia")

        # NOTA DE LIMPIEZA (ORDEN TÉCNICA MAESTRA, punto 4): ya NO se
        # ejecuta poblar_datos_demo_combustible() en el arranque (sembraba
        # 18 bitácoras físicas ficticias ligadas a vehículos inventados).
        # ORDEN TÉCNICA MAESTRA (VACIADO A CEROS): tampoco se ejecuta ya
        # poblar_datos_demo_asignaciones(), que creaba una Asignación de
        # Combustible "de ejemplo" con 0 L reales vinculada a la primera
        # unidad oficial del padrón. Los vales/autorizaciones deben
        # permanecer en cero absoluto hasta la primera operación real
        # capturada por el personal durante las pruebas de campo.
    
    # Configurar entorno
    host, port, modo_depuracion, nivel_log = configurar_entorno_produccion()
    
    print(f"\n[INFO] MODO: {nivel_log}")
    print(f"[INFO] ACCESO: http://{host}:{port}")
    print(f"[INFO] DATOS: {os.path.join(obtener_ruta_base_datos(), 'apoyos.db')}")
    print(f"[INFO] ARCHIVOS: {obtener_ruta_uploads()}")
    print("\n[INFO] Iniciando servidor... (Ctrl+C para detener)")

    
    # Configurar manejo de errores en producción
    if not modo_depuracion:
        app.config['PROPAGATE_EXCEPTIONS'] = False
        app.config['TRAP_HTTP_EXCEPTIONS'] = True
    
    # Detectar si se ejecuta como ejecutable compilado (PyInstaller)
    es_ejecutable = getattr(sys, 'frozen', False)
    
    # Abrir el navegador automáticamente después de un breve retraso,
    # solo cuando se ejecuta como .exe (evita doble apertura por el reloader de Flask)
    if es_ejecutable:
        def abrir_navegador():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=abrir_navegador, daemon=True).start()
    
    # Iniciar servidor con configuración optimizada
    # use_reloader se desactiva en el ejecutable porque PyInstaller no soporta
    # reinicio automático del proceso (no hay archivo .py que vigilar)
    try:
        app.run(
            host=host,
            port=port,
            debug=modo_depuracion and not es_ejecutable,
            threaded=True,
            use_reloader=not es_ejecutable
        )

    except KeyboardInterrupt:
        print("\n[INFO] Servidor detenido por el operador.")
        return 0
    except Exception as e:
        app_logger.critical(f"Error crítico al iniciar servidor: {str(e)}")
        print(f"[ERROR] ERROR CRÍTICO: {str(e)}")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())