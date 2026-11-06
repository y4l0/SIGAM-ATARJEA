"""
Módulo de configuración de logging para el Sistema de Apoyos Municipales.
Proporciona funciones para configurar y obtener loggers personalizados.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# Configuración global
LOG_FORMAT = '%(asctime)s [%(levelname)s] - %(name)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_DIR = 'logs'
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# Asegurar que el directorio de logs exista
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """
    Obtiene un logger configurado con el nombre especificado.
    
    Args:
        name: Nombre del logger (generalmente __name__ del módulo)
        log_file: Nombre del archivo de log (opcional, por defecto usa el nombre del logger)
    
    Returns:
        Un objeto logger configurado
    """
    logger = logging.getLogger(name)
    
    # Evitar configurar el mismo logger múltiples veces
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # Formato para todos los handlers
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    
    # Handler para archivo
    if log_file is None:
        log_file = f"{name.replace('.', '_')}.log"
    
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_file),
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Handler para consola con nivel WARNING para no saturar la terminal
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    
    # Agregar handlers al logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Logger principal de la aplicación
app_logger = get_logger('sistema_apoyos', 'sistema_apoyos.log')

# Logger específico para auditoría (acciones de usuarios)
audit_logger = get_logger('sistema_apoyos.audit', 'audit.log')

# Logger específico para errores de base de datos
db_logger = get_logger('sistema_apoyos.database', 'database.log')

# Logger específico para errores de seguridad
security_logger = get_logger('sistema_apoyos.security', 'security.log')