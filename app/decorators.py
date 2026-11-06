from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user
from .models import db, Solicitud, Dependencia

def roles_required(*roles):
    """
    Decorador para verificar que el usuario tenga al menos uno de los roles especificados.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debe iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('main.login', next=request.url))
            
            if current_user.rol not in roles:
                flash('No tiene permisos suficientes para acceder a esta página.', 'danger')
                return redirect(url_for('main.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """
    Decorador para verificar que el usuario sea administrador.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        
        if not current_user.es_admin():
            flash('Acceso restringido. Se requieren permisos de administrador.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def director_required(f):
    """
    Decorador para verificar que el usuario sea director o administrador.

    CORRECCIÓN CRÍTICA (ORDEN TÉCNICA MAESTRA - CERO CAÍDAS): este
    decorador retornaba `decorator` (una variable inexistente en este
    scope, perteneciente a la función `roles_required` de más arriba),
    lo que provocaba un NameError real (colapso 500) en cuanto se
    aplicara @director_required a cualquier ruta. Se corrige para
    retornar `decorated_function`, igual que el resto de decoradores.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        
        if not (current_user.es_admin() or current_user.es_director()):
            flash('Acceso restringido. Se requieren permisos de director o administrador.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def operador_required(f):
    """
    Decorador para verificar que el usuario sea operador, director o administrador.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        
        if not (current_user.es_admin() or current_user.es_director() or current_user.es_operador()):
            flash('Acceso restringido. Se requieren permisos de operador o superior.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def servicios_publicos_required(f):
    """
    Decorador para el Módulo de Servicios Públicos (Control de Combustible).
    Acceso exclusivo para el rol 'ServiciosPublicos', y además visible para
    el Alcalde (Presidente) y el Administrador, ya que el dashboard de
    alertas de rendimiento debe ser consultado por la autoridad municipal.
    Ningún otro rol social (Director/Operador de otras áreas) tiene acceso.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))

        if not (current_user.es_admin() or current_user.es_presidente() or current_user.es_servicios_publicos()):
            flash('Acceso restringido. Este módulo es exclusivo de Servicios Públicos.', 'danger')
            return redirect(url_for('main.dashboard'))

        return f(*args, **kwargs)
    return decorated_function

def finanzas_combustible_required(f):
    """
    Decorador para la sección de 'Cuentas y Balance Financiero' del
    Módulo de Combustible. Visible únicamente para el rol de
    administración (Admin) o la Alcaldía (Presidente), nunca para el
    rol operativo ServiciosPublicos (que solo captura despachos).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))

        if not (current_user.es_admin() or current_user.es_presidente()):
            flash('Acceso restringido. Esta sección es exclusiva de Administración/Alcaldía.', 'danger')
            return redirect(url_for('main.servicios_publicos'))

        return f(*args, **kwargs)
    return decorated_function

def dependencia_required(f):
    """
    Decorador para verificar que el usuario tenga una dependencia asignada.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        
        if not current_user.es_admin() and not current_user.dependencia_id:
            flash('Su cuenta no tiene una dependencia asignada. Contacte al administrador.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def verificar_permiso_solicitud(f):
    """
    Decorador para verificar que el usuario tenga permiso para acceder a una solicitud específica.
    Los administradores pueden ver todas las solicitudes.
    Los directores solo pueden ver las solicitudes de su dependencia.
    Los operadores solo pueden ver las solicitudes que ellos crearon.
    """
    @wraps(f)
    def decorated_function(solicitud_id, *args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        
        # Obtener la solicitud
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Administradores pueden ver todo
        if current_user.es_admin():
            return f(solicitud_id, *args, **kwargs)
        
        # Directores pueden ver solo las solicitudes de su dependencia
        if current_user.es_director():
            if solicitud.dependencia_id != current_user.dependencia_id:
                flash('No tiene permisos para acceder a esta solicitud.', 'danger')
                return redirect(url_for('main.solicitudes'))
            return f(solicitud_id, *args, **kwargs)
        
        # Operadores pueden ver solo las solicitudes que ellos crearon
        if current_user.es_operador():
            if solicitud.usuario_id != current_user.id:
                flash('No tiene permisos para acceder a esta solicitud.', 'danger')
                return redirect(url_for('main.solicitudes'))
            return f(solicitud_id, *args, **kwargs)
        
        # Si no cumple con ningún rol, denegar acceso
        flash('No tiene permisos para acceder a esta solicitud.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return decorated_function

def registrar_auditoria(accion, tabla=None, registro_id=None, detalles=None):
    """
    Función para registrar acciones de auditoría en el sistema.

    BLINDAJE DE ROBLE: esta función se invoca dentro de rutas que YA
    completaron su operación principal; si el registro de auditoría
    fallara sin este try/except, el error se propagaría hacia arriba
    y podría convertir una operación exitosa en un Error 500. Nunca
    debe bloquear la acción que originó la auditoría.
    """
    from .models import AuditoriaLog, db
    from .logger_config import app_logger
    from datetime import datetime

    if current_user.is_authenticated:
        try:
            auditoria = AuditoriaLog(
                user_id=current_user.id,
                accion=accion,
                tabla_afectada=tabla or 'sistema',
                registro_id=str(registro_id) if registro_id else None,
                detalle_cambio=detalles,
                ip_address=request.remote_addr,
                fecha=datetime.utcnow()
            )
            db.session.add(auditoria)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app_logger.error(f"Error al registrar auditoría ({accion}): {str(e)}")

def verificar_acceso_dependencia(dependencia_id):
    """
    Verifica que el usuario tenga acceso a una dependencia específica.
    Los administradores tienen acceso a todas las dependencias.
    Los directores solo tienen acceso a su propia dependencia.
    """
    if current_user.es_admin():
        return True
    
    if current_user.es_director():
        return current_user.dependencia_id == dependencia_id
    
    return False

def filtrar_solicitudes_por_rol():
    """
    AISLAMIENTO ESTRICTO POR ROL (ORDEN TÉCNICA MAESTRA): filtra las
    solicitudes según el rol del usuario autenticado, garantizando que
    un Director JAMÁS vea la actividad de otra dependencia.

    CORRECCIÓN CRÍTICA: esta función ya existía pero (a) nunca se
    invocaba desde las vistas reales de /dashboard ni /solicitudes
    (por lo que CUALQUIER Director veía TODAS las solicitudes de TODAS
    las dependencias, un hueco de seguridad real) y (b) no contemplaba
    al rol Presidente (Alcalde), que debe tener la misma visibilidad
    total que Admin al ser la máxima autoridad ejecutiva.

    Retorna una consulta SQLAlchemy filtrada.
    """
    from .models import Solicitud

    if current_user.es_admin() or current_user.es_presidente():
        # Administración/Alcaldía ven todas las solicitudes (visión ejecutiva total)
        return Solicitud.query

    elif current_user.es_director():
        # Directores ven ÚNICA Y EXCLUSIVAMENTE las solicitudes de su propia dependencia
        return Solicitud.query.filter_by(dependencia_id=current_user.dependencia_id)

    elif current_user.es_operador():
        # Operadores ven solo las solicitudes que ellos crearon
        return Solicitud.query.filter_by(usuario_id=current_user.id)

    else:
        # Usuarios sin rol específico no ven nada
        return Solicitud.query.filter_by(id=None)