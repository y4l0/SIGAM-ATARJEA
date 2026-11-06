"""
Utilidades para operaciones de base de datos con manejo de excepciones.
"""
import functools
from typing import Any, Callable, TypeVar, cast
from sqlalchemy.exc import SQLAlchemyError
from app.logger_config import db_logger
from app import db

# Definición de tipos para el decorador
F = TypeVar('F', bound=Callable[..., Any])

def db_operation(f: F) -> F:
    """
    Decorador que envuelve una función que realiza operaciones de base de datos.
    Maneja automáticamente las excepciones y realiza rollback en caso de error.
    
    Args:
        f: La función a decorar
        
    Returns:
        La función decorada con manejo de excepciones y rollback
    """
    @functools.wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        try:
            result = f(*args, **kwargs)
            return result
        except SQLAlchemyError as e:
            db.session.rollback()
            db_logger.error(f"Error en operación de base de datos: {str(e)}")
            raise
        except Exception as e:
            db.session.rollback()
            db_logger.error(f"Error inesperado en operación de base de datos: {str(e)}")
            raise
    
    return cast(F, decorated_function)

def safe_commit() -> bool:
    """
    Realiza un commit seguro con manejo de excepciones y rollback automático.
    
    Returns:
        True si el commit fue exitoso, False en caso contrario
    """
    try:
        db.session.commit()
        return True
    except SQLAlchemyError as e:
        db.session.rollback()
        db_logger.error(f"Error al realizar commit: {str(e)}")
        return False
    except Exception as e:
        db.session.rollback()
        db_logger.error(f"Error inesperado al realizar commit: {str(e)}")
        return False