from flask import Flask, render_template, request
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
import os
import sys
import logging
from .models import db, Usuario
from .logger_config import app_logger
from config import Config
from config_paths import obtener_ruta_base_app, obtener_ruta_base_datos

login_manager = LoginManager()
oauth = OAuth()


def _migrar_columnas_solicitud(app):
    """
    DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO: agrega, mediante
    ALTER TABLE, las columnas Monto_Federal/Monto_Estatal/Monto_Municipal/
    Monto_Beneficiario a la tabla 'solicitudes' si todavía no existen
    (bases de datos creadas antes de este cambio). db.create_all() NUNCA
    modifica tablas que ya existen, por lo que esta migración manual es
    necesaria. Es idempotente y segura de ejecutar en cada arranque.
    """
    import sqlite3

    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite:///'):
        return  # Migración manual solo aplica a SQLite

    ruta_db = uri.replace('sqlite:///', '', 1)
    if not os.path.exists(ruta_db):
        return  # La tabla se creará desde cero con db.create_all()

    columnas_nuevas = {
        'Monto_Federal': 'NUMERIC(10, 2) DEFAULT 0',
        'Monto_Estatal': 'NUMERIC(10, 2) DEFAULT 0',
        'Monto_Municipal': 'NUMERIC(10, 2) DEFAULT 0',
        'Monto_Beneficiario': 'NUMERIC(10, 2) DEFAULT 0',
        # MONTOS ESTIMADOS Y CLASIFICACIÓN DE BENEFICIARIOS (nuevas columnas)
        'Monto_Estimado': 'NUMERIC(10, 2) DEFAULT 0',
        'Tipo_Beneficiario': "VARCHAR(20) DEFAULT 'Particular'",
    }

    conn = sqlite3.connect(ruta_db)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitudes'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(solicitudes)")
        existentes = {fila[1] for fila in cursor.fetchall()}
        for columna, tipo in columnas_nuevas.items():
            if columna not in existentes:
                cursor.execute(f"ALTER TABLE solicitudes ADD COLUMN {columna} {tipo}")
                app_logger.info(f"Columna '{columna}' agregada a 'solicitudes'")
        conn.commit()
    finally:
        conn.close()


def _migrar_columnas_asignacion_combustible(app):
    """
    UNIFICACIÓN CON EL REGISTRO GENERAL DE APOYOS: agrega, mediante
    ALTER TABLE, las columnas de Tipo de Beneficiario, desglose de
    Montos por Fuente de Financiamiento y Monto Estimado a la tabla
    'asignaciones_combustible' si todavía no existen (bases de datos
    creadas antes de este cambio). Idempotente y segura de ejecutar en
    cada arranque, igual que _migrar_columnas_solicitud().
    """
    import sqlite3

    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite:///'):
        return

    ruta_db = uri.replace('sqlite:///', '', 1)
    if not os.path.exists(ruta_db):
        return

    columnas_nuevas = {
        'tipo_beneficiario': "VARCHAR(20) DEFAULT 'Particular'",
        'monto_federal': 'NUMERIC(10, 2) DEFAULT 0',
        'monto_estatal': 'NUMERIC(10, 2) DEFAULT 0',
        'monto_municipal': 'NUMERIC(10, 2) DEFAULT 0',
        'monto_beneficiario': 'NUMERIC(10, 2) DEFAULT 0',
        'monto_general': 'NUMERIC(10, 2) DEFAULT 0',
        'monto_estimado': 'NUMERIC(10, 2) DEFAULT 0',
    }

    conn = sqlite3.connect(ruta_db)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='asignaciones_combustible'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(asignaciones_combustible)")
        existentes = {fila[1] for fila in cursor.fetchall()}
        for columna, tipo in columnas_nuevas.items():
            if columna not in existentes:
                cursor.execute(f"ALTER TABLE asignaciones_combustible ADD COLUMN {columna} {tipo}")
                app_logger.info(f"Columna '{columna}' agregada a 'asignaciones_combustible'")
        conn.commit()
    finally:
        conn.close()


def create_app():
    # Rutas absolutas a templates/static. Necesario porque cuando el sistema
    # corre como ejecutable PyInstaller (--onefile), estos archivos se
    # extraen a una carpeta temporal (sys._MEIPASS) y las rutas relativas
    # ('../templates') dejan de coincidir con la ubicación real, causando
    # que Flask no encuentre las plantillas y arroje errores 500/404.
    _base = obtener_ruta_base_app()
    app = Flask(__name__,
                template_folder=os.path.join(_base, 'templates'),
                static_folder=os.path.join(_base, 'static'))
    
    # Configuración desde nuestro módulo config
    app.config.from_object(Config)
    
    # Asegurar que existe el directorio de la base de datos (ruta persistente y portable)
    obtener_ruta_base_datos()

    
    # Inicializar extensiones con configuración de pool
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # Inicializar Authlib OAuth y registrar el proveedor Google
    # (autenticación con Gmail / Google Workspace para directores)
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url=app.config.get('GOOGLE_DISCOVERY_URL'),
        client_kwargs={'scope': 'openid email profile'}
    )

    
    # Inicializar configuración del sistema DESPUÉS de inicializar la base de datos
    with app.app_context():
        try:
            Config.init_config()
        except Exception as e:
            app_logger.warning(f"Error al inicializar configuración: {str(e)}")

        # DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO: garantiza que
        # las 4 columnas nuevas (Monto_Federal, Monto_Estatal,
        # Monto_Municipal, Monto_Beneficiario) existan en la tabla
        # 'solicitudes' SIEMPRE que se cree la app (tanto al arrancar
        # run.py como en pruebas automatizadas que llaman a
        # create_app() directamente), sin afectar los registros ya
        # guardados. Es seguro ejecutarlo múltiples veces.
        try:
            _migrar_columnas_solicitud(app)
        except Exception as e:
            app_logger.warning(f"Error al migrar columnas de 'solicitudes': {str(e)}")

        # UNIFICACIÓN CON EL REGISTRO GENERAL DE APOYOS: garantiza que las
        # columnas nuevas (tipo_beneficiario, desglose de montos y monto
        # estimado) existan en 'asignaciones_combustible' SIEMPRE que se
        # cree la app, igual que con 'solicitudes'.
        try:
            _migrar_columnas_asignacion_combustible(app)
        except Exception as e:
            app_logger.warning(f"Error al migrar columnas de 'asignaciones_combustible': {str(e)}")

        # Crea tablas NUEVAS que no existan todavía (ej.
        # adjuntos_asignacion_combustible) sin afectar las tablas ya
        # existentes. Complementa la migración manual de ALTER TABLE de
        # arriba (que sí cubre columnas nuevas en tablas existentes).
        try:
            db.create_all()
        except Exception as e:
            app_logger.warning(f"Error al verificar/crear tablas nuevas: {str(e)}")

    # Registrar manejadores de errores personalizados
    @app.errorhandler(404)
    def pagina_no_encontrada(error):
        app_logger.warning(f"Error 404: {request.path}")
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def error_interno_servidor(error):
        app_logger.debug(f"Error 500: {str(error)}")
        return render_template('500.html'), 500
    
    @app.errorhandler(403)
    def acceso_denegado(error):
        app_logger.warning(f"Error 403: Acceso denegado")
        return render_template('error.html', 
                             title="Acceso Denegado",
                             error="No tiene permisos para acceder a este recurso."), 403
    
    @app.errorhandler(400)
    def solicitud_erronea(error):
        app_logger.warning(f"Error 400: Solicitud incorrecta")
        return render_template('error.html',
                             title="Solicitud Incorrecta",
                             error="La solicitud contiene datos inválidos o incompletos."), 400
    
    # Manejo de excepciones generales
    @app.errorhandler(Exception)
    def manejo_excepcion_general(error):
        app_logger.critical(f"Excepción no manejada: {str(error)}", exc_info=True)
        if app.config.get('DEBUG', False):
            raise error
        return render_template('500.html'), 500
    
    # BLINDAJE DE ROBLE: garantiza que, al finalizar cada petición HTTP
    # (incluso si terminó con una excepción no manejada), la sesión de
    # SQLAlchemy se cierre y haga rollback de cualquier transacción que
    # hubiera quedado abierta. Sin esto, un error a medio camino en una
    # petición podría dejar objetos "sucios" en la sesión que
    # contaminen silenciosamente la siguiente petición HTTP, generando
    # escrituras parciales o inconsistentes en la base de datos.
    @app.teardown_appcontext
    def _cerrar_sesion_bd(excepcion=None):
        if excepcion is not None:
            try:
                db.session.rollback()
            except Exception:
                pass
        db.session.remove()

    # Registrar rutas
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    # Configurar SQLite con WAL para concurrencia
    if app.config['SQLITE_WAL_ENABLED']:
        try:
            from config import setup_sqlite_wal
            setup_sqlite_wal()
            app_logger.info("SQLite configurado con modo WAL para concurrencia")
        except Exception as e:
            app_logger.warning(f"Error configurando SQLite WAL: {str(e)}")
    
    # Configurar logging de la aplicación
    if not app.debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        app.logger.addHandler(stream_handler)
    
    return app