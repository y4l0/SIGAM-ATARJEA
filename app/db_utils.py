"""
Utilidades para operaciones de base de datos con manejo de excepciones.
"""
import functools
from contextlib import contextmanager
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


@contextmanager
def transaccion_segura(descripcion="operación de base de datos"):
    """
    BLINDAJE DE ROBLE - TRANSACCIÓN SEGURA: context manager que envuelve
    un bloque de escrituras SQLAlchemy en una transacción con rollback
    automático ante cualquier excepción, garantizando que ningún error
    futuro (de red, de validación, de concurrencia, etc.) deje tablas a
    medio escribir, vacías o corrompidas.

    Uso:
        with transaccion_segura("registro de nueva solicitud"):
            db.session.add(nueva_solicitud)
            db.session.add(auditoria)
            # el commit() final lo realiza este context manager

    Si ocurre una excepción dentro del bloque `with`, se ejecuta
    SIEMPRE `db.session.rollback()` antes de relanzar la excepción
    original hacia el llamador (para que la ruta Flask que invoque esto
    pueda decidir el mensaje al usuario), evitando que una sesión
    corrupta de SQLAlchemy contamine la siguiente petición HTTP.
    """
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        db_logger.error(f"Error en transacción segura ({descripcion}): {str(e)}")
        raise