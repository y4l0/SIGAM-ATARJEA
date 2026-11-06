"""
Utilidades para autenticación y autorización con manejo de excepciones.
"""
import functools
from typing import Any, Callable, TypeVar, cast, Optional
from flask import redirect, url_for, flash, request, current_app
from flask_login import current_user
from app.logger_config import security_logger

# Definición de tipos para el decorador
F = TypeVar('F', bound=Callable[..., Any])

def role_required(role: str) -> Callable[[F], F]:
    """
    Decorador que verifica si el usuario tiene el rol requerido.
    Maneja automáticamente los casos donde el usuario no está autenticado.
    
    Args:
        role: El rol requerido para acceder a la ruta
        
    Returns:
        Un decorador que verifica el rol del usuario
    """
    def decorator(f: F) -> F:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # Verificar si el usuario está autenticado
            if not current_user.is_authenticated:
                security_logger.warning(f"Intento de acceso sin autenticación a {request.path}")
                flash('Debe iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('main.login', next=request.url))
            
            # Verificar si el usuario tiene el rol requerido
            if not hasattr(current_user, 'role') or current_user.role != role:
                security_logger.warning(
                    f"Usuario {getattr(current_user, 'id', 'desconocido')} "
                    f"intentó acceder a {request.path} sin el rol requerido ({role})"
                )
                flash('No tiene permisos para acceder a esta página.', 'danger')
                return redirect(url_for('main.dashboard'))
                
            return f(*args, **kwargs)
        
        return cast(F, decorated_function)
    
    return decorator

def admin_required(f: F) -> F:
    """
    Decorador que verifica si el usuario es administrador.
    
    Args:
        f: La función a decorar
        
    Returns:
        La función decorada con verificación de rol de administrador
    """
    return role_required('Admin')(f)

def director_required(f: F) -> F:
    """
    Decorador que verifica si el usuario es director.
    
    Args:
        f: La función a decorar
        
    Returns:
        La función decorada con verificación de rol de director
    """
    return role_required('Director')(f)

def get_user_id() -> Optional[int]:
    """
    Obtiene el ID del usuario actual de forma segura.
    
    Returns:
        El ID del usuario si está autenticado, None en caso contrario
    """
    if current_user.is_authenticated and hasattr(current_user, 'id'):
        return current_user.id
    return None