import os
from datetime import datetime
from config_paths import (
    obtener_ruta_base_app,
    obtener_ruta_base_datos,
    obtener_ruta_uploads,
    obtener_ruta_expedientes,
)

class Config:
    """Configuración principal del Sistema SIGEM"""

    # Rutas absolutas y portables: funcionan igual como script de Python
    # o como ejecutable compilado con PyInstaller, sin importar desde qué
    # directorio se invoque el programa.
    _RUTA_BASE_DATOS = obtener_ruta_base_datos()
    _RUTA_UPLOADS = obtener_ruta_uploads()

    # Configuración de base de datos SQLite con WAL (Write-Ahead Logging)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(_RUTA_BASE_DATOS, "apoyos.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    
    # Configuración de concurrencia SQLite
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'check_same_thread': False,
            'timeout': 10
        }
    }
    
    # Configuración WAL para soportar múltiples usuarios simultáneamente
    SQLITE_WAL_ENABLED = True
    SQLITE_JOURNAL_MODE = 'WAL'  # Write-Ahead Logging para mejor concurrencia
    
    # Configuración de seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sistema-apoyos-municipales-secret-key'
    
    # Configuración de sesión
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    
    # Configuración de archivos (rutas absolutas y portables: funcionan
    # igual en desarrollo y como ejecutable PyInstaller, sin depender del
    # directorio de trabajo actual del proceso)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB límite máximo
    UPLOAD_FOLDER = _RUTA_UPLOADS
    UPLOAD_SOLICITUDES = os.path.join(_RUTA_UPLOADS, 'solicitudes')
    UPLOAD_EXPEDIENTES = os.path.join(_RUTA_UPLOADS, 'expedientes')
    UPLOAD_FOLDER_IDENTIFICACIONES = os.path.join(_RUTA_UPLOADS, 'identificaciones')
    UPLOAD_FOLDER_COMPROBANTES = os.path.join(_RUTA_UPLOADS, 'comprobantes')
    UPLOAD_FOLDER_EVIDENCIAS = os.path.join(_RUTA_UPLOADS, 'evidencias')
    UPLOAD_FOLDER_COMBUSTIBLE = os.path.join(_RUTA_UPLOADS, 'combustible')
    
    # Configuración del sistema: carpeta de expedientes de auditoría en el
    # Escritorio del usuario (nombre solicitado: Expedientes_SIGMA)
    EXPEDIENTE_AUDITORIA_PATH = obtener_ruta_expedientes()

    
    # Configuración de roles
    ADMIN_ROLE = "Admin"
    DIRECTOR_ROLE = "Director"
    OPERADOR_ROLE = "Operador"
    
    # Configuración de folios
    FOLIO_INICIAL = "1900006757"
    FOLIO_FORMATO = "ATJ-2026-XXXX"
    
    # Configuración de auditoría
    AUDITORIA_ACTIVA = True
    REGISTRO_IP = True

    # Configuración de autenticación con Google (OAuth 2.0)
    # Las credenciales deben obtenerse en https://console.cloud.google.com/apis/credentials
    # y definirse como variables de entorno del sistema para NUNCA exponerlas en el
    # código fuente (buena práctica de seguridad institucional).
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_DISCOVERY_URL = 'https://accounts.google.com/.well-known/openid-configuration'

    
    @staticmethod
    def init_config():
        """Inicializa la configuración del sistema"""
        # Crear directorios necesarios
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.UPLOAD_SOLICITUDES, exist_ok=True)
        os.makedirs(Config.UPLOAD_EXPEDIENTES, exist_ok=True)
        os.makedirs(Config.EXPEDIENTE_AUDITORIA_PATH, exist_ok=True)
        os.makedirs(Config.UPLOAD_FOLDER_COMBUSTIBLE, exist_ok=True)

class DatabaseConfig:
    """Configuración específica para la base de datos"""
    
    # Parámetros de conexión para múltiples usuarios concurrentes
    CONNECTION_PARAMS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_recycle': 3600,
        'pool_pre_ping': True
    }
    
    # Parámetros SQLite para concurrencia optimizada
    SQLITE_PARAMS = {
        'journal_mode': 'wal',
        'synchronous': 'normal',
        'temp_store': 'memory',
        'cache_size': -2000  # 2MB cache
    }

class AuditConfig:
    """Configuración de auditoría"""
    
    LOG_FILE = 'logs/audit.log'
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Tipos de acciones registradas
    ACTION_TYPES = {
        'CREATE': 'Creación',
        'UPDATE': 'Actualización',
        'DELETE': 'Eliminación',
        'READ': 'Consulta',
        'DOWNLOAD': 'Descarga',
        'APPROVE': 'Aprobación',
        'REJECT': 'Rechazo'
    }

def setup_sqlite_wal():
    """Configura SQLite en modo WAL para mejor concurrencia"""
    from sqlalchemy import create_engine, text
    
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    connection = engine.connect()
    
    try:
        connection.execute(text(f"PRAGMA journal_mode = {Config.SQLITE_JOURNAL_MODE}"))
        connection.execute(text("PRAGMA synchronous = NORMAL"))
        connection.execute(text("PRAGMA wal_autocheckpoint = 1000"))
        connection.execute(text("PRAGMA cache_size = -2000"))
        connection.execute(text("PRAGMA temp_store = MEMORY"))
        
        print("SQLite configurado en modo WAL para concurrencia optimizada")
    except Exception as e:
        print(f"Error configurando SQLite WAL: {e}")
    finally:
        connection.close()