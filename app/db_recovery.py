from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import os
import shutil
import time
from datetime import datetime
from app.models import db

def verificar_conexion_bd() -> bool:
    """
    Verifica si la conexión a la base de datos está funcionando.
    
    Returns:
        bool: True si la conexión está activa, False en caso contrario
    """
    try:
        # Intenta ejecutar una consulta simple usando text()
        db.session.execute(text("SELECT 1")).scalar()
        return True
    except SQLAlchemyError as e:
        current_app.logger.error(f"Error de conexión a la base de datos: {str(e)}")
        return False
    except Exception as e:
        current_app.logger.error(f"Error inesperado al verificar conexión: {str(e)}")
        return False

def intentar_reconexion() -> bool:
    """
    Intenta reconectar a la base de datos después de un error.
    
    Returns:
        bool: True si la reconexión fue exitosa, False en caso contrario
    """
    try:
        # Cerrar la sesión actual
        db.session.remove()
        
        # Esperar un momento antes de intentar reconectar
        time.sleep(1)
        
        # Intentar una consulta simple para verificar la reconexión usando text()
        db.session.execute(text("SELECT 1")).scalar()
        current_app.logger.info("Reconexión a la base de datos exitosa")
        return True
    except SQLAlchemyError as e:
        current_app.logger.error(f"Error al intentar reconectar a la base de datos: {str(e)}")
        return False
    except Exception as e:
        current_app.logger.error(f"Error inesperado al intentar reconectar: {str(e)}")
        return False

def crear_backup_bd() -> bool:
    """
    Crea una copia de seguridad de la base de datos.
    
    Returns:
        bool: True si el backup fue exitoso, False en caso contrario
    """
    try:
        # Obtener la ruta de la base de datos
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        
        # Verificar que el archivo existe
        if not os.path.exists(db_path):
            current_app.logger.error(f"No se encontró el archivo de base de datos: {db_path}")
            return False
        
        # Crear directorio de backups si no existe
        backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        # Crear nombre de archivo con timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"apoyos_backup_{timestamp}.db")
        
        # Copiar el archivo
        shutil.copy2(db_path, backup_path)
        current_app.logger.info(f"Backup de base de datos creado: {backup_path}")
        return True
    except Exception as e:
        current_app.logger.error(f"Error al crear backup de la base de datos: {str(e)}")
        return False

def recuperar_base_datos() -> bool:
    """
    Intenta recuperar la base de datos después de un error.
    
    Returns:
        bool: True si la recuperación fue exitosa, False en caso contrario
    """
    try:
        # Crear backup antes de intentar recuperar
        crear_backup_bd()
        
        # Intentar reconectar
        if intentar_reconexion():
            return True
        
        # Si la reconexión falla, intentar recrear las tablas
        current_app.logger.warning("Intentando recrear las tablas de la base de datos...")
        db.create_all()
        
        # Verificar si la recuperación fue exitosa
        if verificar_conexion_bd():
            current_app.logger.info("Base de datos recuperada exitosamente")
            return True
        else:
            current_app.logger.error("No se pudo recuperar la base de datos")
            return False
    except Exception as e:
        current_app.logger.error(f"Error al intentar recuperar la base de datos: {str(e)}")
        return False