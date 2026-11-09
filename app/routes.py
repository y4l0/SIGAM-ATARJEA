from flask import Blueprint, render_template, redirect, url_for, flash, request, session, send_file, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from .models import (db, Usuario, Ciudadano, Solicitud, Comunidad, Dependencia, AdjuntoSolicitud,
                      TipoDocumentoMunicipal, AuditLog, AuditoriaLog, CierreEjercicio, BitacoraCombustible,
                      TipoBitacoraEnum, VehiculoMunicipal, OperadorMunicipal, ConfiguracionCombustible,
                      Unidad, Equipo, Conductor, Autorizador, Despachador, Motivo, Area, Gasolinera,
                      ConfiguracionUmbrales, RegistroAbasto, BitacoraSistemaLog,
                      AsignacionCombustible, EstatusAsignacionEnum,
                      SubtipoMaquinariaEnum, SubtipoCiudadanoEnum, DestinoApoyoAguaEnum,
                      TipoFluidoEnum, ConfiguracionTanque, RegistroAbastoFluido)
from .decorators import admin_required, servicios_publicos_required, finanzas_combustible_required, filtrar_solicitudes_por_rol
from .combustible_logic import evaluar_registro
from .backup_utils import (
    respaldar_en_escritorio, generar_paquete_diario_json, importar_paquete_json,
    obtener_ruta_respaldos_escritorio,
)

import shutil
from datetime import datetime, timedelta
from sqlalchemy import or_, func
import os
import sys
# Preparación portable: detección automática de rutas (funciona en cualquier PC)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_paths import obtener_ruta_expedientes

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from copy import copy
from io import BytesIO
import tempfile
from config_paths import obtener_ruta_base_app

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

main = Blueprint('main', __name__)

# ORDEN TÉCNICA MAESTRA - IMPRESIÓN TAMAÑO OFICIO: los formatos oficiales
# del Módulo de Servicios Públicos (Formulario N° 10 de Asignación de
# Combustible y la Orden de Comisión y Solicitud de Combustible) se
# imprimen en tamaño Oficio (216 x 340 mm), el papel usado oficialmente
# en documentos gubernamentales en México, en lugar del tamaño Carta
# (letter) genérico usado por el resto del sistema.
OFICIO_PAGESIZE = (216 * mm, 340 * mm)

# Función para generar folios secuenciales automáticos
def generar_folio():
    """Genera un folio secuencial automático (base inicial: 1900006757)"""
    # Buscar el último folio generado
    ultima_solicitud = Solicitud.query.order_by(Solicitud.id.desc()).first()
    
    # Si no hay solicitudes anteriores, usar la base inicial
    if ultima_solicitud and ultima_solicitud.folio:
        ultimo_folio = ultima_solicitud.folio
        # Extraer solo los números del folio
        if ultimo_folio.isdigit():
            nuevo_numero = int(ultimo_folio) + 1
            return str(nuevo_numero)
        else:
            # Folio no es solo números, extraer números si tiene formato ATJ-XXXX
            try:
                # Buscar números después del prefijo
                if '-' in ultimo_folio:
                    partes = ultimo_folio.split('-')
                    numero = partes[-1]
                    if numero.isdigit():
                        nuevo_numero = int(numero) + 1
                        return f"{partes[0]}-{nuevo_numero}"
            except:
                pass
    
    # Base inicial según instrucción
    return "1900006757"

def generar_folio_asignacion():
    """FORMULARIO N° 10: genera un folio consecutivo tipo ASIG-2026-XXXX."""
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

# Función para verificar duplicidad de CURP entre dependencias
def verificar_duplicidad_curp(curp, usuario):
    """Verifica si un ciudadano ya tiene solicitudes registradas en otras dependencias"""
    # Buscar solicitudes del ciudadano - consulta global en toda la base de datos
    solicitudes_citizen = Solicitud.query.filter_by(CURP=curp).all()
    
    if not solicitudes_citizen:
        return None  # No hay solicitudes anteriores
    
    # Alerta por CURP cruzada - verificar si ya solicitó en esta semana
    fecha_actual = datetime.now()
    solicitudes_semana_actual = []
    
    for solicitud in solicitudes_citizen:
        # Verificar si la solicitud fue creada en los últimos 7 días
        if solicitud.Fecha_Solicitud:
            diferencia_dias = (fecha_actual - solicitud.Fecha_Solicitud).days
            if diferencia_dias <= 7:
                solicitudes_semana_actual.append(solicitud)
    
    if solicitudes_semana_actual:
        # Extraer la fecha y dependencia de la solicitud más reciente de esta semana
        ultima_solicitud_semana = solicitudes_semana_actual[-1]
        fecha_ultima = ultima_solicitud_semana.Fecha_Solicitud.strftime('%d/%m/%Y')
        
        # Determinar dependencia (buscar desde modelo si existe)
        dependencia_otra = None
        if ultima_solicitud_semana.dependencia_id:
            dependencia_obj = Dependencia.query.get(ultima_solicitud_semana.dependencia_id)
            dependencia_otra = dependencia_obj.nombre if dependencia_obj else "Dependencia desconocida"
        else:
            dependencia_otra = ultima_solicitud_semana.Dependencia if ultima_solicitud_semana.Dependencia else "Dependencia desconocida"
        
        # Generar alerta tipo flash
        return {
            "duplicados": solicitudes_semana_actual,
            "tipo": "warning",
            "mensaje": f"Atención: Este ciudadano ya solicitó apoyo en [{dependencia_otra}] el día [{fecha_ultima}]",
            "fecha": fecha_ultima,
            "dependencia": dependencia_otra
        }
    
    # Si el usuario es administrador, puede ver todo
    if usuario.es_admin():
        return {
            "duplicados": solicitudes_citizen,
            "tipo": "admin",
            "mensaje": f"Este ciudadano tiene {len(solicitudes_citizen)} solicitudes registradas en el sistema."
        }
    
    # Si el usuario es director, verificar si hay solicitudes en otras dependencias
    solicitudes_otras_deps = []
    solicitudes_su_dep = []
    
    for solicitud in solicitudes_citizen:
        if solicitud.dependencia_id != usuario.dependencia_id:
            solicitudes_otras_deps.append(solicitud)
        else:
            solicitudes_su_dep.append(solicitud)
    
    if solicitudes_otras_deps:
        # Obtener información de la solicitud más reciente en otra dependencia
        ultima_otra_dep = solicitudes_otras_deps[-1]
        dependencia_otra = Dependencia.query.get(ultima_otra_dep.dependencia_id)
        nombre_dep = dependencia_otra.nombre if dependencia_otra else "Dependencia desconocida"
        
        return {
            "duplicados": solicitudes_otras_deps,
            "tipo": "warning",
            "mensaje": f"Este ciudadano ya recibió/solicitó un apoyo el día {ultima_otra_dep.Fecha_Solicitud.strftime('%d/%m/%Y')} de la dependencia '{nombre_dep}'.",
            "solicitudes_su_dep": len(solicitudes_su_dep),
            "solicitudes_otras_deps": len(solicitudes_otras_deps)
        }
    
    return {
        "duplicados": [],
        "tipo": "info",
        "mensaje": "No se encontraron solicitudes en otras dependencias."
    }

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')

            if not email or not password:
                flash('Por favor ingrese email y contraseña.', 'warning')
                return render_template('login.html')

            # BLINDAJE 100% (ORDEN TÉCNICA MAESTRA - CERO CAÍDAS): la
            # búsqueda de usuario se hace por correo normalizado
            # (minúsculas/sin espacios) para que la autenticación nunca
            # falle por diferencias de mayúsculas entre lo capturado en
            # el formulario y lo almacenado en la base de datos.
            email_normalizado = email.strip().lower()
            user = Usuario.query.filter(func.lower(Usuario.email) == email_normalizado).first()

            if not user:
                current_app.logger.warning(f"Intento de login fallido (usuario no encontrado): {email}")
                flash('Credenciales incorrectas. Intente nuevamente.', 'danger')
                return render_template('login.html')

            if not user.activo:
                current_app.logger.warning(f"Intento de login con cuenta inactiva: {email}")
                flash('Esta cuenta se encuentra inactiva. Contacte al administrador del sistema.', 'danger')
                return render_template('login.html')

            if check_password_hash(user.password, password):
                # Autenticación real con Flask-Login para que @login_required funcione
                login_user(user, remember=True)
                current_app.logger.info(f"Login exitoso para usuario: {email}")

                # Acceso exclusivo: el rol ServiciosPublicos va directo a su Dashboard
                # de Combustible, sin visibilidad a otras áreas sociales del municipio.
                if user.es_servicios_publicos() and not user.es_admin() and not user.es_presidente():
                    return redirect(url_for('main.servicios_publicos'))

                return redirect(url_for('main.dashboard'))
            else:
                current_app.logger.warning(f"Intento de login fallido (contraseña incorrecta): {email}")
                flash('Credenciales incorrectas. Intente nuevamente.', 'danger')
                return render_template('login.html')

        return render_template('login.html')

    except Exception as e:
        # BLINDAJE 100%: ante cualquier error inesperado (ej. base de
        # datos bloqueada, columna faltante) el login NUNCA debe mostrar
        # un error 500 genérico; siempre regresa a la pantalla de login
        # con un mensaje claro para el operador, nunca "cuelga" el sistema.
        current_app.logger.error(f"Error en función login: {str(e)}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        flash('Error interno del sistema al iniciar sesión. Intente nuevamente.', 'danger')
        return render_template('login.html')

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@main.route('/registro_cuenta', methods=['GET', 'POST'])
def registro_cuenta():
    """
    REGISTRO DE CUENTAS INSTITUCIONALES (Directores): permite que un
    nuevo Director de Área se dé de alta por sí mismo capturando
    Nombre, Correo, Contraseña y su Área/Dirección (dependencia).

    BLINDAJE DE SEGURIDAD: esta ruta pública SIEMPRE crea la cuenta
    con rol "Director" de forma fija (ignorando cualquier intento de
    enviar otro valor en el formulario). Los roles Admin/Presidente/
    ServiciosPublicos/Operador solo pueden asignarse desde el panel
    interno de Administración de Usuarios (requiere ya estar
    autenticado como Admin), nunca desde el registro público.
    """
    try:
        dependencias = Dependencia.query.order_by(Dependencia.nombre.asc()).all()

        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            password2 = request.form.get('password2', '')
            dependencia_id = request.form.get('dependencia_id') or None

            if not nombre or not email or not password:
                flash('Nombre, correo electrónico y contraseña son obligatorios.', 'warning')
                return render_template('registro_cuenta.html', dependencias=dependencias)

            if not dependencia_id:
                flash('Debe seleccionar su Área/Dirección.', 'warning')
                return render_template('registro_cuenta.html', dependencias=dependencias)

            if len(password) < 8:
                flash('La contraseña debe tener al menos 8 caracteres.', 'warning')
                return render_template('registro_cuenta.html', dependencias=dependencias)

            if password != password2:
                flash('Las contraseñas no coinciden.', 'warning')
                return render_template('registro_cuenta.html', dependencias=dependencias)

            if Usuario.query.filter(func.lower(Usuario.email) == email).first():
                flash('Ya existe una cuenta registrada con ese correo electrónico.', 'danger')
                return render_template('registro_cuenta.html', dependencias=dependencias)

            nuevo_director = Usuario(
                nombre=nombre,
                email=email,
                password=generate_password_hash(password),
                rol='Director',  # SIEMPRE Director: aislamiento estricto por diseño
                dependencia_id=int(dependencia_id),
                activo=True
            )
            db.session.add(nuevo_director)
            db.session.flush()

            auditoria = AuditoriaLog(
                user_id=nuevo_director.id,
                accion="Registro de nueva cuenta institucional (Director)",
                tabla_afectada='usuarios',
                registro_id=str(nuevo_director.id),
                ip_address=request.remote_addr,
                detalle_cambio=f"Se autorregistró la cuenta '{nombre}' ({email}) para el Área/Dirección ID {dependencia_id}."
            )
            db.session.add(auditoria)
            db.session.commit()

            respaldar_en_escritorio(motivo=f"Registro de nueva cuenta: {email}", usuario_nombre=nombre)

            flash(f'Cuenta creada exitosamente para {nombre}. Ya puede iniciar sesión.', 'success')
            return redirect(url_for('main.login'))

        return render_template('registro_cuenta.html', dependencias=dependencias)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en registro de cuenta: {str(e)}", exc_info=True)
        flash('No se pudo completar el registro. Intente nuevamente.', 'danger')
        return redirect(url_for('main.login'))


@main.route('/login/google')
def login_google():
    """
    ORDEN TÉCNICA - AUTENTICACIÓN CON GOOGLE (OAUTH 2.0):
    Inicia el flujo de autenticación redirigiendo al usuario a la
    pantalla de consentimiento de Google. Al aceptar, Google redirige
    de vuelta a /login/google/authorize con el código de autorización.
    """
    from . import oauth
    try:
        redirect_uri = url_for('main.login_google_authorize', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)
    except Exception as e:
        current_app.logger.error(f"Error al iniciar autenticación con Google: {str(e)}")
        flash('No fue posible conectar con Google. Verifique la configuración OAuth del sistema.', 'danger')
        return redirect(url_for('main.login'))

@main.route('/login/google/authorize')
def login_google_authorize():
    """
    Ruta de redirección (callback) de Google OAuth 2.0.
    Captura el token, extrae el correo electrónico del perfil de Google
    y valida que dicho correo exista en la tabla Usuario. Si existe,
    inicia sesión automáticamente; si no, rechaza el acceso.
    """
    from . import oauth
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo')
        if not userinfo:
            userinfo = oauth.google.parse_id_token(token, nonce=None)

        email_google = (userinfo.get('email') if userinfo else None)

        if not email_google:
            current_app.logger.warning("Autenticación Google: no se pudo obtener el correo electrónico.")
            flash('No fue posible obtener el correo electrónico desde Google.', 'danger')
            return redirect(url_for('main.login'))

        email_google = email_google.strip().lower()

        # Validación: el correo debe existir en la tabla Usuario (case-insensitive)
        usuario = Usuario.query.filter(func.lower(Usuario.email) == email_google).first()

        if not usuario:
            current_app.logger.warning(f"Intento de login con Google no autorizado: {email_google}")
            flash('Este correo institucional no está registrado en el sistema.', 'danger')
            return redirect(url_for('main.login'))

        if not usuario.activo:
            flash('Su cuenta se encuentra inactiva. Contacte al administrador del sistema.', 'danger')
            return redirect(url_for('main.login'))

        # Autenticación exitosa con Flask-Login
        login_user(usuario, remember=True)

        # Trazabilidad total: registrar el inicio de sesión vía Google en AuditoriaLog
        auditoria = AuditoriaLog(
            user_id=usuario.id,
            accion="Inicio de sesión con Google (OAuth 2.0)",
            tabla_afectada='usuarios',
            registro_id=str(usuario.id),
            ip_address=request.remote_addr,
            detalle_cambio=f"Usuario {usuario.nombre} ({usuario.email}) inició sesión mediante Google."
        )
        db.session.add(auditoria)
        db.session.commit()

        current_app.logger.info(f"Login con Google exitoso para usuario: {email_google}")
        return redirect(url_for('main.dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en autorización de Google OAuth: {str(e)}")
        flash('Ocurrió un error al autenticar con Google. Intente nuevamente.', 'danger')
        return redirect(url_for('main.login'))


def poblar_datos_demo():
    """
    DESACTIVADO: No se generan datos ficticios en el sistema.
    Este es un sistema de auditoría real; las tablas deben reflejar
    únicamente información capturada legítimamente por los usuarios.
    """
    pass


@main.route('/dashboard')
@login_required
def dashboard():
    try:
        # Acceso exclusivo: el rol ServiciosPublicos no tiene visibilidad a
        # las demás áreas sociales del municipio, por lo que se redirige
        # siempre a su propio Dashboard de Combustible.
        if current_user.es_servicios_publicos() and not current_user.es_admin() and not current_user.es_presidente():
            return redirect(url_for('main.servicios_publicos'))

        current_app.logger.info(f"Dashboard accedido por usuario: {current_user.email}")
        
        # Mandatorio: poblar datos demo si la BD está vacía
        poblar_datos_demo()
        
        # AISLAMIENTO ESTRICTO POR ROL (ORDEN TÉCNICA MAESTRA): un
        # Director NUNCA debe ver la actividad de otras dependencias.
        # Admin/Presidente (Alcalde) conservan la visión ejecutiva total.
        base_query = filtrar_solicitudes_por_rol()
        solicitudes = base_query.all()
        ciudadanos = Ciudadano.query.all()
        
        # Obtener estadísticas básicas (ya filtradas por dependencia del Director)
        solicitudes_recientes = base_query.order_by(Solicitud.Fecha_Solicitud.desc()).limit(5).all()
        
        total_solicitudes = len(solicitudes)
        total_ciudadanos = len(ciudadanos)
        solicitudes_pendientes = len([s for s in solicitudes if s.Estatus == 'Pendiente'])
        solicitudes_aprobadas = len([s for s in solicitudes if s.Estatus == 'Aprobado'])
        solicitudes_rechazadas = len([s for s in solicitudes if s.Estatus == 'Rechazado'])
        
        # Calcular presupuesto total simple
        presupuesto_total = sum(float(s.Monto) for s in solicitudes if s.Monto and s.Estatus == 'Aprobado')
        
        # Alertas simples
        alertas = len([s for s in solicitudes if not s.Monto or s.Monto <= 0])
        solicitudes_sin_docs = []
        
        # 1. TOP 3 comunidades con mayor presupuesto ejercido (Aprobado)
        # AISLAMIENTO ESTRICTO: para un Director, este agregado también
        # debe limitarse a su propia dependencia (misma regla aplicada
        # a `solicitudes`), nunca mezclar datos de otras dependencias.
        top_comunidades_query = db.session.query(
            Solicitud.Comunidad, func.sum(Solicitud.Monto)
        ).filter(
            Solicitud.Estatus == 'Aprobado'
        )
        if not (current_user.es_admin() or current_user.es_presidente()):
            top_comunidades_query = top_comunidades_query.filter(
                Solicitud.dependencia_id == current_user.dependencia_id
            )
        top_comunidades_query = top_comunidades_query.group_by(Solicitud.Comunidad).order_by(
            func.sum(Solicitud.Monto).desc()
        ).limit(3).all()
        
        demanda_por_comunidad = {com: float(monto) for com, monto in top_comunidades_query if com}
        
        # Si no hay datos aprobados, usar conteo de solicitudes como respaldo
        if not demanda_por_comunidad:
            conteo_comunidad = {}
            for solicitud in solicitudes:
                comunidad = solicitud.Comunidad or 'Sin comunidad'
                conteo_comunidad[comunidad] = conteo_comunidad.get(comunidad, 0) + 1
            # Top 3 por cantidad
            demanda_por_comunidad = dict(sorted(conteo_comunidad.items(), key=lambda x: x[1], reverse=True)[:3])
        
        # 2. TOP 3 tipos de apoyo más frecuentes (con colores distintos asignados en el template)
        conteo_tipo_apoyo = {}
        for solicitud in solicitudes:
            tipo = solicitud.Tipo_Apoyo or 'Sin tipo'
            conteo_tipo_apoyo[tipo] = conteo_tipo_apoyo.get(tipo, 0) + 1
        
        top3_tipos = dict(sorted(conteo_tipo_apoyo.items(), key=lambda x: x[1], reverse=True)[:3])
        
        # REINICIO DE GRÁFICOS DE PRESUPUESTO (ORDEN TÉCNICA MAESTRA): la
        # gráfica de "Distribución de Presupuesto por Programa Social" debe
        # reflejar ESTRICTAMENTE 0%/vacío cuando no existan apoyos APROBADOS
        # con monto real en el período, eliminando cualquier presupuesto
        # visual fantasma (antes se rellenaba con el conteo de solicitudes
        # por tipo o, en su defecto, con montos de ejemplo fijos ficticios
        # de $150,000/$120,000/$80,000 que NUNCA existieron en la base de
        # datos real). Si no hay presupuesto real, se entrega un diccionario
        # vacío y el template/gráfica deben mostrar el estado en cero.
        presupuesto_por_programa = {}
        for solicitud in solicitudes:
            if solicitud.Estatus == 'Aprobado' and solicitud.Tipo_Apoyo and solicitud.Monto:
                tipo = solicitud.Tipo_Apoyo
                presupuesto_por_programa[tipo] = presupuesto_por_programa.get(tipo, 0) + float(solicitud.Monto)

        presupuesto_por_programa = dict(
            sorted(presupuesto_por_programa.items(), key=lambda x: x[1], reverse=True)[:3]
        )
        
        return render_template('dashboard.html', 
                               solicitudes_recientes=solicitudes_recientes,
                               total_solicitudes=total_solicitudes,
                               total_ciudadanos=total_ciudadanos,
                               solicitudes_pendientes=solicitudes_pendientes,
                               solicitudes_aprobadas=solicitudes_aprobadas,
                               solicitudes_rechazadas=solicitudes_rechazadas,
                               presupuesto_total=presupuesto_total,
                               alertas=alertas,
                               solicitudes_sin_docs=solicitudes_sin_docs,
                               demanda_por_comunidad=demanda_por_comunidad,
                               presupuesto_por_programa=presupuesto_por_programa,
                               es_admin=current_user.es_admin())
    
    except Exception as e:
        current_app.logger.error(f"Error en dashboard: {str(e)}")
        return "Error temporal: datos no disponibles"

@main.route('/ciudadanos')
@login_required
def lista_ciudadanos():
    """BLINDAJE: cualquier fallo de lectura se informa sin provocar un Error 500."""
    try:
        ciudadanos = Ciudadano.query.all()
        return render_template('ciudadanos.html', ciudadanos=ciudadanos)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al listar ciudadanos: {str(e)}")
        flash('No se pudo cargar la lista de ciudadanos en este momento.', 'danger')
        return render_template('ciudadanos.html', ciudadanos=[])

@main.route('/ciudadano/<curp>')
@login_required
def ver_ciudadano(curp):
    """
    BLINDAJE: cualquier fallo de lectura se informa sin provocar un Error 500.

    AISLAMIENTO ESTRICTO POR ROL (CORRECCIÓN CRÍTICA DE SEGURIDAD): esta
    vista mostraba TODAS las solicitudes del ciudadano sin filtrar por
    dependencia, exponiendo a cualquier Director el historial completo
    de apoyos (montos, programas, estatus) gestionados por OTRAS áreas
    municipales. Ahora un Director ve ÚNICAMENTE las solicitudes propias
    de su dependencia; Admin/Presidente conservan la visión total.
    """
    try:
        ciudadano = Ciudadano.query.get_or_404(curp)
        solicitudes_query = Solicitud.query.filter_by(CURP=curp)
        if not current_user.tiene_vision_total():
            solicitudes_query = solicitudes_query.filter_by(dependencia_id=current_user.dependencia_id)
        solicitudes = solicitudes_query.all()
        return render_template('ciudadano.html', ciudadano=ciudadano, solicitudes=solicitudes)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al consultar ciudadano {curp}: {str(e)}")
        flash('No se pudo cargar la información de este ciudadano.', 'danger')
        return redirect(url_for('main.lista_ciudadanos'))

@main.route('/buscar_ciudadano', methods=['GET', 'POST'])
@login_required
def buscar_ciudadano():
    """
    Búsqueda de ciudadanos por CURP o nombre, con dashboard de historial
    de apoyos (Aprobados vs Pendientes) y línea de tiempo de montos.

    CORRECCIÓN CRÍTICA (BLINDAJE DE ROBLE): el bloque que calculaba
    `historial_apoyos` estaba indentado DENTRO del `if not resultados:`,
    después de un `return`, por lo que ese código JAMÁS se ejecutaba
    para ningún caso real de búsqueda exitosa (el historial llegaba
    siempre vacío al template). Se corrige la indentación para que el
    historial se calcule siempre que SÍ existan resultados.
    """
    resultados = []
    historial_apoyos = {}

    try:
        if request.method == 'POST':
            curp = request.form.get('curp', '').strip()

            # Validación estricta: verificar que el CURP no esté vacío
            if not curp:
                flash('Por favor ingrese un CURP o nombre para buscar', 'warning')
                return render_template('buscar_ciudadano.html', resultados=[], historial_apoyos={})

            # Si parece un CURP (18 caracteres), buscar por CURP
            if len(curp) == 18 and curp.isupper():
                resultados = Ciudadano.query.filter(Ciudadano.CURP.ilike(f"%{curp}%")).all()
            else:
                # Buscar por nombre (nombre o apellidos)
                resultados = Ciudadano.query.filter(
                    or_(
                        Ciudadano.Nombre.ilike(f"%{curp}%"),
                        Ciudadano.Apellido_Paterno.ilike(f"%{curp}%"),
                        Ciudadano.Apellido_Materno.ilike(f"%{curp}%")
                    )
                ).all()

            # Validación estricta: verificar si no se encontraron resultados
            if not resultados:
                flash('No se encontraron ciudadanos con ese criterio de búsqueda.', 'warning')
                return render_template('usuario_no_encontrado.html')

            # Verificar duplicidad de CURP entre dependencias
            if len(resultados) == 1:
                ciudadano = resultados[0]
                duplicidad_info = verificar_duplicidad_curp(ciudadano.CURP, current_user)
                if duplicidad_info:
                    if duplicidad_info['tipo'] == 'warning':
                        flash(duplicidad_info['mensaje'], 'warning')
                    elif duplicidad_info['tipo'] == 'admin':
                        flash(duplicidad_info['mensaje'], 'info')

            # Obtener historial de apoyos para cada ciudadano encontrado
            # (DASHBOARD PERSONAL: Aprobados vs Pendientes + línea de
            # tiempo histórica de montos, requerido por la consulta
            # inteligente por CURP).
            for ciudadano in resultados:
                # Filtrar solicitudes según el rol del usuario
                if current_user.es_admin():
                    # El Admin ve todas las solicitudes
                    solicitudes = Solicitud.query.filter_by(CURP=ciudadano.CURP).order_by(Solicitud.Fecha_Solicitud.asc()).all()
                else:
                    # El Director solo ve las solicitudes de su dependencia
                    solicitudes = Solicitud.query.filter_by(
                        CURP=ciudadano.CURP,
                        dependencia_id=current_user.dependencia_id
                    ).order_by(Solicitud.Fecha_Solicitud.asc()).all()

                # Calcular monto total recibido (solo Aprobados)
                monto_total = sum(float(s.Monto) for s in solicitudes if s.Monto and s.Estatus == 'Aprobado')
                total_aprobados = len([s for s in solicitudes if s.Estatus == 'Aprobado'])
                total_pendientes = len([s for s in solicitudes if s.Estatus == 'Pendiente'])

                historial_apoyos[ciudadano.CURP] = {
                    'solicitudes': solicitudes,
                    'monto_total': monto_total,
                    'total_aprobados': total_aprobados,
                    'total_pendientes': total_pendientes,
                }

        return render_template('buscar_ciudadano.html',
                              resultados=resultados,
                              historial_apoyos=historial_apoyos,
                              es_admin=current_user.es_admin())
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en búsqueda de ciudadano: {str(e)}")
        flash('No se pudo completar la búsqueda en este momento. Intente nuevamente.', 'danger')
        return render_template('buscar_ciudadano.html', resultados=[], historial_apoyos={}, es_admin=current_user.es_admin())

def _calcular_datos_comunidades():
    """
    Calcula el panel estratégico presupuestal por comunidad usando datos REALES
    de la tabla Solicitud (func.sum / func.count para evitar errores de tipo
    cuando una comunidad no tiene registros). Ordena por total_gastado descendente
    y clasifica prioridad según el volumen relativo de solicitudes.

    AISLAMIENTO ESTRICTO POR ROL: un Director solo debe ver el
    panorama de comunidades construido con los datos de SU PROPIA
    dependencia, nunca el agregado municipal completo (eso es
    exclusivo de Admin/Presidencia - el Alcalde).
    """
    consulta = db.session.query(
        Solicitud.Comunidad,
        func.coalesce(func.sum(Solicitud.Monto), 0).label('total_gastado'),
        func.count(Solicitud.id).label('cantidad_solicitudes')
    )
    if not (current_user.es_admin() or current_user.es_presidente()):
        consulta = consulta.filter(Solicitud.dependencia_id == current_user.dependencia_id)

    resultados_query = consulta.group_by(Solicitud.Comunidad).order_by(
        func.coalesce(func.sum(Solicitud.Monto), 0).desc()
    ).all()

    max_solicitudes = max((r.cantidad_solicitudes for r in resultados_query), default=0)

    datos_comunidades = []
    for r in resultados_query:
        nombre = r.Comunidad or 'Sin comunidad'
        total_gastado = float(r.total_gastado or 0)
        cantidad = r.cantidad_solicitudes

        # Priorización según volumen relativo de solicitudes respecto a la comunidad con más demanda
        ratio = (cantidad / max_solicitudes) if max_solicitudes else 0
        if ratio >= 0.66:
            prioridad = 'Alta'
        elif ratio >= 0.33:
            prioridad = 'Media'
        else:
            prioridad = 'Baja'

        datos_comunidades.append({
            'nombre_comunidad': nombre,
            'total_gastado': total_gastado,
            'cantidad_solicitudes': cantidad,
            'prioridad': prioridad
        })

    return datos_comunidades

@main.route('/comunidades')
@login_required
def comunidades():
    """Panel estratégico de comunidades: presupuesto real ejercido, demanda y prioridad."""
    try:
        datos_comunidades = _calcular_datos_comunidades()
        presupuesto_por_comunidad = {d['nombre_comunidad']: d['total_gastado'] for d in datos_comunidades}

        return render_template('comunidades.html',
                              datos_comunidades=datos_comunidades,
                              presupuesto_por_comunidad=presupuesto_por_comunidad)
    except Exception as e:
        current_app.logger.error(f"Error en comunidades: {str(e)}")
        flash('Error al cargar la información de comunidades.', 'danger')
        return render_template('comunidades.html', datos_comunidades=[], presupuesto_por_comunidad={})

@main.route('/api/comunidades')
@login_required
def api_comunidades():
    """
    API JSON del panel estratégico de comunidades.
    Devuelve: nombre_comunidad, total_gastado, cantidad_solicitudes y prioridad,
    ordenado por total_gastado descendente. Consumido por el mapa (hover/clic).
    """
    try:
        datos_comunidades = _calcular_datos_comunidades()
        return jsonify(datos_comunidades)
    except Exception as e:
        current_app.logger.error(f"Error en api_comunidades: {str(e)}")
        return jsonify({'error': 'Error al obtener datos de comunidades'}), 500


@main.route('/solicitudes')
@login_required
def solicitudes():
    try:
        poblar_datos_demo()

        # AISLAMIENTO ESTRICTO POR ROL (ORDEN TÉCNICA MAESTRA):
        # CORRECCIÓN CRÍTICA DE SEGURIDAD: esta vista mostraba
        # "TODAS las solicitudes sin filtros" a CUALQUIER usuario
        # autenticado, incluyendo Directores de otras dependencias.
        # Ahora un Director ve ÚNICAMENTE las solicitudes de su propia
        # área; Admin/Presidente (Alcalde) conservan la visión total.
        solicitudes = filtrar_solicitudes_por_rol().order_by(Solicitud.Fecha_Solicitud.desc()).all()

        return render_template('solicitudes.html', solicitudes=solicitudes, es_admin=current_user.es_admin())
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en solicitudes: {str(e)}")
        return "Error temporal: datos no disponibles"

@main.route('/exportar_excel', methods=['GET'])
@login_required
def exportar_excel():
    """
    ORDEN EJECUTIVA - ESTRUCTURA DE EXCEL OFICIAL PARA AUDITORÍA:
    Genera un archivo .xlsx (hoja "beneficiarios") con los 21 encabezados
    exactos de la plantilla oficial de auditoría municipal, mapeando los
    datos desde Solicitud y Ciudadano dentro del rango de fechas recibido
    por querystring (fecha_inicio, fecha_fin). Los campos que no existen
    en el modelo de datos actual se rellenan con "no se cuenta", tal como
    lo indica el formato oficial de ejemplo. Al final de la columna MONTO
    se agrega una fórmula de suma automática de Excel (=SUM(...)).
    Cada exportación queda registrada en AuditoriaLog para trazabilidad total.
    """
    try:
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')

        if not fecha_inicio_str or not fecha_fin_str:
            flash('Debe seleccionar una fecha de inicio y una fecha de fin para exportar el reporte.', 'warning')
            return redirect(url_for('main.solicitudes'))

        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
            # Se incluye todo el día final (23:59:59) para no perder registros del último día
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            current_app.logger.warning(f"Formato de fecha inválido en exportar_excel: {fecha_inicio_str} - {fecha_fin_str}")
            flash('Formato de fecha inválido. Utilice el selector de fechas.', 'danger')
            return redirect(url_for('main.solicitudes'))

        if fecha_inicio > fecha_fin:
            flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'danger')
            return redirect(url_for('main.solicitudes'))

        # Consulta principal: todas las solicitudes dentro del rango de fechas
        query = Solicitud.query.filter(Solicitud.Fecha_Solicitud.between(fecha_inicio, fecha_fin))

        # Jerarquía de usuarios: el Director solo puede exportar las solicitudes
        # de su dependencia. CORRECCIÓN CRÍTICA: se usa tiene_vision_total()
        # (Admin o Presidente) en vez de es_admin() a secas, ya que el
        # Presidente tiene dependencia_id=None y quedaba filtrado por un
        # valor que NUNCA existe en Solicitud, devolviendo siempre 0 filas.
        if not current_user.tiene_vision_total():
            query = query.filter_by(dependencia_id=current_user.dependencia_id)

        solicitudes_rango = query.order_by(Solicitud.Fecha_Solicitud.asc()).all()

        if not solicitudes_rango:
            flash('No se encontraron solicitudes en el rango de fechas seleccionado.', 'warning')
            return redirect(url_for('main.solicitudes'))

        NO_DATO = 'no se cuenta'

        # Encabezados EXACTOS de la plantilla oficial de auditoría (hoja "beneficiarios")
        columnas = [
            'POLIZA', 'DIRECCIÓN_ÁREA', 'NOMBRE', 'A_PATERNO', 'A_MATERNO', 'CURP',
            'GENERO', 'FECHA_NACIMIENTO', 'RFC', 'DOMICILIO', 'LOCALIDAD/CABECERA',
            'CP', 'TELEFONO1', 'TELEFONO2', 'CLAVE_PROGRAMA', 'PROGRAMA',
            'FECHA_SOLICITUD', 'FECHA_FINAL_ENTREGA', 'TIPO_APOYO', 'TIPO_BENEFICIARIO', 'MONTO'
        ]

        # Mapeo de datos: Solicitud + Ciudadano -> plantilla oficial
        datos = []
        for s in solicitudes_rango:
            ciudadano = Ciudadano.query.get(s.CURP)
            dependencia_obj = Dependencia.query.get(s.dependencia_id) if s.dependencia_id else None
            direccion_area = dependencia_obj.nombre if dependencia_obj else (s.Dependencia or NO_DATO)

            datos.append({
                'POLIZA': s.folio or str(s.id),
                'DIRECCIÓN_ÁREA': direccion_area,
                'NOMBRE': ciudadano.Nombre if ciudadano else NO_DATO,
                'A_PATERNO': ciudadano.Apellido_Paterno if ciudadano else NO_DATO,
                'A_MATERNO': ciudadano.Apellido_Materno if ciudadano and ciudadano.Apellido_Materno else NO_DATO,
                'CURP': s.CURP,
                'GENERO': ciudadano.Genero if ciudadano and ciudadano.Genero else NO_DATO,
                'FECHA_NACIMIENTO': ciudadano.Fecha_Nacimiento.strftime('%d/%m/%Y') if ciudadano and ciudadano.Fecha_Nacimiento else NO_DATO,
                'RFC': ciudadano.RFC if ciudadano and ciudadano.RFC else NO_DATO,
                'DOMICILIO': ciudadano.Direccion if ciudadano and ciudadano.Direccion else NO_DATO,
                'LOCALIDAD/CABECERA': s.Comunidad or NO_DATO,
                'CP': ciudadano.Codigo_Postal if ciudadano and ciudadano.Codigo_Postal else NO_DATO,
                'TELEFONO1': ciudadano.Telefono if ciudadano and ciudadano.Telefono else NO_DATO,
                # Campos sin equivalente en el modelo actual: rellenados por defecto
                'TELEFONO2': NO_DATO,
                'CLAVE_PROGRAMA': NO_DATO,
                'PROGRAMA': s.Programa or NO_DATO,
                'FECHA_SOLICITUD': s.Fecha_Solicitud.strftime('%d/%m/%Y') if s.Fecha_Solicitud else NO_DATO,
                'FECHA_FINAL_ENTREGA': NO_DATO,
                'TIPO_APOYO': s.Tipo_Apoyo or NO_DATO,
                'TIPO_BENEFICIARIO': NO_DATO,
                'MONTO': float(s.Monto) if s.Monto else 0.0
            })

        df = pd.DataFrame(datos, columns=columnas)

        # Generación del archivo Excel en memoria usando pandas + openpyxl
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='beneficiarios', index=False)

            worksheet = writer.sheets['beneficiarios']

            # Formato institucional para encabezados (azul institucional / texto blanco)
            header_font = Font(bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='1A237E', end_color='1A237E', fill_type='solid')

            for col_num, _ in enumerate(df.columns, start=1):
                celda = worksheet.cell(row=1, column=col_num)
                celda.font = header_font
                celda.fill = header_fill
                worksheet.column_dimensions[celda.column_letter].width = 20

            # SUMA AUTOMÁTICA: fórmula de Excel dinámica en la última fila de la columna MONTO
            total_filas = len(df)
            fila_inicio_datos = 2
            fila_fin_datos = fila_inicio_datos + total_filas - 1
            fila_total = fila_fin_datos + 1

            columna_monto_idx = df.columns.get_loc('MONTO') + 1
            columna_monto_letra = worksheet.cell(row=1, column=columna_monto_idx).column_letter

            celda_etiqueta = worksheet.cell(row=fila_total, column=columna_monto_idx - 1, value='TOTAL:')
            celda_etiqueta.font = Font(bold=True)

            celda_suma = worksheet.cell(
                row=fila_total,
                column=columna_monto_idx,
                value=f"=SUM({columna_monto_letra}{fila_inicio_datos}:{columna_monto_letra}{fila_fin_datos})"
            )
            celda_suma.font = Font(bold=True)

        output.seek(0)

        # Trazabilidad total: registrar la exportación en AuditoriaLog
        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Exportación de Reporte Oficial de Auditoría (Excel - beneficiarios)",
            tabla_afectada='solicitudes',
            registro_id='N/A',
            ip_address=request.remote_addr,
            detalle_cambio=(
                f"{current_user.nombre} ({current_user.rol}) exportó {len(solicitudes_rango)} "
                f"beneficiario(s) en formato Excel oficial del {fecha_inicio_str} al {fecha_fin_str}."
            )
        )
        db.session.add(auditoria)
        db.session.commit()

        filename = f"Reporte_Beneficiarios_{fecha_inicio_str}_a_{fecha_fin_str}.xlsx"

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al exportar reporte Excel: {str(e)}")
        flash(f'Error al generar el reporte Excel: {str(e)}', 'danger')
        return redirect(url_for('main.solicitudes'))



# ============================================
# RUTAS SIMPLES DE EMERGENCIA: APROBAR / RECHAZAR / EXPEDIENTE TXT
# ============================================

@main.route('/aprobar/<int:id>')
@login_required
def aprobar_simple(id):
    """Ruta simple y directa para aprobar una solicitud (demo)"""
    try:
        solicitud = Solicitud.query.get(id)
        if solicitud:
            solicitud.Estatus = 'Aprobado'
            db.session.commit()
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al aprobar (simple): {str(e)}")
        return "Error temporal: datos no disponibles"

@main.route('/rechazar/<int:id>')
@login_required
def rechazar_simple(id):
    """Ruta simple y directa para rechazar una solicitud (demo)"""
    try:
        solicitud = Solicitud.query.get(id)
        if solicitud:
            solicitud.Estatus = 'Rechazado'
            db.session.commit()
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al rechazar (simple): {str(e)}")
        return "Error temporal: datos no disponibles"

@main.route('/expediente_txt/<int:id>')
@login_required
def expediente_txt(id):
    """Genera un expediente en TXT como fallback si el PDF falla"""
    try:
        solicitud = Solicitud.query.get(id)
        if not solicitud:
            return "Error temporal: datos no disponibles"
        
        ciudadano = Ciudadano.query.get(solicitud.CURP)
        nombre_ciudadano = ciudadano.nombre_completo() if ciudadano else "N/A"
        
        contenido = f"""SISTEMA INTEGRAL DE GESTION MUNICIPAL - ATARJEA
EXPEDIENTE DE SOLICITUD DE APOYO

Folio: {solicitud.folio or 'N/A'}
ID Solicitud: #{solicitud.id}
Fecha de Solicitud: {solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M:%S') if solicitud.Fecha_Solicitud else 'N/A'}

DATOS DEL CIUDADANO
--------------------------------------------------
CURP: {solicitud.CURP}
Nombre: {nombre_ciudadano}

DATOS DEL APOYO
--------------------------------------------------
Comunidad: {solicitud.Comunidad}
Programa: {solicitud.Programa}
Tipo de Apoyo: {solicitud.Tipo_Apoyo}
Monto: ${float(solicitud.Monto) if solicitud.Monto else 0:.2f}
Dependencia: {solicitud.Dependencia or 'N/A'}
Estatus: {solicitud.Estatus}

Documento generado automaticamente
Municipio de Atarjea, Guanajuato
Fecha de generacion: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
        buffer = BytesIO()
        buffer.write(contenido.encode('utf-8'))
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"Expediente_Solicitud_{id}.txt",
            mimetype='text/plain'
        )
    except Exception as e:
        current_app.logger.error(f"Error al generar expediente txt: {str(e)}")
        return "Error temporal: datos no disponibles"

@main.route('/buscar_curp/<curp>', methods=['GET'])
@login_required
def buscar_curp(curp):
    """
    Ruta de validación de CURP en tiempo real.
    Consulta si el CURP ya tiene solicitudes registradas y devuelve
    un JSON con el historial de apoyos para mostrar al usuario mientras
    llena el formulario de nueva solicitud.

    AISLAMIENTO ESTRICTO POR ROL (CORRECCIÓN CRÍTICA DE SEGURIDAD): este
    endpoint exponía folio, programa, monto y estatus de las solicitudes
    del CURP en TODAS las dependencias a cualquier usuario autenticado
    (incluidos Directores), vía AJAX. Ahora el detalle (historial) se
    limita a la propia dependencia del Director; si existen solicitudes
    en OTRAS dependencias, solo se informa el conteo total y una alerta
    genérica de posible duplicidad, sin revelar montos ni programas de
    áreas ajenas. Admin/Presidente conservan la visión total.
    """
    try:
        curp = (curp or '').strip().upper()
        
        if len(curp) != 18:
            return jsonify({
                'existe': False,
                'valido': False,
                'mensaje': 'El CURP debe tener 18 caracteres.'
            })
        
        ciudadano = Ciudadano.query.filter_by(CURP=curp).first()
        
        if not ciudadano:
            return jsonify({
                'existe': False,
                'valido': True,
                'mensaje': 'No se encontraron registros previos para este CURP. Puede continuar con el registro.'
            })
        
        # Buscar historial de solicitudes para este CURP, aislado por dependencia
        todas_las_solicitudes = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.Fecha_Solicitud.desc()).all()

        if current_user.tiene_vision_total():
            solicitudes_previas = todas_las_solicitudes
            total_otras_dependencias = 0
        else:
            solicitudes_previas = [
                s for s in todas_las_solicitudes if s.dependencia_id == current_user.dependencia_id
            ]
            total_otras_dependencias = len(todas_las_solicitudes) - len(solicitudes_previas)

        historial = []
        for s in solicitudes_previas:
            historial.append({
                'folio': s.folio or 'N/A',
                'comunidad': s.Comunidad,
                'tipo_apoyo': s.Tipo_Apoyo,
                'programa': s.Programa,
                'monto': float(s.Monto) if s.Monto else 0,
                'estatus': s.Estatus,
                'fecha': s.Fecha_Solicitud.strftime('%d/%m/%Y') if s.Fecha_Solicitud else 'N/A'
            })

        if total_otras_dependencias > 0:
            return jsonify({
                'existe': True,
                'valido': True,
                'nombre_completo': ciudadano.nombre_completo(),
                'total_apoyos': len(historial),
                'historial': historial,
                'alerta_otras_dependencias': True,
                'total_otras_dependencias': total_otras_dependencias,
                'mensaje': (
                    f'Este ciudadano tiene {len(historial)} solicitud(es) en su dependencia y '
                    f'{total_otras_dependencias} registro(s) adicional(es) en OTRAS dependencias '
                    f'(detalle no disponible por aislamiento de información entre áreas).'
                )
            })

        return jsonify({
            'existe': True,
            'valido': True,
            'nombre_completo': ciudadano.nombre_completo(),
            'total_apoyos': len(historial),
            'historial': historial,
            'mensaje': f'Este ciudadano ya tiene {len(historial)} solicitud(es) registrada(s) en el sistema.'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error en buscar_curp: {str(e)}")
        return jsonify({
            'existe': False,
            'valido': False,
            'mensaje': f'Error al verificar el CURP: {str(e)}'
        }), 500

@main.route('/solicitar_apoyo', methods=['GET', 'POST'])
@login_required
def solicitar_apoyo():
    # Verificar si se proporciona un CURP en la URL
    curp_param = request.args.get('curp')
    ciudadano = None
    
    if curp_param:
        ciudadano = Ciudadano.query.filter_by(CURP=curp_param).first()
    
    if request.method == 'POST':
        try:
            # Obtener datos del formulario - FICHA COMPLETA DEL CIUDADANO
            curp = request.form.get('curp')
            rfc = request.form.get('rfc')
            nombre = request.form.get('nombre')
            apellido_paterno = request.form.get('apellido_paterno')
            apellido_materno = request.form.get('apellido_materno')
            genero = request.form.get('genero')
            fecha_nacimiento_str = request.form.get('fecha_nacimiento')
            edad = request.form.get('edad')
            discapacidad = request.form.get('discapacidad') == '1'
            
            # Datos de ubicación y contacto
            comunidad = request.form.get('comunidad')
            codigo_postal = request.form.get('codigo_postal')
            telefono = request.form.get('telefono')
            domicilio = request.form.get('domicilio')
            referencia = request.form.get('referencia')
            
            # Datos del apoyo
            programa = request.form.get('programa')
            tipo_apoyo = request.form.get('tipo_apoyo')
            dependencia = request.form.get('dependencia')
            estatus = request.form.get('estatus', 'Pendiente')

            # DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO (4 apartados
            # independientes y opcionales): Federal, Estatal, Municipal y
            # del Beneficiario. El monto total se calcula automáticamente
            # como la suma de los 4 apartados (ver Solicitud.calcular_monto_total()).
            monto_federal = request.form.get('monto_federal') or 0
            monto_estatal = request.form.get('monto_estatal') or 0
            monto_municipal = request.form.get('monto_municipal') or 0
            monto_beneficiario = request.form.get('monto_beneficiario') or 0
            
            # Convertir fecha de nacimiento si existe (soporta DD/MM/AAAA del datepicker y YYYY-MM-DD legacy)
            fecha_nacimiento = None
            if fecha_nacimiento_str:
                for formato_fecha in ('%d/%m/%Y', '%Y-%m-%d'):
                    try:
                        fecha_nacimiento = datetime.strptime(fecha_nacimiento_str, formato_fecha).date()
                        break
                    except ValueError:
                        continue
            
            # Verificar si el ciudadano existe
            ciudadano = Ciudadano.query.filter_by(CURP=curp).first()
            if not ciudadano:
                # Crear nuevo ciudadano con ficha completa
                ciudadano = Ciudadano(
                    CURP=curp,
                    RFC=rfc,
                    Nombre=nombre,
                    Apellido_Paterno=apellido_paterno,
                    Apellido_Materno=apellido_materno,
                    Genero=genero,
                    Fecha_Nacimiento=fecha_nacimiento,
                    Edad=int(edad) if edad else None,
                    Discapacidad=discapacidad,
                    Telefono=telefono,
                    Direccion=domicilio,
                    Colonia=comunidad,
                    Codigo_Postal=codigo_postal
                )
                db.session.add(ciudadano)
                db.session.flush()  # Obtener ID sin commit
            else:
                # Actualizar ciudadano existente con datos completos
                ciudadano.Nombre = nombre
                ciudadano.Apellido_Paterno = apellido_paterno
                ciudadano.Apellido_Materno = apellido_materno
                ciudadano.Genero = genero
                ciudadano.Fecha_Nacimiento = fecha_nacimiento
                ciudadano.Edad = int(edad) if edad else None
                ciudadano.Discapacidad = discapacidad
                ciudadano.Telefono = telefono
                ciudadano.Direccion = domicilio
                ciudadano.Colonia = comunidad
                ciudadano.Codigo_Postal = codigo_postal
                if rfc:
                    ciudadano.RFC = rfc
            
            # Obtener el ID de la dependencia basado en el nombre
            dependencia_obj = Dependencia.query.filter_by(nombre=dependencia).first()
            dependencia_id = dependencia_obj.id if dependencia_obj else None
            
            # Verificar duplicidad de CURP entre dependencias
            duplicidad_info = verificar_duplicidad_curp(curp, current_user)
            if duplicidad_info and duplicidad_info['tipo'] == 'warning':
                flash(duplicidad_info['mensaje'], 'warning')
            
            # Generar folio automático
            folio = generar_folio()
            
            # Crear la solicitud con todos los datos obligatorios. El
            # monto total (campo legacy `Monto`) se calcula AUTOMÁTICAMENTE
            # a partir del desglose por fuente de financiamiento.
            nueva_solicitud = Solicitud(
                folio=folio,
                CURP=curp,
                Comunidad=comunidad,
                Programa=programa,
                Tipo_Apoyo=tipo_apoyo,
                Monto_Federal=float(monto_federal) if monto_federal else 0,
                Monto_Estatal=float(monto_estatal) if monto_estatal else 0,
                Monto_Municipal=float(monto_municipal) if monto_municipal else 0,
                Monto_Beneficiario=float(monto_beneficiario) if monto_beneficiario else 0,
                Dependencia=dependencia,
                Estatus=estatus,
                Fecha_Solicitud=datetime.utcnow(),
                dependencia_id=dependencia_id,
                usuario_id=current_user.id
            )
            nueva_solicitud.calcular_monto_total()
            
            db.session.add(nueva_solicitud)
            db.session.flush()  # Obtener ID de la solicitud
            
            # Procesar archivos
            archivos_procesados = []
            
            # 1. Identificación oficial
            if 'identificacion_archivo' in request.files:
                archivo = request.files['identificacion_archivo']
                if archivo and archivo.filename:
                    archivo_info = guardar_archivo_solicitud(archivo, nueva_solicitud.id, 'identificacion_oficial', 'identificacion')
                    if archivo_info:
                        archivos_procesados.append(archivo_info)
            
            # 2. Comprobante de domicilio
            if 'comprobante_archivo' in request.files:
                archivo = request.files['comprobante_archivo']
                if archivo and archivo.filename:
                    archivo_info = guardar_archivo_solicitud(archivo, nueva_solicitud.id, 'comprobante_domicilio', 'comprobante')
                    if archivo_info:
                        archivos_procesados.append(archivo_info)
            
            # 3. Foto evidencia
            if 'foto_evidencia' in request.files:
                archivo = request.files['foto_evidencia']
                if archivo and archivo.filename:
                    archivo_info = guardar_archivo_solicitud(archivo, nueva_solicitud.id, 'evidencia_fotografica', 'evidencia')
                    if archivo_info:
                        archivos_procesados.append(archivo_info)
            
            # 4. Documentos adicionales (múltiples)
            if 'documentos_adicionales' in request.files:
                archivos = request.files.getlist('documentos_adicionales')
                for archivo in archivos:
                    if archivo and archivo.filename:
                        archivo_info = guardar_archivo_solicitud(archivo, nueva_solicitud.id, 'documento_adicional', 'adicional')
                        if archivo_info:
                            archivos_procesados.append(archivo_info)
            
            # Confirmar todos los cambios
            db.session.commit()

            # MÓDULO PORTABLE: respaldo automático en el Escritorio tras
            # registrar una solicitud (CERO BLOQUEOS: nunca interrumpe el flujo).
            respaldar_en_escritorio(motivo=f"Nueva solicitud #{nueva_solicitud.id}", usuario_nombre=current_user.nombre)

            flash(f'Solicitud registrada exitosamente. ID: {nueva_solicitud.id}. Archivos procesados: {len(archivos_procesados)}', 'success')
            return redirect(url_for('main.expediente', solicitud_id=nueva_solicitud.id))
            
        except Exception as e:
            db.session.rollback()
            print("Error en registro:", request.form)
            current_app.logger.error(f'Error al crear solicitud: {str(e)}')
            flash(f'Error al procesar la solicitud: {str(e)}', 'danger')
            return render_template('solicitar_apoyo.html', ciudadano=ciudadano)
    
    return render_template('solicitar_apoyo.html', ciudadano=ciudadano)

def guardar_archivo_solicitud(archivo, solicitud_id, tipo_documento, categoria):
    """Guarda un archivo asociado a una solicitud"""
    if archivo.filename == '':
        return None
    
    # Crear directorio si no existe
    directorio = os.path.join('static', 'uploads', 'solicitudes', str(solicitud_id))
    if not os.path.exists(directorio):
        os.makedirs(directorio)
    
    # Generar nombre seguro único con UUID para evitar colisiones
    import uuid
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre_base = secure_filename(archivo.filename)
    nombre_unico = f"{timestamp}_{uuid.uuid4().hex[:8]}_{nombre_base}"
    ruta_completa = os.path.join(directorio, nombre_unico)
    
    # Guardar archivo
    archivo.save(ruta_completa)
    
    # Obtener información del archivo
    tamano = os.path.getsize(ruta_completa)
    extension = nombre_unico.rsplit('.', 1)[1].lower() if '.' in nombre_unico else ''
    
    # Crear registro en base de datos
    nuevo_adjunto = AdjuntoSolicitud(
        solicitud_id=solicitud_id,
        tipo_documento=tipo_documento,
        categoria_documento=categoria,
        nombre_original=archivo.filename,
        nombre_archivo=nombre_unico,
        ruta_archivo=os.path.join('uploads', 'solicitudes', str(solicitud_id), nombre_unico),
        tamano_bytes=tamano,
        extension=extension,
        usuario_carga_id=current_user.id,
        fecha_carga=datetime.utcnow()
    )
    
    db.session.add(nuevo_adjunto)
    return nuevo_adjunto

@main.route('/expediente/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def expediente(solicitud_id):
    """BLINDAJE DE ROBLE: toda la vista queda envuelta en try/except con
    db.session.rollback() ante cualquier falla, de forma que un error al
    adjuntar un documento NUNCA produzca un Error 500 (Server Error)."""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)

        # Verificar permisos: solo Admin/Presidente (visión total) o el
        # Director de la dependencia dueña de la solicitud.
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para acceder a este expediente', 'danger')
            return redirect(url_for('main.dashboard'))

        # Obtener el ciudadano asociado a la solicitud
        ciudadano = Ciudadano.query.get(solicitud.CURP)
        if not ciudadano:
            flash('No se encontró información del ciudadano asociado a esta solicitud', 'danger')
            return redirect(url_for('main.dashboard'))

        # AISLAMIENTO ESTRICTO POR ROL: el historial de apoyos del
        # ciudadano mostrado en el expediente también debe limitarse a
        # la propia dependencia del Director (antes se mostraban TODAS
        # las solicitudes del CURP sin filtrar, exponiendo montos y
        # programas de otras áreas a cualquier Director con acceso a
        # esta solicitud puntual).
        solicitudes_ciudadano_query = Solicitud.query.filter_by(CURP=solicitud.CURP)
        if not current_user.tiene_vision_total():
            solicitudes_ciudadano_query = solicitudes_ciudadano_query.filter_by(
                dependencia_id=current_user.dependencia_id
            )
        solicitudes_ciudadano = solicitudes_ciudadano_query.all()

        # Calcular estadísticas
        total_apoyos = len(solicitudes_ciudadano)
        total_monto = sum(s.Monto for s in solicitudes_ciudadano if s.Monto)

        # Calcular tipos de apoyo
        tipos_apoyo = {}
        for s in solicitudes_ciudadano:
            programa = s.Programa or 'Sin programa'
            tipos_apoyo[programa] = tipos_apoyo.get(programa, 0) + 1

        if request.method == 'POST':
            # Verificar si se envió un archivo
            if 'documento' not in request.files:
                flash('No se seleccionó ningún archivo', 'warning')
                return redirect(request.url)

            archivo = request.files['documento']
            tipo_doc = request.form.get('tipo_documento')

            # Si el usuario no seleccionó un archivo
            if archivo.filename == '':
                flash('No se seleccionó ningún archivo', 'warning')
                return redirect(request.url)

            if archivo:
                # Crear directorio si no existe
                directorio = os.path.join('static', 'uploads', 'expedientes', str(solicitud_id))
                if not os.path.exists(directorio):
                    os.makedirs(directorio)

                # Guardar archivo con nombre seguro
                filename = secure_filename(archivo.filename)
                ruta_completa = os.path.join(directorio, filename)
                archivo.save(ruta_completa)

                # Crear registro en la base de datos usando el nuevo modelo
                nuevo_adjunto = AdjuntoSolicitud(
                    solicitud_id=solicitud_id,
                    tipo_documento=tipo_doc,
                    categoria_documento='otro_documento',
                    nombre_original=archivo.filename,
                    nombre_archivo=filename,
                    ruta_archivo=os.path.join('uploads', 'expedientes', str(solicitud_id), filename),
                    tamano_bytes=os.path.getsize(ruta_completa),
                    extension=filename.rsplit('.', 1)[1].lower() if '.' in filename else '',
                    usuario_carga_id=current_user.id
                )

                db.session.add(nuevo_adjunto)
                db.session.commit()

                flash('Documento cargado exitosamente', 'success')
                return redirect(url_for('main.expediente', solicitud_id=solicitud_id))

        # Obtener adjuntos existentes
        adjuntos = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud_id, activo=True).all()

        # Obtener tipos de documentos disponibles
        tipos_documentos = [tipo.value for tipo in TipoDocumentoMunicipal]

        return render_template('expediente.html',
                              beneficiario=ciudadano,
                              solicitud=solicitud,
                              solicitudes=solicitudes_ciudadano,
                              total_apoyos=total_apoyos,
                              total_monto=total_monto,
                              tipos_apoyo=tipos_apoyo,
                              adjuntos=adjuntos,
                              tipos_documentos=tipos_documentos)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en expediente #{solicitud_id}: {str(e)}", exc_info=True)
        flash('No se pudo cargar o actualizar el expediente en este momento. Intente nuevamente.', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/solicitud/<int:solicitud_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_solicitud(solicitud_id):
    """
    DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO Y ESTATUS COMPLETAMENTE
    EDITABLE: permite modificar posteriormente los 4 apartados de monto
    (Federal/Estatal/Municipal/Beneficiario, con recálculo automático del
    total) y el estatus del apoyo (incluyendo el nuevo estatus "Otorgado"),
    en cualquier momento posterior al registro inicial, por parte de un
    usuario autorizado (Admin/Presidente con visión total, o el Director
    de la dependencia dueña de la solicitud).
    """
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)

        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para editar esta solicitud.', 'danger')
            return redirect(url_for('main.dashboard'))

        if request.method == 'POST':
            estatus_permitidos = ['Pendiente', 'Aprobado', 'Rechazado', 'Otorgado']
            nuevo_estatus = request.form.get('estatus', solicitud.Estatus)
            if nuevo_estatus not in estatus_permitidos:
                flash(f'Estatus no válido. Debe ser uno de: {", ".join(estatus_permitidos)}', 'danger')
                return redirect(url_for('main.editar_solicitud', solicitud_id=solicitud_id))

            estatus_anterior = solicitud.Estatus
            monto_anterior = float(solicitud.Monto or 0)

            solicitud.Programa = request.form.get('programa', solicitud.Programa)
            solicitud.Tipo_Apoyo = request.form.get('tipo_apoyo', solicitud.Tipo_Apoyo)
            solicitud.Monto_Federal = float(request.form.get('monto_federal') or 0)
            solicitud.Monto_Estatal = float(request.form.get('monto_estatal') or 0)
            solicitud.Monto_Municipal = float(request.form.get('monto_municipal') or 0)
            solicitud.Monto_Beneficiario = float(request.form.get('monto_beneficiario') or 0)
            solicitud.calcular_monto_total()
            solicitud.Estatus = nuevo_estatus

            if nuevo_estatus != estatus_anterior:
                solicitud.usuario_autorizador = current_user.id
                solicitud.puesto_autorizador = current_user.rol

            auditoria = AuditoriaLog(
                user_id=current_user.id,
                accion=f"Edición de solicitud #{solicitud_id}",
                tabla_afectada='solicitudes',
                registro_id=str(solicitud_id),
                ip_address=request.remote_addr,
                detalle_cambio=(
                    f"{current_user.nombre} ({current_user.rol}) editó la solicitud #{solicitud_id}. "
                    f"Estatus: '{estatus_anterior}' -> '{nuevo_estatus}'. "
                    f"Monto total: ${monto_anterior:.2f} -> ${float(solicitud.Monto or 0):.2f} "
                    f"(Federal: ${float(solicitud.Monto_Federal or 0):.2f}, "
                    f"Estatal: ${float(solicitud.Monto_Estatal or 0):.2f}, "
                    f"Municipal: ${float(solicitud.Monto_Municipal or 0):.2f}, "
                    f"Beneficiario: ${float(solicitud.Monto_Beneficiario or 0):.2f})."
                )
            )
            db.session.add(auditoria)
            db.session.commit()

            respaldar_en_escritorio(motivo=f"Edición de solicitud #{solicitud_id}", usuario_nombre=current_user.nombre)

            flash(f'Solicitud #{solicitud_id} actualizada exitosamente.', 'success')
            return redirect(url_for('main.expediente', solicitud_id=solicitud_id))

        return render_template('editar_solicitud.html', solicitud=solicitud)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al editar solicitud #{solicitud_id}: {str(e)}", exc_info=True)
        flash('No se pudo actualizar la solicitud en este momento. Intente nuevamente.', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/solicitud/<int:solicitud_id>/eliminar', methods=['POST'])
@login_required
def eliminar_solicitud(solicitud_id):
    """
    ELIMINACIÓN CON CONFIRMACIÓN Y CASCADA GLOBAL: elimina POR COMPLETO
    una solicitud de la base de datos (incluyendo, en cascada, todos sus
    adjuntos gracias a cascade="all, delete-orphan" definido en el
    modelo), de forma que su desaparición se refleje de inmediato en
    todas las vistas, métricas, gráficas y cuentas del sistema (al ya
    no existir el registro, ninguna consulta futura puede volver a
    contarlo). Exclusivo de Admin/Presidente (visión total) o del
    Director dueño de la dependencia de la solicitud.
    """
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)

        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para eliminar esta solicitud.', 'danger')
            return redirect(request.referrer or url_for('main.dashboard'))

        folio_eliminado = solicitud.folio or str(solicitud.id)
        detalle_eliminado = (
            f"{current_user.nombre} ({current_user.rol}) eliminó PERMANENTEMENTE la solicitud "
            f"#{solicitud_id} (folio {folio_eliminado}, CURP {solicitud.CURP}, "
            f"Monto total ${float(solicitud.Monto or 0):.2f}, Estatus '{solicitud.Estatus}')."
        )

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion=f"Eliminación definitiva de solicitud #{solicitud_id}",
            tabla_afectada='solicitudes',
            registro_id=str(solicitud_id),
            ip_address=request.remote_addr,
            detalle_cambio=detalle_eliminado
        )
        db.session.add(auditoria)

        # Eliminación real y en cascada (adjuntos incluidos vía relationship).
        db.session.delete(solicitud)
        db.session.commit()

        respaldar_en_escritorio(motivo=f"Eliminación de solicitud #{solicitud_id}", usuario_nombre=current_user.nombre)

        flash(f'Solicitud #{solicitud_id} (folio {folio_eliminado}) eliminada permanentemente.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al eliminar solicitud #{solicitud_id}: {str(e)}", exc_info=True)
        flash('No se pudo eliminar la solicitud en este momento. Intente nuevamente.', 'danger')

    return redirect(request.referrer or url_for('main.solicitudes'))


@main.route('/generar_reporte', methods=['GET', 'POST'])
@login_required
def generar_reporte():
    if request.method == 'POST':
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        formato = request.form.get('formato', 'excel')
        
        # Convertir fechas a objetos datetime
        try:
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d')
            # Ajustar fecha_fin para incluir todo el día
            fecha_fin = fecha_fin.replace(hour=23, minute=59, second=59)
        except ValueError:
            flash('Formato de fecha inválido', 'danger')
            return redirect(url_for('main.generar_reporte'))
        
        # Filtrar solicitudes por fecha
        query = Solicitud.query.filter(
            Solicitud.Fecha_Solicitud >= fecha_inicio,
            Solicitud.Fecha_Solicitud <= fecha_fin
        )
        
        # Si no tiene visión total (Admin/Presidente), filtrar por dependencia.
        # CORRECCIÓN CRÍTICA: antes usaba solo es_admin(), excluyendo al
        # Presidente de la visión total y devolviendo siempre 0 resultados.
        if not current_user.tiene_vision_total():
            query = query.filter_by(dependencia_id=current_user.dependencia_id)
        
        solicitudes = query.all()
        
        if not solicitudes:
            flash('No se encontraron solicitudes en el rango de fechas seleccionado', 'warning')
            return redirect(url_for('main.generar_reporte'))
        
        # Generar reporte según formato seleccionado
        if formato == 'excel':
            return generar_excel(solicitudes, fecha_inicio, fecha_fin)
        else:
            return generar_pdf(solicitudes, fecha_inicio, fecha_fin)
    
    return render_template('generar_reporte.html')

def generar_excel(solicitudes, fecha_inicio, fecha_fin):
    """Genera un reporte en formato Excel"""
    # Crear DataFrame con los datos
    datos = []
    for s in solicitudes:
        ciudadano = Ciudadano.query.get(s.CURP)
        dependencia = Dependencia.query.get(s.dependencia_id) if s.dependencia_id else None
        
        datos.append({
            'ID': s.id,
            'CURP': s.CURP,
            'Nombre': f"{ciudadano.Nombre} {ciudadano.Apellido_Paterno} {ciudadano.Apellido_Materno or ''}".strip() if ciudadano else 'N/A',
            'Comunidad': s.Comunidad,
            'Programa': s.Programa,
            'Monto': s.Monto or 0,
            'Dependencia': dependencia.nombre if dependencia else s.Dependencia or 'N/A',
            'Fecha': s.Fecha_Solicitud.strftime('%d/%m/%Y'),
            'Estatus': s.Estatus,
            'Documentos': 'Sí' if s.tiene_documentos_completos() else 'No'
        })
    
    # Crear DataFrame
    df = pd.DataFrame(datos)
    
    # Crear archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Solicitudes', index=False)
        
        # Obtener el objeto workbook y worksheet
        workbook = writer.book
        worksheet = writer.sheets['Solicitudes']
        
        # Añadir formatos
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#1a237e',
            'font_color': 'white',
            'border': 1
        })
        
        # Aplicar formato a encabezados
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 15)
    
    # Preparar respuesta
    output.seek(0)
    
    # Nombre del archivo
    filename = f"Reporte_Solicitudes_{fecha_inicio.strftime('%Y%m%d')}_{fecha_fin.strftime('%Y%m%d')}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

def generar_pdf(solicitudes, fecha_inicio, fecha_fin):
    """Genera un reporte en formato PDF"""
    # Crear archivo PDF en memoria
    output = BytesIO()
    
    # Configurar documento
    doc = SimpleDocTemplate(output, pagesize=letter)
    elements = []
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Título
    elements.append(Paragraph("Sistema de Apoyos Municipales", title_style))
    elements.append(Paragraph(f"Municipio de Atarjea, Guanajuato", subtitle_style))
    elements.append(Paragraph(f"Reporte de Solicitudes del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}", subtitle_style))
    elements.append(Paragraph(" ", normal_style))  # Espacio
    
    # Datos para la tabla
    data = [['ID', 'CURP', 'Nombre', 'Comunidad', 'Programa', 'Monto', 'Dependencia', 'Fecha', 'Estatus']]
    
    for s in solicitudes:
        ciudadano = Ciudadano.query.get(s.CURP)
        dependencia = Dependencia.query.get(s.dependencia_id) if s.dependencia_id else None
        
        data.append([
            str(s.id),
            s.CURP,
            f"{ciudadano.Nombre} {ciudadano.Apellido_Paterno} {ciudadano.Apellido_Materno or ''}".strip() if ciudadano else 'N/A',
            s.Comunidad,
            s.Programa,
            f"${s.Monto:.2f}" if s.Monto else '$0.00',
            dependencia.nombre if dependencia else s.Dependencia or 'N/A',
            s.Fecha_Solicitud.strftime('%d/%m/%Y'),
            s.Estatus
        ])
    
    # Crear tabla
    table = Table(data)
    
    # Estilo de tabla
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ])
    
    table.setStyle(style)
    elements.append(table)
    
    # Agregar resumen
    elements.append(Paragraph(" ", normal_style))  # Espacio
    elements.append(Paragraph(f"Total de solicitudes: {len(solicitudes)}", normal_style))
    
    # Calcular montos por estatus
    monto_aprobado = sum(s.Monto for s in solicitudes if s.Estatus == 'Aprobado' and s.Monto)
    monto_pendiente = sum(s.Monto for s in solicitudes if s.Estatus == 'Pendiente' and s.Monto)
    monto_rechazado = sum(s.Monto for s in solicitudes if s.Estatus == 'Rechazado' and s.Monto)
    
    elements.append(Paragraph(f"Monto total aprobado: ${monto_aprobado:.2f}", normal_style))
    elements.append(Paragraph(f"Monto total pendiente: ${monto_pendiente:.2f}", normal_style))
    elements.append(Paragraph(f"Monto total rechazado: ${monto_rechazado:.2f}", normal_style))
    
    # Construir PDF
    doc.build(elements)
    
    # Preparar respuesta
    output.seek(0)
    
    # Nombre del archivo
    filename = f"Reporte_Solicitudes_{fecha_inicio.strftime('%Y%m%d')}_{fecha_fin.strftime('%Y%m%d')}.pdf"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

@main.route('/error')
def error():
    return render_template('error.html')

# ============================================
# RUTAS PARA GESTIÓN DE ARCHIVOS ADJUNTOS
# ============================================

@main.route('/solicitud/<int:solicitud_id>/adjuntos', methods=['GET'])
@login_required
def ver_adjuntos_solicitud(solicitud_id):
    """Muestra los archivos adjuntos de una solicitud"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para ver los adjuntos de esta solicitud.', 'warning')
            return redirect(url_for('main.dashboard'))
        
        adjuntos = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud_id, activo=True).all()
        
        return render_template('adjuntos_solicitud.html',
                             solicitud=solicitud,
                             adjuntos=adjuntos,
                             es_admin=current_user.es_admin())
    
    except Exception as e:
        current_app.logger.error(f"Error al ver adjuntos: {str(e)}")
        flash('Error al cargar los adjuntos de la solicitud.', 'danger')
        return redirect(url_for('main.dashboard'))

@main.route('/solicitud/<int:solicitud_id>/adjuntar', methods=['POST'])
@login_required
def adjuntar_archivo_solicitud(solicitud_id):
    """Adjunta un archivo a una solicitud"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            return jsonify({'success': False, 'error': 'Permisos insuficientes'}), 403
        
        # Obtener datos del formulario
        tipo_documento = request.form.get('tipo_documento')
        categoria = request.form.get('categoria')
        archivo = request.files.get('archivo')
        
        if not archivo or archivo.filename == '':
            return jsonify({'success': False, 'error': 'No se seleccionó ningún archivo'}), 400
        
        if not tipo_documento or not categoria:
            return jsonify({'success': False, 'error': 'Tipo de documento y categoría son requeridos'}), 400
        
        # Validar archivo usando GestorArchivosMunicipales
        from .upload_utils import GestorArchivosMunicipales
        
        validacion = GestorArchivosMunicipales.validar_archivo_completo(archivo, categoria, solicitud_id)
        
        if not validacion['valido']:
            return jsonify({'success': False, 'error': validacion['error']}), 400
        
        # Guardar archivo
        if not GestorArchivosMunicipales.guardar_archivo(archivo.stream, validacion['ruta_destino']):
            return jsonify({'success': False, 'error': 'Error al guardar el archivo'}), 500
        
        # Crear registro en base de datos
        nuevo_adjunto = AdjuntoSolicitud(
            solicitud_id=solicitud_id,
            tipo_documento=tipo_documento,
            categoria_documento=categoria,
            nombre_original=archivo.filename,
            nombre_archivo=validacion['nombre_archivo'],
            ruta_archivo=validacion['ruta_destino'],
            tamano_bytes=validacion['tamano_bytes'],
            tipo_mime=validacion.get('tipo_mime'),
            extension=archivo.filename.rsplit('.', 1)[1].lower() if '.' in archivo.filename else '',
            usuario_carga_id=current_user.id
        )
        
        db.session.add(nuevo_adjunto)
        db.session.commit()
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Carga de archivo adjunto: {tipo_documento}",
            tabla='adjuntos_solicitud',
            registro_id=str(nuevo_adjunto.id),
            detalles=f"Archivo: {archivo.filename}, Tamaño: {validacion['tamano_bytes']} bytes"
        )
        db.session.add(auditoria)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'adjunto_id': nuevo_adjunto.id,
            'nombre_archivo': nuevo_adjunto.nombre_archivo,
            'tipo_documento': nuevo_adjunto.tipo_documento,
            'tamano_bytes': nuevo_adjunto.tamano_bytes
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al adjuntar archivo: {str(e)}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500

@main.route('/adjunto/<int:adjunto_id>/descargar', methods=['GET'])
@login_required
def descargar_adjunto(adjunto_id):
    """Descarga un archivo adjunto"""
    try:
        adjunto = AdjuntoSolicitud.query.get_or_404(adjunto_id)
        solicitud = adjunto.solicitud_relacion
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para descargar este archivo.', 'warning')
            return redirect(url_for('main.dashboard'))
        
        # Verificar que el archivo existe
        if not os.path.exists(adjunto.ruta_archivo):
            flash('El archivo solicitado no existe en el servidor.', 'danger')
            return redirect(url_for('main.ver_adjuntos_solicitud', solicitud_id=solicitud.id))
        
        # Registrar descarga en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Descarga de archivo adjunto: {adjunto.tipo_documento}",
            tabla='adjuntos_solicitud',
            registro_id=str(adjunto.id),
            detalles=f"Archivo: {adjunto.nombre_original}"
        )
        db.session.add(auditoria)
        db.session.commit()
        
        return send_file(
            adjunto.ruta_archivo,
            as_attachment=True,
            download_name=adjunto.nombre_original,
            mimetype=adjunto.tipo_mime or 'application/octet-stream'
        )
    
    except Exception as e:
        current_app.logger.error(f"Error al descargar adjunto: {str(e)}")
        flash('Error al descargar el archivo.', 'danger')
        return redirect(url_for('main.dashboard'))

@main.route('/adjunto/<int:adjunto_id>/eliminar', methods=['POST'])
@login_required
def eliminar_adjunto(adjunto_id):
    """Elimina un archivo adjunto (marcado como inactivo)"""
    try:
        adjunto = AdjuntoSolicitud.query.get_or_404(adjunto_id)
        solicitud = adjunto.solicitud_relacion
        
        # Verificar permisos (solo admin o usuario que cargó el archivo)
        if not current_user.es_admin() and adjunto.usuario_carga_id != current_user.id:
            return jsonify({'success': False, 'error': 'Permisos insuficientes'}), 403
        
        # Marcar como inactivo en lugar de eliminar físicamente
        adjunto.activo = False
        db.session.commit()
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Eliminación de archivo adjunto: {adjunto.tipo_documento}",
            tabla='adjuntos_solicitud',
            registro_id=str(adjunto.id),
            detalles=f"Archivo: {adjunto.nombre_original}"
        )
        db.session.add(auditoria)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Archivo eliminado correctamente'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al eliminar adjunto: {str(e)}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500

@main.route('/solicitud/<int:solicitud_id>/adjuntos/estado', methods=['GET'])
@login_required
def obtener_estado_adjuntos(solicitud_id):
    """Obtiene el estado de los adjuntos requeridos para una solicitud"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            return jsonify({'success': False, 'error': 'Permisos insuficientes'}), 403
        
        # Obtener adjuntos activos de la solicitud
        adjuntos = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud_id, activo=True).all()
        
        # Determinar qué tipos de documentos están presentes
        tipos_presentes = {adjunto.categoria_documento for adjunto in adjuntos}
        
        # Tipos de documentos requeridos
        tipos_requeridos = ['identificacion', 'comprobante_domicilio', 'evidencia_fotografica']
        
        estado = {
            'solicitud_id': solicitud_id,
            'total_adjuntos': len(adjuntos),
            'tipos_requeridos': tipos_requeridos,
            'tipos_presentes': list(tipos_presentes),
            'completo': all(tipo in tipos_presentes for tipo in tipos_requeridos),
            'adjuntos': [adjunto.obtener_informacion_archivo() for adjunto in adjuntos]
        }
        
        return jsonify({'success': True, 'estado': estado})
    
    except Exception as e:
        current_app.logger.error(f"Error al obtener estado de adjuntos: {str(e)}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500

# ============================================
# RUTAS PARA APROBAR/RECHAZAR SOLICITUDES
# ============================================

@main.route('/api/solicitud/<int:solicitud_id>/aprobar', methods=['POST'])
@login_required
def aprobar_solicitud(solicitud_id):
    """Ruta para aprobar una solicitud desde el dashboard"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total():
            # Director solo puede aprobar solicitudes de su dependencia
            if solicitud.dependencia_id != current_user.dependencia_id:
                return jsonify({'success': False, 'error': 'No tiene permisos para aprobar esta solicitud.'}), 403
        
        # Cambiar estado a Aprobado
        solicitud.Estatus = 'Aprobado'
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Aprobación de solicitud #{solicitud_id}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Solicitud aprobada por {current_user.nombre}. Tipo de apoyo: {solicitud.Tipo_Apoyo}, Monto: ${solicitud.Monto:.2f}"
        )
        db.session.add(auditoria)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Solicitud aprobada exitosamente.',
            'estatus': solicitud.Estatus,
            'monto': float(solicitud.Monto)
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al aprobar solicitud: {str(e)}")
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500

@main.route('/api/solicitud/<int:solicitud_id>/rechazar', methods=['POST'])
@login_required
def rechazar_solicitud(solicitud_id):
    """Ruta para rechazar una solicitud desde el dashboard"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total():
            # Director solo puede rechazar solicitudes de su dependencia
            if solicitud.dependencia_id != current_user.dependencia_id:
                return jsonify({'success': False, 'error': 'No tiene permisos para rechazar esta solicitud.'}), 403
        
        # Cambiar estado a Rechazado
        solicitud.Estatus = 'Rechazado'
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Rechazo de solicitud #{solicitud_id}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Solicitud rechazada por {current_user.nombre}. Tipo de apoyo: {solicitud.Tipo_Apoyo}, Monto: ${solicitud.Monto:.2f}"
        )
        db.session.add(auditoria)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Solicitud rechazada exitosamente.',
            'estatus': solicitud.Estatus,
            'monto': float(solicitud.Monto) if solicitud.Monto else 0
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al rechazar solicitud: {str(e)}")
        return jsonify({'success': False, 'error': f'Error interno: {str(e)}'}), 500

# ============================================
# RUTAS PARA AUTORIZACIÓN/RECHAZO DESDE INTERFAZ
# ============================================

@main.route('/autorizar/<int:solicitud_id>', methods=['POST'])
@login_required
def autorizar_solicitud(solicitud_id):
    """Ruta para autorizar una solicitud desde la interfaz web"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente con visión total, o Director)
        if not current_user.tiene_vision_total() and not current_user.es_director():
            flash('No tiene permisos para autorizar solicitudes.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Verificar que el director solo puede autorizar solicitudes de su dependencia
        if current_user.es_director() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('Solo puede autorizar solicitudes de su dependencia.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Cambiar estado a Aprobado
        solicitud.Estatus = 'Aprobado'
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Autorización de solicitud #{solicitud_id}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Solicitud autorizada por {current_user.nombre} ({current_user.rol}). Tipo de apoyo: {solicitud.Tipo_Apoyo}, Monto: ${solicitud.Monto:.2f}"
        )
        db.session.add(auditoria)
        
        db.session.commit()
        
        flash(f'Solicitud #{solicitud_id} autorizada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al autorizar solicitud: {str(e)}")
        flash(f'Error al autorizar la solicitud: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.dashboard'))

@main.route('/rechazar/<int:solicitud_id>', methods=['POST'])
@login_required
def rechazar_solicitud_web(solicitud_id):
    """Ruta para rechazar una solicitud desde la interfaz web"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente con visión total, o Director)
        if not current_user.tiene_vision_total() and not current_user.es_director():
            flash('No tiene permisos para rechazar solicitudes.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Verificar que el director solo puede rechazar solicitudes de su dependencia
        if current_user.es_director() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('Solo puede rechazar solicitudes de su dependencia.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Cambiar estado a Rechazado
        solicitud.Estatus = 'Rechazado'
        
        # Registrar en auditoría
        from .models import AuditLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Rechazo de solicitud #{solicitud_id}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Solicitud rechazada por {current_user.nombre} ({current_user.rol}). Tipo de apoyo: {solicitud.Tipo_Apoyo}, Monto: ${solicitud.Monto:.2f}"
        )
        db.session.add(auditoria)
        
        db.session.commit()
        
        flash(f'Solicitud #{solicitud_id} rechazada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al rechazar solicitud: {str(e)}")
        flash(f'Error al rechazar la solicitud: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.dashboard'))

@main.route('/cambiar_estatus/<int:solicitud_id>/<string:nuevo_estatus>', methods=['POST'])
@login_required
def cambiar_estatus_solicitud(solicitud_id, nuevo_estatus):
    """Ruta para cambiar el estatus de una solicitud según la orden de producción"""
    try:
        # Validar estatus permitidos (incluye el cuarto estatus "Otorgado",
        # editable en cualquier momento posterior al registro inicial).
        estatus_permitidos = ['Aprobado', 'Rechazado', 'Pendiente', 'Otorgado']
        if nuevo_estatus not in estatus_permitidos:
            flash(f'Estatus no válido. Debe ser uno de: {", ".join(estatus_permitidos)}', 'danger')
            return redirect(request.referrer or url_for('main.dashboard'))
        
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente con visión total, o Director)
        if not current_user.tiene_vision_total() and not current_user.es_director():
            flash('No tiene permisos para cambiar el estatus de solicitudes.', 'danger')
            return redirect(request.referrer or url_for('main.dashboard'))
        
        # Verificar que el director solo puede cambiar estatus de solicitudes de su dependencia
        if current_user.es_director() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('Solo puede cambiar el estatus de solicitudes de su dependencia.', 'danger')
            return redirect(request.referrer or url_for('main.dashboard'))
        
        # Guardar el estatus anterior para auditoría
        estatus_anterior = solicitud.Estatus
        
        # Cambiar estado
        solicitud.Estatus = nuevo_estatus
        
        # Registrar usuario autorizador y puesto
        solicitud.usuario_autorizador = current_user.id
        solicitud.puesto_autorizador = current_user.rol
        
        # Registrar en auditoría
        from .models import AuditLog, AuditoriaLog
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Cambio de estatus de solicitud #{solicitud_id}: {estatus_anterior} -> {nuevo_estatus}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Solicitud cambiada por {current_user.nombre} ({current_user.rol}). Tipo de apoyo: {solicitud.Tipo_Apoyo}, Monto: ${solicitud.Monto:.2f}"
        )
        db.session.add(auditoria)
        
        # También registrar en AuditoriaLog para trazabilidad completa
        auditoria_detallada = AuditoriaLog(
            user_id=current_user.id,
            accion=f"Cambio de estatus de solicitud #{solicitud_id}",
            tabla_afectada='solicitudes',
            registro_id=str(solicitud_id),
            detalle_cambio=f"Estatus cambiado de '{estatus_anterior}' a '{nuevo_estatus}' por {current_user.nombre} ({current_user.rol})"
        )
        db.session.add(auditoria_detallada)
        
        db.session.commit()

        # MÓDULO PORTABLE: respaldo automático en el Escritorio tras
        # autorizar/rechazar una solicitud (CERO BLOQUEOS).
        respaldar_en_escritorio(motivo=f"Cambio de estatus solicitud #{solicitud_id} -> {nuevo_estatus}", usuario_nombre=current_user.nombre)

        flash(f'Solicitud #{solicitud_id} cambiada a "{nuevo_estatus}" exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al cambiar estatus de solicitud: {str(e)}")
        flash(f'Error al cambiar el estatus de la solicitud: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('main.dashboard'))

# ============================================
# RUTA PARA HISTORIAL DE AUDITORÍA Y FILTRO POR FECHA
# ============================================

# ============================================
# RUTA PARA HISTORIAL DE AUDITORÍA Y FILTRO POR FECHA
# ============================================

@main.route('/historial_auditoria', methods=['GET', 'POST'])
@login_required
def historial_auditoria():
    """Ruta para mostrar historial de auditoría con filtro por fecha"""
    try:
        # Obtener fecha filtro del formulario si existe
        fecha_filtro = request.args.get('fecha_filtro')
        
        # Base de consulta para SOLICITUDES (no auditoría como se tenía antes)
        # CORRECCIÓN CRÍTICA: se usa tiene_vision_total() (Admin o
        # Presidente) en vez de es_admin() a secas, ya que el Presidente
        # quedaba excluido de la visión total y filtrado por su propio
        # dependencia_id=None, que nunca coincide con ninguna solicitud
        # real, devolviendo siempre 0 resultados en este historial.
        if current_user.tiene_vision_total():
            # Admin/Presidente ven todas las solicitudes
            query = Solicitud.query
        else:
            # Director solo ve solicitudes de su dependencia
            query = Solicitud.query.filter_by(dependencia_id=current_user.dependencia_id)
        
        # Filtrar por fecha si se proporciona
        if fecha_filtro:
            fecha_filtro_date = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Solicitud.Fecha_Solicitud) == fecha_filtro_date)
        
        # Ordenar por fecha descendente
        solicitudes = query.order_by(Solicitud.Fecha_Solicitud.desc()).all()
        
        # Preparar datos para tabla de reportes
        solicitudes_data = []
        for solicitud in solicitudes:
            # Obtener información del ciudadano (nombres reales del modelo: CURP en mayúsculas)
            ciudadano = Ciudadano.query.filter_by(CURP=solicitud.CURP).first()

            solicitudes_data.append({
                'id': solicitud.id,
                'ciudadano': ciudadano.nombre_completo() if ciudadano else (solicitud.CURP or 'No identificado'),
                'fecha': solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M:%S') if solicitud.Fecha_Solicitud else '-',
                'tipo_apoyo': solicitud.Programa if solicitud.Programa else 'Sin tipo definido',
                'dependencia': solicitud.Dependencia if solicitud.Dependencia else 'Sin dependencia',
                'monto': float(solicitud.Monto) if solicitud.Monto else 0,
                'estatus': solicitud.Estatus if solicitud.Estatus else 'Pendiente',
                'curp': solicitud.CURP
            })
        
        # Obtener tipos de apoyo para mostrar en la vista
        tipos_apoyo = [
            'Alimentario',
            'Educativo',
            'A la Salud',
            'A la Vivienda',
            'Apoyo a la Movilidad',
            'Fortalecimiento Comunitario y Cohesión Social'
        ]
        
        return render_template('historial_auditoria.html',
                               solicitudes=solicitudes_data,
                               fecha_filtro=fecha_filtro,
                               tipos_apoyo=tipos_apoyo,
                               es_admin=current_user.es_admin())
    
    except Exception as e:
        current_app.logger.error(f"Error en historial de auditoría: {str(e)}")
        flash('Error al cargar el historial de auditoría.', 'danger')
        return redirect(url_for('main.dashboard'))

from .pdf_utils import generar_ficha_tecnica_pdf, generar_reporte_completo_solicitud

@main.route('/api/generar_reporte_solicitud/<int:solicitud_id>', methods=['GET'])
@login_required
def generar_reporte_solicitud_api(solicitud_id):
    """
    CORRECCIÓN CRÍTICA: endpoint real que consume el JavaScript de
    historial_auditoria.html (fetch + descarga de blob). Antes esta
    ruta no existía en absoluto (404), provocando que el botón
    "Generar Reporte" colapsara siempre. Genera la Ficha Técnica
    completa en PDF (con datos del ciudadano, del apoyo, autorizante
    y evidencia fotográfica) y la sirve como archivo descargable real.
    """
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)

        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            return jsonify({'success': False, 'error': 'Sin permisos para esta solicitud.'}), 403

        pdf_path = generar_ficha_tecnica_pdf(solicitud_id, current_user.id)
        nombre_descarga = f"Reporte_Solicitud_{solicitud_id}_{solicitud.folio or solicitud.CURP}.pdf"
        return send_file(pdf_path, as_attachment=True, download_name=nombre_descarga, mimetype='application/pdf')
    except Exception as e:
        current_app.logger.error(f"Error al generar reporte de solicitud (API): {str(e)}")
        return jsonify({'success': False, 'error': 'Error interno al generar el PDF.'}), 500


@main.route('/api/generar_reporte_individual/<int:solicitud_id>', methods=['GET'])
@login_required
def generar_reporte_individual(solicitud_id):
    """
    Genera un PDF individual (reporte completo) para una solicitud
    específica. CORRECCIÓN: antes devolvía la RUTA del archivo como
    texto plano (string), no el PDF descargable; ahora sirve el
    archivo real generado con send_file.
    """
    try:
        pdf_path = generar_reporte_completo_solicitud(solicitud_id)
        solicitud = Solicitud.query.get(solicitud_id)
        nombre_descarga = f"Reporte_Completo_Solicitud_{solicitud_id}.pdf"
        return send_file(pdf_path, as_attachment=True, download_name=nombre_descarga, mimetype='application/pdf')
    except Exception as e:
        current_app.logger.error(f"Error al generar reporte individual: {str(e)}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 500

@main.route('/generar_reporte/<int:solicitud_id>', methods=['GET'])
@login_required
def generar_reporte_pdf(solicitud_id):
    """Genera un PDF de reporte para una solicitud específica según la orden de producción"""
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        
        # Verificar permisos (Admin/Presidente tienen visión total)
        if not current_user.tiene_vision_total() and solicitud.dependencia_id != current_user.dependencia_id:
            flash('No tiene permisos para generar reportes de esta solicitud.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Obtener información del ciudadano
        ciudadano = Ciudadano.query.get(solicitud.CURP)
        if not ciudadano:
            flash('No se encontró información del ciudadano asociado a esta solicitud.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Obtener información del usuario autorizador si existe
        usuario_autorizador = None
        if solicitud.usuario_autorizador:
            usuario_autorizador = Usuario.query.get(solicitud.usuario_autorizador)
        
        # Crear directorio para guardar el PDF si no existe (ruta portable, funciona en cualquier PC)
        directorio_reporte = obtener_ruta_expedientes()
        
        # Generar nombre del archivo
        nombre_archivo = f"Reporte_Solicitud_{solicitud_id}_{solicitud.CURP}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ruta_completa = os.path.join(directorio_reporte, nombre_archivo)
        
        # Crear PDF usando FPDF
        from fpdf import FPDF
        
        pdf = FPDF()
        pdf.add_page()
        
        # Configurar fuente
        pdf.set_font("Arial", 'B', 16)
        
        # Título
        pdf.cell(200, 10, "Sistema Integral de Gestión Municipal (SIGEM)", ln=True, align='C')
        pdf.cell(200, 10, "Municipio de Atarjea, Guanajuato", ln=True, align='C')
        pdf.ln(10)
        
        # Subtítulo
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, "Reporte de Solicitud de Apoyo", ln=True, align='C')
        pdf.ln(5)
        
        # Información de la solicitud
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, f"Folio: {solicitud.folio or 'N/A'}", ln=True)
        pdf.cell(200, 10, f"ID Solicitud: #{solicitud.id}", ln=True)
        pdf.ln(5)
        
        # Datos del ciudadano
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, "Datos del Ciudadano:", ln=True)
        pdf.set_font("Arial", '', 11)
        pdf.cell(200, 8, f"CURP: {solicitud.CURP}", ln=True)
        pdf.cell(200, 8, f"Nombre Completo: {ciudadano.nombre_completo()}", ln=True)
        pdf.cell(200, 8, f"Fecha de Nacimiento: {ciudadano.Fecha_Nacimiento.strftime('%d/%m/%Y') if ciudadano.Fecha_Nacimiento else 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Género: {ciudadano.Genero or 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Domicilio: {ciudadano.Direccion or 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Teléfono: {ciudadano.Telefono or 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Colonia: {ciudadano.Colonia or 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Código Postal: {ciudadano.Codigo_Postal or 'N/A'}", ln=True)
        pdf.ln(5)
        
        # Datos de la solicitud
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, "Datos de la Solicitud:", ln=True)
        pdf.set_font("Arial", '', 11)
        pdf.cell(200, 8, f"Comunidad: {solicitud.Comunidad}", ln=True)
        pdf.cell(200, 8, f"Programa: {solicitud.Programa}", ln=True)
        pdf.cell(200, 8, f"Tipo de Apoyo: {solicitud.Tipo_Apoyo}", ln=True)
        pdf.cell(200, 8, f"Monto: ${solicitud.Monto:.2f}" if solicitud.Monto else "Monto: N/A", ln=True)
        pdf.cell(200, 8, f"Dependencia: {solicitud.Dependencia or 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Fecha de Solicitud: {solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M:%S') if solicitud.Fecha_Solicitud else 'N/A'}", ln=True)
        pdf.cell(200, 8, f"Estatus: {solicitud.Estatus}", ln=True)
        pdf.ln(5)
        
        # Información de autorización
        if usuario_autorizador:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 10, "Información de Autorización:", ln=True)
            pdf.set_font("Arial", '', 11)
            pdf.cell(200, 8, f"Autorizado por: {usuario_autorizador.nombre}", ln=True)
            pdf.cell(200, 8, f"Puesto: {solicitud.puesto_autorizador or usuario_autorizador.rol}", ln=True)
            pdf.cell(200, 8, f"Fecha de Autorización: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
            pdf.ln(5)

        # Evidencia fotográfica adjunta a la solicitud
        adjuntos_solicitud = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud_id, activo=True).all()
        adjuntos_imagen = [
            a for a in adjuntos_solicitud
            if a.extension and a.extension.lower() in ('jpg', 'jpeg', 'png', 'bmp', 'gif')
        ]

        if adjuntos_solicitud:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 10, "Documentos Adjuntos / Evidencia Fotografica:", ln=True)
            pdf.set_font("Arial", '', 11)

            if not adjuntos_imagen:
                pdf.cell(200, 8, "No hay imagenes adjuntas para mostrar (solo documentos no graficos).", ln=True)
            else:
                for adjunto in adjuntos_imagen:
                    # Resolver ruta absoluta del archivo en el servidor.
                    # ruta_archivo se guarda relativa a la carpeta 'static' de la app.
                    ruta_relativa = adjunto.ruta_archivo
                    ruta_imagen = ruta_relativa
                    if not os.path.isabs(ruta_imagen) or not os.path.exists(ruta_imagen):
                        ruta_candidata = os.path.join(current_app.static_folder, ruta_relativa)
                        if os.path.exists(ruta_candidata):
                            ruta_imagen = ruta_candidata

                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(200, 6, f"{adjunto.nombre_original}", ln=True)

                    if os.path.exists(ruta_imagen):
                        try:
                            # Verificar espacio disponible en la página; si no alcanza, agregar página nueva
                            if pdf.get_y() > 220:
                                pdf.add_page()
                            pdf.image(ruta_imagen, x=10, y=pdf.get_y(), w=80, h=60)
                            pdf.ln(65)
                        except Exception as img_error:
                            current_app.logger.error(f"Error insertando imagen {ruta_imagen} en PDF: {str(img_error)}")
                            pdf.set_font("Arial", '', 11)
                            pdf.cell(200, 8, "Imagen no disponible", ln=True)
                    else:
                        current_app.logger.warning(f"Imagen de evidencia no encontrada en disco: {ruta_relativa}")
                        pdf.set_font("Arial", '', 11)
                        pdf.cell(200, 8, "Imagen no disponible", ln=True)
            pdf.ln(5)

        # Pie de página

        pdf.set_font("Arial", 'I', 10)
        pdf.cell(200, 10, "Documento generado automáticamente por el Sistema Integral de Gestión Municipal", ln=True)
        pdf.cell(200, 10, "Este documento es parte del expediente de auditoría del municipio de Atarjea, Guanajuato", ln=True)
        pdf.cell(200, 10, f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
        
        # Guardar PDF
        pdf.output(ruta_completa)
        
        # Registrar en auditoría
        auditoria = AuditLog(
            usuario_id=current_user.id,
            accion=f"Generación de reporte PDF para solicitud #{solicitud_id}",
            tabla='solicitudes',
            registro_id=str(solicitud_id),
            detalles=f"Reporte PDF generado y guardado en: {ruta_completa}"
        )
        db.session.add(auditoria)
        db.session.commit()
        
        # Enviar archivo al usuario
        return send_file(
            ruta_completa,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        # CERO CAÍDAS (ORDEN TÉCNICA MAESTRA): nunca se muestra el detalle
        # técnico crudo de la excepción al operador (riesgo de confusión y
        # de exponer rutas internas del servidor); se registra en el log
        # y se informa un mensaje claro y accionable.
        db.session.rollback()
        current_app.logger.error(f"Error al generar reporte PDF de la solicitud #{solicitud_id}: {str(e)}", exc_info=True)
        flash('No se pudo generar el reporte PDF. Verifique los datos del folio e intente nuevamente.', 'danger')
        return redirect(url_for('main.dashboard'))

# ============================================
# CIERRE DE EJERCICIO ANUAL (SOLO PRESIDENTE MUNICIPAL / ADMIN)
# ============================================

# ORDEN TÉCNICA MAESTRA - JORNADA ADMINISTRATIVA DE REFERENCIA: horario
# oficial de oficina del Municipio de Atarjea (08:00 a 15:00) usado
# ÚNICAMENTE para calcular el "% de avance de la jornada" en la Línea
# de Tiempo Operativa del Alcalde. Es un valor de referencia visual,
# nunca bloquea ni valida la captura real de ningún Director.
HORA_INICIO_JORNADA = 8
HORA_FIN_JORNADA = 15


def _construir_linea_tiempo_operativa(usuario, fecha_desde=None, fecha_hasta=None):
    """
    LÍNEA DE TIEMPO OPERATIVA DEL DÍA (DASHBOARD EJECUTIVO DEL ALCALDE):
    reconstruye, en orden cronológico, TODA la actividad real de un
    Director/trabajador específico dentro del rango de fechas dado:
      - Apoyos otorgados (Solicitud creada por ese usuario).
      - Vales de combustible autorizados (Formulario N° 10).
      - Cualquier otra acción registrada en AuditoriaLog (ediciones de
        expediente, exportaciones, cambios de estatus, etc.).

    CERO CAÍDAS: cualquier fuente de datos que falle se omite en
    silencio (se registra en el log) sin interrumpir las demás.
    Retorna (eventos, metricas) donde `metricas` incluye el total de
    eventos, el rendimiento por hora y el % de avance de la jornada
    administrativa de referencia (08:00-15:00).
    """
    eventos = []

    try:
        q_sol = Solicitud.query.filter_by(usuario_id=usuario.id)
        if fecha_desde:
            q_sol = q_sol.filter(Solicitud.Fecha_Solicitud >= fecha_desde)
        if fecha_hasta:
            q_sol = q_sol.filter(Solicitud.Fecha_Solicitud <= fecha_hasta)
        for s in q_sol.all():
            if not s.Fecha_Solicitud:
                continue
            eventos.append({
                'hora': s.Fecha_Solicitud,
                'tipo': 'Apoyo Otorgado',
                'icono': 'fa-hand-holding-heart',
                'color': 'success',
                'detalle': f"Folio {s.folio or s.id} - {s.Tipo_Apoyo or 'Sin tipo'} - ${float(s.Monto or 0):,.2f} ({s.Estatus or 'Pendiente'})",
            })
    except Exception as e:
        current_app.logger.warning(f"Línea de tiempo: no se pudieron cargar solicitudes del usuario {usuario.id}: {str(e)}")

    try:
        q_asig = AsignacionCombustible.query.filter_by(usuario_id=usuario.id)
        if fecha_desde:
            q_asig = q_asig.filter(AsignacionCombustible.fecha_creacion >= fecha_desde)
        if fecha_hasta:
            q_asig = q_asig.filter(AsignacionCombustible.fecha_creacion <= fecha_hasta)
        for a in q_asig.all():
            if not a.fecha_creacion:
                continue
            eventos.append({
                'hora': a.fecha_creacion,
                'tipo': 'Vale de Combustible Autorizado',
                'icono': 'fa-gas-pump',
                'color': 'warning',
                'detalle': f"Folio {a.folio_asignacion} - {a.litros_asignados or 0} L ({a.tipo_asignacion or 'N/A'})",
            })
    except Exception as e:
        current_app.logger.warning(f"Línea de tiempo: no se pudieron cargar asignaciones del usuario {usuario.id}: {str(e)}")

    try:
        q_audit = AuditoriaLog.query.filter_by(user_id=usuario.id)
        if fecha_desde:
            q_audit = q_audit.filter(AuditoriaLog.fecha >= fecha_desde)
        if fecha_hasta:
            q_audit = q_audit.filter(AuditoriaLog.fecha <= fecha_hasta)
        for ev in q_audit.all():
            if not ev.fecha:
                continue
            eventos.append({
                'hora': ev.fecha,
                'tipo': ev.accion or 'Acción registrada',
                'icono': 'fa-file-alt',
                'color': 'info',
                'detalle': ev.detalle_cambio or '-',
            })
    except Exception as e:
        current_app.logger.warning(f"Línea de tiempo: no se pudo cargar AuditoriaLog del usuario {usuario.id}: {str(e)}")

    eventos.sort(key=lambda e: e['hora'])

    # ---------------- INDICADORES DE RENDIMIENTO ----------------
    total_eventos = len(eventos)
    rendimiento_por_hora = {}
    for ev in eventos:
        etiqueta_hora = ev['hora'].strftime('%H:00')
        rendimiento_por_hora[etiqueta_hora] = rendimiento_por_hora.get(etiqueta_hora, 0) + 1

    hoy = datetime.utcnow()
    hora_actual_decimal = hoy.hour + (hoy.minute / 60.0)
    duracion_jornada = max(HORA_FIN_JORNADA - HORA_INICIO_JORNADA, 1)
    avance = (hora_actual_decimal - HORA_INICIO_JORNADA) / duracion_jornada * 100
    porcentaje_avance_jornada = round(min(max(avance, 0), 100), 1)

    metricas = {
        'total_eventos': total_eventos,
        'rendimiento_por_hora': rendimiento_por_hora,
        'porcentaje_avance_jornada': porcentaje_avance_jornada,
        'primer_evento': eventos[0]['hora'] if eventos else None,
        'ultimo_evento': eventos[-1]['hora'] if eventos else None,
    }

    return eventos, metricas


@main.route('/auditoria_en_vivo', methods=['GET'])
@login_required
def auditoria_en_vivo():
    """
    PANEL DE SUPERVISIÓN EN TIEMPO REAL (VISTA DEL ALCALDE) - ORDEN
    TÉCNICA MAESTRA punto 4: exclusivo para el rol Administrador
    (Alcalde/Presidencia). Muestra en vivo, sin recargar la captura de
    campo de ningún operador, la actividad reciente de TODAS las cuentas
    institucionales que existan en el sistema en este momento (dinámico:
    no se asume un número fijo de cuentas), con folios emitidos y litros
    consumidos del Formulario N° 10 de combustible, además del último
    movimiento de auditoría general (AuditoriaLog) por usuario.

    FILTRO DE PERÍODO (OPTIMIZACIÓN DEL DASHBOARD DEL ALCALDE): permite
    filtrar la actividad de todas las cuentas por 'hoy', 'semana' (los
    últimos 7 días) o 'personalizado' (rango de fechas elegido por el
    Alcalde vía ?periodo=personalizado&fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD).
    Por defecto se muestra el histórico completo ('todo').

    CERO CAÍDAS: cualquier dato ausente (usuario sin folios, catálogo
    vacío, etc.) se traduce en ceros/listas vacías, nunca en un error.
    """
    try:
        if not (current_user.es_admin() or current_user.es_presidente()):
            flash('Acceso restringido. Esta vista es exclusiva de la Alcaldía/Administración.', 'danger')
            return redirect(url_for('main.dashboard'))

        # ---------------- FILTRO DE PERÍODO (Hoy / Ayer / Semana / Personalizado) ----------------
        periodo = (request.args.get('periodo') or 'todo').strip().lower()
        hoy = datetime.utcnow()
        fecha_desde = None
        fecha_hasta = None

        if periodo == 'hoy':
            fecha_desde = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
            fecha_hasta = hoy.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif periodo == 'ayer':
            ayer = hoy - timedelta(days=1)
            fecha_desde = ayer.replace(hour=0, minute=0, second=0, microsecond=0)
            fecha_hasta = ayer.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif periodo == 'semana':
            fecha_desde = (hoy - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            fecha_hasta = hoy
        elif periodo == 'mes':
            # CENTRO DE CONTROL EJECUTIVO (PRESIDENCIA MUNICIPAL): avance
            # mensual del mes en curso, para comparar contra el filtro
            # "semana" en el mismo resumen por área.
            fecha_desde = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            fecha_hasta = hoy
        elif periodo == 'personalizado':
            try:
                fecha_inicio_str = request.args.get('fecha_inicio')
                fecha_fin_str = request.args.get('fecha_fin')
                if fecha_inicio_str:
                    fecha_desde = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                if fecha_fin_str:
                    fecha_hasta = datetime.strptime(fecha_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            except ValueError:
                flash('Formato de fecha inválido en el Período Personalizado. Mostrando histórico completo.', 'warning')
                fecha_desde = None
                fecha_hasta = None
        # periodo == 'todo' (o cualquier otro valor): sin filtro, histórico completo.

        usuarios_activos = Usuario.query.filter_by(activo=True).order_by(Usuario.nombre.asc()).all()

        actividad_por_usuario = []
        total_folios_global = 0
        total_litros_global = 0.0

        for usuario in usuarios_activos:
            asignaciones_usuario = AsignacionCombustible.query.filter_by(usuario_id=usuario.id).all()

            if fecha_desde or fecha_hasta:
                asignaciones_periodo = [
                    a for a in asignaciones_usuario
                    if a.fecha_creacion
                    and (fecha_desde is None or a.fecha_creacion >= fecha_desde)
                    and (fecha_hasta is None or a.fecha_creacion <= fecha_hasta)
                ]
            else:
                asignaciones_periodo = asignaciones_usuario

            folios_usuario = len(asignaciones_periodo)
            litros_usuario = sum(
                float(a.litros_asignados or 0) for a in asignaciones_periodo
                if a.estatus != EstatusAsignacionEnum.CANCELADA.value
            )
            asignaciones_mes_usuario = [
                a for a in asignaciones_usuario
                if a.fecha_creacion and a.fecha_creacion.month == hoy.month and a.fecha_creacion.year == hoy.year
            ]

            ultima_accion_query = AuditoriaLog.query.filter_by(user_id=usuario.id)
            if fecha_desde:
                ultima_accion_query = ultima_accion_query.filter(AuditoriaLog.fecha >= fecha_desde)
            if fecha_hasta:
                ultima_accion_query = ultima_accion_query.filter(AuditoriaLog.fecha <= fecha_hasta)
            ultima_accion = ultima_accion_query.order_by(AuditoriaLog.fecha.desc()).first()

            total_folios_global += folios_usuario
            total_litros_global += litros_usuario

            actividad_por_usuario.append({
                'usuario': usuario,
                'folios_totales': folios_usuario,
                'litros_totales': round(litros_usuario, 2),
                'folios_mes': len(asignaciones_mes_usuario),
                'ultima_accion': ultima_accion,
            })

        # Orden descendente por actividad reciente para que el Alcalde vea
        # primero a los usuarios operando activamente en este momento.
        actividad_por_usuario.sort(
            key=lambda item: item['ultima_accion'].fecha if item['ultima_accion'] else datetime.min,
            reverse=True
        )

        eventos_query = AuditoriaLog.query
        if fecha_desde:
            eventos_query = eventos_query.filter(AuditoriaLog.fecha >= fecha_desde)
        if fecha_hasta:
            eventos_query = eventos_query.filter(AuditoriaLog.fecha <= fecha_hasta)
        eventos_recientes = eventos_query.order_by(AuditoriaLog.fecha.desc()).limit(30).all()

        # ---------------- RESÚMENES EJECUTIVOS DE NIVEL PRESIDENCIAL ----------------
        # Sumatorias claras de montos invertidos (Apoyos Sociales) y
        # litros consumidos por fluido (Gasolina/Diésel/Urea) dentro
        # del mismo período filtrado arriba, para el Dashboard del Alcalde.
        resumen_monto_apoyos = 0.0
        resumen_folios_apoyos = 0
        try:
            q_apoyos = Solicitud.query.filter(Solicitud.Estatus == 'Aprobado')
            if fecha_desde:
                q_apoyos = q_apoyos.filter(Solicitud.Fecha_Solicitud >= fecha_desde)
            if fecha_hasta:
                q_apoyos = q_apoyos.filter(Solicitud.Fecha_Solicitud <= fecha_hasta)
            solicitudes_periodo = q_apoyos.all()
            resumen_monto_apoyos = sum(float(s.Monto or 0) for s in solicitudes_periodo)
            resumen_folios_apoyos = len(solicitudes_periodo)
        except Exception as e:
            current_app.logger.warning(f"Resumen ejecutivo: no se pudo calcular el monto de apoyos: {str(e)}")

        resumen_litros_por_fluido = {}
        try:
            asignaciones_vigentes_query = AsignacionCombustible.query.filter(
                AsignacionCombustible.estatus != EstatusAsignacionEnum.CANCELADA.value
            )
            if fecha_desde:
                asignaciones_vigentes_query = asignaciones_vigentes_query.filter(AsignacionCombustible.fecha_creacion >= fecha_desde)
            if fecha_hasta:
                asignaciones_vigentes_query = asignaciones_vigentes_query.filter(AsignacionCombustible.fecha_creacion <= fecha_hasta)
            for a in asignaciones_vigentes_query.all():
                fluido = _resolver_tipo_fluido_asignacion(a) or 'OTRO'
                nombre_fluido = TipoFluidoEnum.nombre_completo(fluido) if fluido != 'OTRO' else 'Otro/No identificado'
                resumen_litros_por_fluido[nombre_fluido] = resumen_litros_por_fluido.get(nombre_fluido, 0.0) + float(a.litros_asignados or 0)
            resumen_litros_por_fluido = {k: round(v, 2) for k, v in resumen_litros_por_fluido.items()}
        except Exception as e:
            current_app.logger.warning(f"Resumen ejecutivo: no se pudo calcular litros por fluido: {str(e)}")

        # ---------------- CENTRO DE CONTROL EJECUTIVO (PRESIDENCIA MUNICIPAL) ----------------
        # Desglose en tiempo real del avance de apoyos por ÁREA/DEPENDENCIA
        # dentro del mismo período filtrado arriba (Hoy/Ayer/Semana/Mes/
        # Personalizado/Histórico). Refleja de forma instantánea los
        # movimientos que cada Director va registrando, inspirado en el
        # mismo patrón que el Reporte Semanal Consolidado de combustible
        # (control de gasolina) de Servicios Públicos, pero aplicado al
        # avance de los apoyos sociales por dependencia.
        resumen_apoyos_por_area = []
        try:
            dependencias_todas = Dependencia.query.order_by(Dependencia.nombre.asc()).all()
            for dep in dependencias_todas:
                q_dep = Solicitud.query.filter(Solicitud.dependencia_id == dep.id)
                if fecha_desde:
                    q_dep = q_dep.filter(Solicitud.Fecha_Solicitud >= fecha_desde)
                if fecha_hasta:
                    q_dep = q_dep.filter(Solicitud.Fecha_Solicitud <= fecha_hasta)
                solicitudes_dep = q_dep.all()

                monto_aprobado_dep = sum(float(s.Monto or 0) for s in solicitudes_dep if s.Estatus == 'Aprobado')
                total_dep = len(solicitudes_dep)
                aprobadas_dep = len([s for s in solicitudes_dep if s.Estatus == 'Aprobado'])
                pendientes_dep = len([s for s in solicitudes_dep if s.Estatus == 'Pendiente'])
                rechazadas_dep = len([s for s in solicitudes_dep if s.Estatus == 'Rechazado'])
                avance_dep_pct = round((aprobadas_dep / total_dep * 100), 1) if total_dep else 0.0

                resumen_apoyos_por_area.append({
                    'dependencia': dep.nombre,
                    'monto_aprobado': round(monto_aprobado_dep, 2),
                    'total_solicitudes': total_dep,
                    'aprobadas': aprobadas_dep,
                    'pendientes': pendientes_dep,
                    'rechazadas': rechazadas_dep,
                    'avance_pct': avance_dep_pct,
                })

            # Ordenar por monto aprobado descendente para que el Alcalde
            # vea primero las áreas con mayor ejercicio de presupuesto.
            resumen_apoyos_por_area.sort(key=lambda item: item['monto_aprobado'], reverse=True)
        except Exception as e:
            current_app.logger.warning(f"Centro de Control Ejecutivo: no se pudo calcular el resumen por área: {str(e)}")

        # ---------------- DASHBOARD EJECUTIVO: SELECTOR DE TRABAJADOR/DIRECTOR ----------------
        # Permite al Alcalde elegir a un Director/trabajador específico
        # (ej. "Director de Desarrollo Rural") y desplegar su Línea de
        # Tiempo Operativa del Día (cronología completa de su jornada).
        director_seleccionado_id = request.args.get('director_id', type=int)
        director_seleccionado = None
        linea_tiempo_eventos = []
        linea_tiempo_metricas = None

        if director_seleccionado_id:
            director_seleccionado = Usuario.query.get(director_seleccionado_id)
            if director_seleccionado:
                linea_tiempo_eventos, linea_tiempo_metricas = _construir_linea_tiempo_operativa(
                    director_seleccionado, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
                )

        return render_template(
            'auditoria_en_vivo.html',
            actividad_por_usuario=actividad_por_usuario,
            eventos_recientes=eventos_recientes,
            total_cuentas=len(usuarios_activos),
            total_folios_global=total_folios_global,
            total_litros_global=round(total_litros_global, 2),
            periodo_actual=periodo,
            fecha_inicio_personalizada=request.args.get('fecha_inicio', ''),
            fecha_fin_personalizada=request.args.get('fecha_fin', ''),
            usuarios_activos=usuarios_activos,
            director_seleccionado=director_seleccionado,
            linea_tiempo_eventos=linea_tiempo_eventos,
            linea_tiempo_metricas=linea_tiempo_metricas,
            hora_inicio_jornada=HORA_INICIO_JORNADA,
            hora_fin_jornada=HORA_FIN_JORNADA,
            resumen_monto_apoyos=round(resumen_monto_apoyos, 2),
            resumen_folios_apoyos=resumen_folios_apoyos,
            resumen_litros_por_fluido=resumen_litros_por_fluido,
            resumen_apoyos_por_area=resumen_apoyos_por_area,
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en Panel de Auditoría en Vivo: {str(e)}", exc_info=True)
        flash('No se pudo cargar el Panel de Auditoría en Vivo en este momento.', 'danger')
        return redirect(url_for('main.dashboard'))


# ============================================
# MÓDULO PORTABLE: SINCRONIZACIÓN ASÍNCRONA SIN RED FIJA
# "Exportar Paquete Diario" / "Importar Paquete de Director" - permite
# al Alcalde y a los Directores consolidar manualmente la información
# capturada en distintas computadoras/módems de Atarjea (USB, correo o
# carpeta compartida), sin depender de un servidor central.
# ============================================

@main.route('/paquete_diario/exportar', methods=['GET'])
@login_required
def exportar_paquete_diario():
    """
    Botón "Exportar Paquete Diario (.sigem/json)": genera y descarga un
    archivo .sigem.json con los datos operativos clave del sistema
    (usuarios, dependencias, comunidades, ciudadanos, solicitudes y
    los registros del Módulo de Servicios Públicos). Exclusivo del
    Alcalde/Administración y Directores.
    """
    try:
        if not (current_user.es_admin() or current_user.es_presidente() or current_user.es_director()):
            flash('Acceso restringido. Solo el Alcalde o los Directores pueden exportar el Paquete Diario.', 'danger')
            return redirect(url_for('main.dashboard'))

        nombre_archivo, contenido = generar_paquete_diario_json()
        if not contenido:
            flash('No se pudo generar el Paquete Diario en este momento. Intente nuevamente.', 'danger')
            return redirect(url_for('main.dashboard'))

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Exportación de Paquete Diario (Sincronización sin red fija)",
            tabla_afectada='sistema',
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} exportó el Paquete Diario '{nombre_archivo}'."
        )
        db.session.add(auditoria)
        db.session.commit()

        buffer = BytesIO()
        buffer.write(contenido.encode('utf-8'))
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/json'
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al exportar el Paquete Diario: {str(e)}", exc_info=True)
        flash('No se pudo exportar el Paquete Diario en este momento.', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/paquete_diario/importar', methods=['POST'])
@login_required
def importar_paquete_diario():
    """
    Botón "Importar Paquete de Director": recibe un archivo .sigem.json
    generado en OTRA computadora y fusiona sus datos en la base local,
    sin duplicar registros ya existentes. Exclusivo del Alcalde /
    Administración.
    """
    try:
        if not (current_user.es_admin() or current_user.es_presidente()):
            flash('Acceso restringido. Solo el Alcalde o la Administración pueden importar un Paquete de Director.', 'danger')
            return redirect(url_for('main.dashboard'))

        archivo = request.files.get('paquete')
        if not archivo or not archivo.filename:
            flash('Debe seleccionar un archivo de Paquete de Director (.sigem.json) para importar.', 'warning')
            return redirect(url_for('main.auditoria_en_vivo'))

        contenido_texto = archivo.read().decode('utf-8')
        resumen = importar_paquete_json(contenido_texto)

        if not resumen.get('exito'):
            flash(f"No se pudo importar el paquete: {resumen.get('error') or 'Error desconocido'}.", 'danger')
            return redirect(url_for('main.auditoria_en_vivo'))

        total_insertados = sum(d.get('insertados', 0) for d in resumen['detalle'].values())
        total_duplicados = sum(d.get('omitidos_duplicados', 0) for d in resumen['detalle'].values())

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Importación de Paquete de Director (Sincronización sin red fija)",
            tabla_afectada='sistema',
            ip_address=request.remote_addr,
            detalle_cambio=(
                f"{current_user.nombre} importó '{archivo.filename}'. "
                f"Registros nuevos: {total_insertados}. Ya existentes (omitidos): {total_duplicados}."
            )
        )
        db.session.add(auditoria)
        db.session.commit()

        respaldar_en_escritorio(motivo=f"Importación de Paquete de Director ({archivo.filename})", usuario_nombre=current_user.nombre)

        flash(f'Paquete importado exitosamente. Registros nuevos agregados: {total_insertados}. '
              f'Registros ya existentes omitidos: {total_duplicados}.', 'success')
        return redirect(url_for('main.auditoria_en_vivo'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al importar el Paquete de Director: {str(e)}", exc_info=True)
        flash('No se pudo importar el Paquete de Director. Verifique que el archivo sea válido.', 'danger')
        return redirect(url_for('main.auditoria_en_vivo'))


@main.route('/cierre_ejercicio', methods=['GET'])
@login_required
def cierre_ejercicio_vista():
    """
    Vista de confirmación para el Cierre de Ejercicio Anual.
    Restringida exclusivamente al Presidente Municipal (rol Presidente) o Admin.
    Muestra el resumen presupuestal del año en curso y los cierres históricos.
    """
    try:
        if not current_user.puede_cerrar_ejercicio():
            flash('Solo el Presidente Municipal puede realizar el Cierre de Ejercicio Anual.', 'danger')
            return redirect(url_for('main.dashboard'))

        anio_actual = datetime.now().year

        presupuesto_ejercido = db.session.query(
            func.coalesce(func.sum(Solicitud.Monto), 0)
        ).filter(
            Solicitud.Estatus == 'Aprobado',
            func.strftime('%Y', Solicitud.Fecha_Solicitud) == str(anio_actual)
        ).scalar() or 0

        total_aprobadas = Solicitud.query.filter(
            Solicitud.Estatus == 'Aprobado',
            func.strftime('%Y', Solicitud.Fecha_Solicitud) == str(anio_actual)
        ).count()

        ya_cerrado = CierreEjercicio.query.filter_by(anio=anio_actual).first()
        historial_cierres = CierreEjercicio.query.order_by(CierreEjercicio.anio.desc()).all()

        return render_template('cierre_ejercicio.html',
                              anio_actual=anio_actual,
                              presupuesto_ejercido=float(presupuesto_ejercido),
                              total_aprobadas=total_aprobadas,
                              ya_cerrado=ya_cerrado,
                              historial_cierres=historial_cierres)
    except Exception as e:
        current_app.logger.error(f"Error en vista de cierre de ejercicio: {str(e)}")
        flash('Error al cargar la información del cierre de ejercicio.', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/cierre_ejercicio/confirmar', methods=['POST'])
@login_required
def cierre_ejercicio_confirmar():
    """
    Ejecuta el Cierre de Ejercicio Anual:
    1. Verifica que el usuario sea Presidente Municipal o Admin.
    2. Genera un respaldo (backup) físico de la base de datos SQLite.
    3. Congela el presupuesto total ejercido del año en un registro CierreEjercicio.
    4. Registra la acción en AuditoriaLog con usuario, fecha, IP y detalle del cambio.
    """
    try:
        if not current_user.puede_cerrar_ejercicio():
            flash('Solo el Presidente Municipal puede realizar el Cierre de Ejercicio Anual.', 'danger')
            return redirect(url_for('main.dashboard'))

        anio_actual = datetime.now().year

        if CierreEjercicio.query.filter_by(anio=anio_actual).first():
            flash(f'El ejercicio del año {anio_actual} ya fue cerrado previamente.', 'warning')
            return redirect(url_for('main.cierre_ejercicio_vista'))

        presupuesto_ejercido = db.session.query(
            func.coalesce(func.sum(Solicitud.Monto), 0)
        ).filter(
            Solicitud.Estatus == 'Aprobado',
            func.strftime('%Y', Solicitud.Fecha_Solicitud) == str(anio_actual)
        ).scalar() or 0

        total_aprobadas = Solicitud.query.filter(
            Solicitud.Estatus == 'Aprobado',
            func.strftime('%Y', Solicitud.Fecha_Solicitud) == str(anio_actual)
        ).count()

        # 1. Generar respaldo físico de la base de datos antes de cerrar el ejercicio
        ruta_backup = None
        try:
            ruta_bd_origen = os.path.abspath(os.path.join('database', 'apoyos.db'))
            directorio_backups = os.path.abspath('backups')
            os.makedirs(directorio_backups, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_backup = f'apoyos_backup_cierre_ejercicio_{anio_actual}_{timestamp}.db'
            ruta_backup = os.path.join(directorio_backups, nombre_backup)

            if os.path.exists(ruta_bd_origen):
                shutil.copy2(ruta_bd_origen, ruta_backup)
            else:
                current_app.logger.warning("No se encontró el archivo físico de la base de datos para respaldar.")
                ruta_backup = None
        except Exception as backup_error:
            current_app.logger.error(f"Error al generar backup de cierre de ejercicio: {str(backup_error)}")
            ruta_backup = None

        # 2. Registrar el cierre de ejercicio (congela el presupuesto del año)
        nuevo_cierre = CierreEjercicio(
            anio=anio_actual,
            presupuesto_total_ejercido=presupuesto_ejercido,
            total_solicitudes_aprobadas=total_aprobadas,
            usuario_id=current_user.id,
            ruta_backup=ruta_backup,
            observaciones=request.form.get('observaciones', '')
        )
        db.session.add(nuevo_cierre)

        # 3. Trazabilidad total: registrar en AuditoriaLog (usuario, fecha, ip, detalle)
        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion=f"Cierre de Ejercicio Anual {anio_actual}",
            tabla_afectada='cierres_ejercicio',
            registro_id=str(anio_actual),
            ip_address=request.remote_addr,
            detalle_cambio=(
                f"Cierre de ejercicio {anio_actual} realizado por {current_user.nombre} "
                f"({current_user.rol}). Presupuesto total ejercido: ${float(presupuesto_ejercido):.2f}. "
                f"Solicitudes aprobadas: {total_aprobadas}. "
                f"Backup generado en: {ruta_backup or 'No se pudo generar backup'}."
            )
        )
        db.session.add(auditoria)

        db.session.commit()

        # MÓDULO PORTABLE: respaldo automático en el Escritorio del
        # usuario (además del backup institucional en /backups).
        respaldar_en_escritorio(motivo=f"Cierre de Ejercicio Anual {anio_actual}", usuario_nombre=current_user.nombre)

        flash(f'Ejercicio {anio_actual} cerrado exitosamente. Presupuesto ejercido: ${float(presupuesto_ejercido):,.2f}. '
              f'Respaldo generado correctamente.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al cerrar ejercicio anual: {str(e)}")
        flash(f'Error al cerrar el ejercicio anual: {str(e)}', 'danger')

    return redirect(url_for('main.cierre_ejercicio_vista'))


# ============================================
# ADMINISTRACIÓN DE USUARIOS (SOLO ADMIN)
# Permite registrar el correo de Gmail exacto del director para que
# el sistema lo reconozca al iniciar sesión con Google (OAuth 2.0).
# ============================================

@main.route('/admin/usuarios', methods=['GET'])
@login_required
@admin_required
def admin_usuarios():
    """Lista todos los usuarios del sistema (solo Administrador)."""
    try:
        usuarios = Usuario.query.order_by(Usuario.nombre.asc()).all()
        dependencias = Dependencia.query.order_by(Dependencia.nombre.asc()).all()
        return render_template('admin_usuarios.html', usuarios=usuarios, dependencias=dependencias)
    except Exception as e:
        current_app.logger.error(f"Error al listar usuarios: {str(e)}")
        flash('Error al cargar la lista de usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_usuario_nuevo():
    """Crea un nuevo usuario, incluyendo el correo de Gmail para login con Google."""
    dependencias = Dependencia.query.order_by(Dependencia.nombre.asc()).all()

    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            rol = request.form.get('rol', 'Director')
            dependencia_id = request.form.get('dependencia_id') or None
            activo = request.form.get('activo') == 'on'

            if not nombre or not email or not password:
                flash('Nombre, correo electrónico y contraseña son obligatorios.', 'warning')
                return render_template('admin_usuario_form.html', usuario=None, dependencias=dependencias)

            if Usuario.query.filter(func.lower(Usuario.email) == email).first():
                flash('Ya existe un usuario registrado con ese correo electrónico.', 'danger')
                return render_template('admin_usuario_form.html', usuario=None, dependencias=dependencias)

            nuevo_usuario = Usuario(
                nombre=nombre,
                email=email,
                password=generate_password_hash(password),
                rol=rol,
                dependencia_id=int(dependencia_id) if dependencia_id else None,
                activo=activo
            )
            db.session.add(nuevo_usuario)
            db.session.flush()

            # Trazabilidad total: registrar la creación del usuario en AuditoriaLog
            auditoria = AuditoriaLog(
                user_id=current_user.id,
                accion="Creación de usuario",
                tabla_afectada='usuarios',
                registro_id=str(nuevo_usuario.id),
                ip_address=request.remote_addr,
                detalle_cambio=(
                    f"El administrador {current_user.nombre} creó al usuario '{nombre}' "
                    f"({email}) con rol '{rol}'."
                )
            )
            db.session.add(auditoria)
            db.session.commit()

            flash(f'Usuario "{nombre}" creado exitosamente. Ya puede iniciar sesión con Google usando {email}.', 'success')
            return redirect(url_for('main.admin_usuarios'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error al crear usuario: {str(e)}")
            flash(f'Error al crear el usuario: {str(e)}', 'danger')
            return render_template('admin_usuario_form.html', usuario=None, dependencias=dependencias)

    return render_template('admin_usuario_form.html', usuario=None, dependencias=dependencias)


@main.route('/admin/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_usuario_editar(usuario_id):
    """
    Edita un usuario existente. Permite registrar/actualizar el correo
    de Gmail exacto para que el director pueda iniciar sesión con Google.
    """
    usuario = Usuario.query.get_or_404(usuario_id)
    dependencias = Dependencia.query.order_by(Dependencia.nombre.asc()).all()

    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            rol = request.form.get('rol', usuario.rol)
            dependencia_id = request.form.get('dependencia_id') or None
            activo = request.form.get('activo') == 'on'

            if not nombre or not email:
                flash('Nombre y correo electrónico son obligatorios.', 'warning')
                return render_template('admin_usuario_form.html', usuario=usuario, dependencias=dependencias)

            # Verificar que el correo no esté en uso por otro usuario
            existente = Usuario.query.filter(func.lower(Usuario.email) == email, Usuario.id != usuario.id).first()
            if existente:
                flash('Ese correo electrónico ya está registrado por otro usuario.', 'danger')
                return render_template('admin_usuario_form.html', usuario=usuario, dependencias=dependencias)

            email_anterior = usuario.email
            usuario.nombre = nombre
            usuario.email = email
            usuario.rol = rol
            usuario.dependencia_id = int(dependencia_id) if dependencia_id else None
            usuario.activo = activo

            if password:
                usuario.password = generate_password_hash(password)

            # Trazabilidad total: registrar la edición del usuario en AuditoriaLog
            auditoria = AuditoriaLog(
                user_id=current_user.id,
                accion="Edición de usuario",
                tabla_afectada='usuarios',
                registro_id=str(usuario.id),
                ip_address=request.remote_addr,
                detalle_cambio=(
                    f"El administrador {current_user.nombre} editó al usuario '{nombre}'. "
                    f"Correo: '{email_anterior}' -> '{email}'. Rol: '{rol}'. Activo: {activo}."
                )
            )
            db.session.add(auditoria)
            db.session.commit()

            flash(f'Usuario "{nombre}" actualizado exitosamente.', 'success')
            return redirect(url_for('main.admin_usuarios'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error al editar usuario: {str(e)}")
            flash(f'Error al editar el usuario: {str(e)}', 'danger')
            return render_template('admin_usuario_form.html', usuario=usuario, dependencias=dependencias)

    return render_template('admin_usuario_form.html', usuario=usuario, dependencias=dependencias)


# ============================================
# MÓDULO DE SERVICIOS PÚBLICOS (CONTROL DE COMBUSTIBLE)
# "Mecánica de Tsuru": captura idéntica a las 5 bitácoras físicas del
# corralón municipal. CERO BLOQUEOS OPERATIVOS: ningún dato detiene un
# despacho de combustible. La validación de rendimiento es siempre
# pasiva (solo genera una bandera visual en el Dashboard).
# ============================================

def _guardar_archivo_combustible(archivo, prefijo):
    """Guarda una fotografía (odómetro o vale) del módulo de combustible.
    Nunca lanza excepción hacia el llamador: si falla, retorna None para
    no bloquear jamás el registro del despacho."""
    try:
        if not archivo or archivo.filename == '':
            return None

        directorio = current_app.config.get('UPLOAD_FOLDER_COMBUSTIBLE')
        if not directorio:
            directorio = os.path.join(current_app.static_folder, 'uploads', 'combustible')
        os.makedirs(directorio, exist_ok=True)

        import uuid
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_base = secure_filename(archivo.filename)
        nombre_unico = f"{prefijo}_{timestamp}_{uuid.uuid4().hex[:8]}_{nombre_base}"
        ruta_completa = os.path.join(directorio, nombre_unico)
        archivo.save(ruta_completa)

        # Ruta relativa para construir url_for('static', filename=...)
        return os.path.join('uploads', 'combustible', nombre_unico).replace('\\', '/')
    except Exception as e:
        current_app.logger.warning(f"No se pudo guardar archivo de combustible ({prefijo}): {str(e)}")
        return None


def _registro_a_dict(registro):
    """Convierte un BitacoraCombustible (o similar) al dict plano que
    espera la función PURA evaluar_registro()."""
    return {
        'tipo_bitacora': registro.tipo_bitacora,
        'km_anterior': registro.km_anterior,
        'km_actual': registro.km_actual,
        'horometro_anterior': registro.horometro_anterior,
        'horometro_actual': registro.horometro_actual,
        'litros': registro.litros,
        'capacidad_tanque': (registro.unidad.capacidad_tanque if registro.unidad_id and registro.unidad
                              else (registro.equipo.capacidad_tanque if registro.equipo_id and registro.equipo else None)),
        'tanque_lleno': registro.tanque_lleno,
        'foto_vale': registro.foto_vale,
        'folio_vale': registro.folio_vale,
        'tiene_factura': registro.tiene_factura,
        'precio_por_litro': float(registro.precio_por_litro) if registro.precio_por_litro else None,
        'beneficiario_curp': registro.beneficiario_curp,
    }


def _construir_contexto_alertas(registro, unidad_obj=None, equipo_obj=None):
    """
    Calcula el 'contexto' estadístico que requiere evaluar_registro():
    folio repetido, mediana histórica de rendimiento de la unidad,
    cargas previas, días desde la última carga, promedio de precio por
    litro, días desde el último apoyo ciudadano y días sin foto de
    tablero. Cualquier error en estas consultas se ignora (NUNCA bloquea).
    """
    contexto = {'umbrales': ConfiguracionUmbrales.obtener_vigente()}
    try:
        if registro.folio_vale:
            existente = BitacoraCombustible.query.filter(
                BitacoraCombustible.folio_vale == registro.folio_vale,
                BitacoraCombustible.estatus == 'ACTIVO',
                BitacoraCombustible.id != (registro.id or -1)
            ).first()
            contexto['folio_repetido'] = existente is not None
    except Exception:
        contexto['folio_repetido'] = False

    try:
        filtro_unidad = None
        if unidad_obj:
            filtro_unidad = BitacoraCombustible.unidad_id == unidad_obj.id
        elif equipo_obj:
            filtro_unidad = BitacoraCombustible.equipo_id == equipo_obj.id

        if filtro_unidad is not None:
            historicos = BitacoraCombustible.query.filter(
                filtro_unidad, BitacoraCombustible.estatus == 'ACTIVO'
            ).order_by(BitacoraCombustible.fecha.desc()).all()

            contexto['cargas_previas_unidad'] = len(historicos)

            rendimientos = []
            for h in historicos:
                if h.tanque_lleno:
                    r = None
                    if h.tipo_bitacora == 'MAQUINARIA' and h.horas_trabajo and h.litros:
                        r = h.litros / h.horas_trabajo if h.horas_trabajo > 0 else None
                    elif h.km_recorridos and h.litros and h.km_recorridos > 0:
                        r = h.km_recorridos / h.litros
                    if r:
                        rendimientos.append(r)
            if rendimientos:
                rendimientos.sort()
                n = len(rendimientos)
                mediana = rendimientos[n // 2] if n % 2 == 1 else (rendimientos[n // 2 - 1] + rendimientos[n // 2]) / 2
                contexto['mediana_rendimiento_unidad'] = mediana

            if historicos:
                ultima_fecha = historicos[0].fecha
                if ultima_fecha:
                    contexto['dias_desde_ultima_carga_unidad'] = (datetime.utcnow() - ultima_fecha).days

                con_foto = [h for h in historicos if h.foto_odometro or h.foto_horometro]
                if con_foto:
                    contexto['dias_desde_ultima_foto_tablero'] = (datetime.utcnow() - con_foto[0].fecha).days
                else:
                    contexto['dias_desde_ultima_foto_tablero'] = 9999
    except Exception:
        pass

    try:
        foraneas = BitacoraCombustible.query.filter(
            BitacoraCombustible.tipo_bitacora == 'FORANEA',
            BitacoraCombustible.precio_por_litro.isnot(None),
            BitacoraCombustible.estatus == 'ACTIVO'
        ).all()
        precios = [float(f.precio_por_litro) for f in foraneas if f.precio_por_litro]
        if precios:
            contexto['promedio_precio_litro'] = sum(precios) / len(precios)
    except Exception:
        pass

    try:
        if registro.beneficiario_curp:
            anterior = BitacoraCombustible.query.filter(
                BitacoraCombustible.beneficiario_curp == registro.beneficiario_curp,
                BitacoraCombustible.estatus == 'ACTIVO',
                BitacoraCombustible.id != (registro.id or -1)
            ).order_by(BitacoraCombustible.fecha.desc()).first()
            if anterior and anterior.fecha:
                contexto['dias_desde_ultimo_apoyo_ciudadano'] = (datetime.utcnow() - anterior.fecha).days
    except Exception:
        pass

    return contexto


# ================================================================
# ORDEN TÉCNICA MAESTRA - ARQUITECTURA MULTITANQUE (GASOLINA, DIÉSEL,
# UREA CON DOBLE BARRA SIMULTÁNEA) Y REPORTE SEMANAL CONSOLIDADO
# ================================================================

CAPACIDAD_TANQUE_DEFAULT = {
    TipoFluidoEnum.GASOLINA.value: 1000.0,
    TipoFluidoEnum.DIESEL.value: 1000.0,
    TipoFluidoEnum.UREA.value: 500.0,
}

MAPA_TIPO_COMBUSTIBLE_A_FLUIDO = {
    'gasolina': TipoFluidoEnum.GASOLINA.value,
    'magna': TipoFluidoEnum.GASOLINA.value,
    'premium': TipoFluidoEnum.GASOLINA.value,
    'diesel': TipoFluidoEnum.DIESEL.value,
    'diésel': TipoFluidoEnum.DIESEL.value,
    'urea': TipoFluidoEnum.UREA.value,
}


def _resolver_tipo_fluido_asignacion(asignacion):
    """
    CERO CAÍDAS: determina a qué fluido (Gasolina/Diésel/Urea) pertenece
    una Asignación de Combustible, a partir de tipo_combustible o del
    tipo de bitácora (UREA siempre descuenta del fluido Urea; LUBRICANTE
    no descuenta de ningún tanque de combustible). Nunca lanza
    excepción; por defecto GASOLINA.
    """
    try:
        if asignacion.tipo_asignacion == TipoBitacoraEnum.UREA.value:
            return TipoFluidoEnum.UREA.value
        if asignacion.tipo_asignacion == TipoBitacoraEnum.LUBRICANTE.value:
            return None
        texto = (asignacion.tipo_combustible or '').strip().lower()
        return MAPA_TIPO_COMBUSTIBLE_A_FLUIDO.get(texto, TipoFluidoEnum.GASOLINA.value)
    except Exception:
        return TipoFluidoEnum.GASOLINA.value


def calcular_estado_multitanque():
    """
    ORDEN TÉCNICA MAESTRA: calcula, para cada uno de los 3 fluidos
    (Gasolina, Diésel, Urea), el estado independiente de sus 2 tanques
    posibles (Tanque 1 Principal y Tanque 2 Secundario/Provisional):
    capacidad, litros disponibles, porcentaje y color de alerta. Las
    Cargas Foráneas NUNCA descuentan litros. Blindado con try/except por
    fluido: si uno falla, los demás siguen mostrándose con normalidad.

    TANQUE SECUENCIAL AUTOMÁTICO: si el tanque actualmente Principal se
    agota (0 L disponibles) y el Secundario tiene litros disponibles, el
    sistema promueve automáticamente al Secundario a Principal (y marca
    el agotado como no-Principal), emitiendo una alerta visual pasiva
    ('alerta_rotacion') que el Dashboard muestra sin bloquear ninguna
    operación.
    """
    resultado = {}
    for fluido in TipoFluidoEnum:
        try:
            tanques_info = []
            alerta_rotacion = None
            litros_abasto_fluido = sum(
                float(r.litros_recibidos or 0)
                for r in RegistroAbastoFluido.query.filter_by(tipo_fluido=fluido.value).all()
            )
            asignaciones_fluido = [
                a for a in AsignacionCombustible.query.all()
                if a.tipo_asignacion != TipoBitacoraEnum.FORANEA.value
                and a.estatus != EstatusAsignacionEnum.CANCELADA.value
                and _resolver_tipo_fluido_asignacion(a) == fluido.value
            ]
            litros_consumidos_fluido = sum(float(a.litros_asignados or 0) for a in asignaciones_fluido)

            # ----------------------------------------------------------
            # CONSUMO SECUENCIAL REAL (no proporcional): el tanque
            # Principal se drena PRIMERO con todo el consumo; solo el
            # EXCEDENTE (lo que el Principal ya no puede cubrir) se
            # descuenta del Secundario. Así, si el Principal se agota,
            # el Secundario entra en servicio automáticamente.
            # ----------------------------------------------------------
            configs = {}
            capacidades = {}
            litros_abasto_por_tanque = {}
            for numero_tanque in (1, 2):
                try:
                    config = ConfiguracionTanque.obtener_o_crear(
                        fluido.value, numero_tanque,
                        capacidad_default=CAPACIDAD_TANQUE_DEFAULT.get(fluido.value, 1000.0)
                    )
                    configs[numero_tanque] = config
                    capacidades[numero_tanque] = float(config.capacidad_litros or 1000.0)
                    litros_abasto_por_tanque[numero_tanque] = sum(
                        float(r.litros_recibidos or 0)
                        for r in RegistroAbastoFluido.query.filter_by(
                            tipo_fluido=fluido.value, numero_tanque=numero_tanque
                        ).all()
                    )
                except Exception:
                    configs[numero_tanque] = None
                    capacidades[numero_tanque] = 0.0
                    litros_abasto_por_tanque[numero_tanque] = 0.0

            datos_tanques_calculados = {}
            try:
                if configs.get(1) and configs.get(2):
                    numero_principal = 1 if configs[1].es_principal else (2 if configs[2].es_principal else 1)
                    numero_secundario = 2 if numero_principal == 1 else 1

                    abasto_principal = litros_abasto_por_tanque[numero_principal]
                    abasto_secundario = litros_abasto_por_tanque[numero_secundario]

                    litros_disponibles_principal = max(0.0, abasto_principal - litros_consumidos_fluido)
                    excedente_hacia_secundario = max(0.0, litros_consumidos_fluido - abasto_principal)
                    litros_disponibles_secundario = max(0.0, abasto_secundario - excedente_hacia_secundario)

                    datos_tanques_calculados[numero_principal] = {
                        'config': configs[numero_principal], 'capacidad': capacidades[numero_principal],
                        'litros_disponibles': min(capacidades[numero_principal], litros_disponibles_principal),
                    }
                    datos_tanques_calculados[numero_secundario] = {
                        'config': configs[numero_secundario], 'capacidad': capacidades[numero_secundario],
                        'litros_disponibles': min(capacidades[numero_secundario], litros_disponibles_secundario),
                    }

                    # TANQUE SECUENCIAL AUTOMÁTICO: si el Principal quedó
                    # en 0 L y el Secundario (activo) tiene litros
                    # disponibles, se promueve automáticamente a Principal.
                    if (litros_disponibles_principal <= 0 and configs[numero_secundario].activo
                            and litros_disponibles_secundario > 0):
                        configs[numero_principal].es_principal = False
                        configs[numero_secundario].es_principal = True
                        db.session.commit()
                        alerta_rotacion = (
                            f"El Tanque {numero_principal} de "
                            f"{TipoFluidoEnum.nombre_completo(fluido.value)} se agotó. El Tanque "
                            f"{numero_secundario} (respaldo) entró en servicio como Principal."
                        )
            except Exception as e:
                current_app.logger.warning(f"Error al evaluar consumo secuencial de {fluido.value}: {str(e)}")
                db.session.rollback()

            for numero_tanque in (1, 2):
                try:
                    datos = datos_tanques_calculados.get(numero_tanque)
                    if not datos:
                        raise ValueError("Sin datos calculados para este tanque")
                    config = datos['config']
                    capacidad = datos['capacidad']
                    litros_disponibles = datos['litros_disponibles']
                    porcentaje = round((litros_disponibles / capacidad) * 100, 1) if capacidad else 0.0
                    if porcentaje > 40:
                        color = 'success'
                    elif porcentaje >= 15:
                        color = 'warning'
                    else:
                        color = 'danger'

                    tanques_info.append({
                        'numero_tanque': numero_tanque,
                        'activo': bool(config.activo),
                        'es_principal': bool(config.es_principal),
                        'capacidad': capacidad,
                        'litros_disponibles': round(litros_disponibles, 1),
                        'porcentaje': porcentaje,
                        'color': color,
                    })
                except Exception:
                    tanques_info.append({
                        'numero_tanque': numero_tanque, 'activo': False, 'es_principal': (numero_tanque == 1),
                        'capacidad': 0.0, 'litros_disponibles': 0.0, 'porcentaje': 0.0, 'color': 'secondary',
                    })

            resultado[fluido.value] = {
                'nombre': TipoFluidoEnum.nombre_completo(fluido.value),
                'litros_abasto_total': round(litros_abasto_fluido, 1),
                'litros_consumidos_total': round(litros_consumidos_fluido, 1),
                'tanques': tanques_info,
                'alerta_rotacion': alerta_rotacion,
            }
        except Exception as e:
            current_app.logger.warning(f"Error al calcular estado multitanque de {fluido.value}: {str(e)}")
            resultado[fluido.value] = {
                'nombre': TipoFluidoEnum.nombre_completo(fluido.value),
                'litros_abasto_total': 0.0, 'litros_consumidos_total': 0.0,
                'tanques': [
                    {'numero_tanque': 1, 'activo': True, 'es_principal': True, 'capacidad': 0.0, 'litros_disponibles': 0.0, 'porcentaje': 0.0, 'color': 'secondary'},
                    {'numero_tanque': 2, 'activo': False, 'es_principal': False, 'capacidad': 0.0, 'litros_disponibles': 0.0, 'porcentaje': 0.0, 'color': 'secondary'},
                ],
                'alerta_rotacion': None,
            }
    return resultado


def calcular_reporte_semanal_consolidado(fecha_fin=None):
    """
    ORDEN TÉCNICA MAESTRA - REPORTE SEMANAL CONSOLIDADO: unifica, para
    los últimos 7 días (hasta fecha_fin, por defecto hoy), los registros
    de las 11 bitácoras oficiales en un único resumen ejecutivo
    auditable: litros y folios por bitácora, costos por fluido, y un
    balance simple de eficiencia. CERO CAÍDAS: cualquier error se
    captura y retorna un resumen vacío seguro.
    """
    try:
        fecha_fin = fecha_fin or datetime.utcnow()
        fecha_inicio = fecha_fin - timedelta(days=7)

        # COHERENCIA CON EL CÁLCULO DE TANQUES (calcular_estado_
        # multitanque): las asignaciones CANCELADAS nunca descuentan
        # litros del tanque real, por lo que TAMPOCO deben contarse como
        # consumo/costo en el Reporte Semanal. Sin esta exclusión, el
        # desglose por fluido del reporte no coincidía con los litros
        # realmente descontados de los tanques (discrepancia de costos).
        asignaciones_semana = AsignacionCombustible.query.filter(
            AsignacionCombustible.fecha_creacion >= fecha_inicio,
            AsignacionCombustible.fecha_creacion <= fecha_fin,
            AsignacionCombustible.estatus != EstatusAsignacionEnum.CANCELADA.value
        ).all()

        costo_litro_vigente = ConfiguracionCombustible.obtener_costo_vigente()

        desglose_por_bitacora = []
        total_litros_semana = 0.0
        total_folios_semana = 0
        total_costo_semana = 0.0

        for tipo in TipoBitacoraEnum:
            registros_tipo = [a for a in asignaciones_semana if a.tipo_asignacion == tipo.value]
            litros_tipo = sum(float(a.litros_asignados or 0) for a in registros_tipo)
            costo_tipo = round(litros_tipo * float(costo_litro_vigente or 0), 2)
            desglose_por_bitacora.append({
                'nombre': TipoBitacoraEnum.nombre_completo(tipo.value),
                'folios': len(registros_tipo),
                'litros': round(litros_tipo, 2),
                'costo': costo_tipo,
            })
            total_litros_semana += litros_tipo
            total_folios_semana += len(registros_tipo)
            total_costo_semana += costo_tipo

        desglose_por_fluido = []
        total_litros_consumidos_fluidos = 0.0
        total_litros_abastecidos_fluidos = 0.0
        total_costo_abasto_fluidos = 0.0
        for fluido in TipoFluidoEnum:
            # Misma regla EXACTA que calcular_estado_multitanque(): las
            # Cargas Foráneas y las asignaciones CANCELADAS (ya excluidas
            # arriba en asignaciones_semana) nunca descuentan litros de
            # ningún tanque, por lo que tampoco se cuentan aquí.
            registros_fluido = [
                a for a in asignaciones_semana
                if a.tipo_asignacion != TipoBitacoraEnum.FORANEA.value
                and _resolver_tipo_fluido_asignacion(a) == fluido.value
            ]
            litros_fluido = sum(float(a.litros_asignados or 0) for a in registros_fluido)
            abastos_fluido_semana = RegistroAbastoFluido.query.filter(
                RegistroAbastoFluido.tipo_fluido == fluido.value,
                RegistroAbastoFluido.fecha >= fecha_inicio,
                RegistroAbastoFluido.fecha <= fecha_fin
            ).all()
            costo_abasto_fluido = sum(float(r.costo_total or 0) for r in abastos_fluido_semana)
            litros_abastecidos_fluido = sum(float(r.litros_recibidos or 0) for r in abastos_fluido_semana)
            desglose_por_fluido.append({
                'nombre': TipoFluidoEnum.nombre_completo(fluido.value),
                'litros_consumidos': round(litros_fluido, 2),
                'litros_abastecidos': round(litros_abastecidos_fluido, 2),
                'costo_abasto': round(costo_abasto_fluido, 2),
            })
            total_litros_consumidos_fluidos += litros_fluido
            total_litros_abastecidos_fluidos += litros_abastecidos_fluido
            total_costo_abasto_fluidos += costo_abasto_fluido

        vales_con_alerta = [a for a in asignaciones_semana if a.excede_umbral_rendimiento()]
        indicador_positivo = len(asignaciones_semana) - len(vales_con_alerta)
        indicador_negativo = len(vales_con_alerta)

        return {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'total_litros': round(total_litros_semana, 2),
            'total_folios': total_folios_semana,
            'total_costo': round(total_costo_semana, 2),
            'desglose_por_bitacora': desglose_por_bitacora,
            'desglose_por_fluido': desglose_por_fluido,
            'total_litros_consumidos_fluidos': round(total_litros_consumidos_fluidos, 2),
            'total_litros_abastecidos_fluidos': round(total_litros_abastecidos_fluidos, 2),
            'total_costo_abasto_fluidos': round(total_costo_abasto_fluidos, 2),
            'indicador_positivo': indicador_positivo,
            'indicador_negativo': indicador_negativo,
        }
    except Exception as e:
        current_app.logger.error(f"Error al calcular el Reporte Semanal Consolidado: {str(e)}", exc_info=True)
        return {
            'fecha_inicio': None, 'fecha_fin': None, 'total_litros': 0.0, 'total_folios': 0,
            'total_costo': 0.0, 'desglose_por_bitacora': [], 'desglose_por_fluido': [],
            'total_litros_consumidos_fluidos': 0.0, 'total_litros_abastecidos_fluidos': 0.0,
            'total_costo_abasto_fluidos': 0.0,
            'indicador_positivo': 0, 'indicador_negativo': 0,
        }


@main.route('/servicios_publicos')
@main.route('/servicios_publicos/combustible')
@login_required
@servicios_publicos_required
def servicios_publicos():
    """Dashboard del Módulo de Servicios Públicos - Control de Combustible."""
    try:
        registros = BitacoraCombustible.query.order_by(BitacoraCombustible.fecha.desc()).all()

        hoy = datetime.utcnow()
        registros_mes = [r for r in registros if r.fecha and r.fecha.month == hoy.month and r.fecha.year == hoy.year]

        total_litros_mes = sum(r.litros for r in registros_mes if r.litros)
        total_vales_mes = len(registros_mes)
        alertas_rendimiento = len([r for r in registros if r.alerta_rendimiento])

        # Totales por bitácora para las tarjetas de captura rápida
        totales_por_tipo = {}
        for tipo in TipoBitacoraEnum:
            registros_tipo = [r for r in registros if r.tipo_bitacora == tipo.value]
            totales_por_tipo[tipo.value] = {
                'cantidad': len(registros_tipo),
                'litros': sum(r.litros for r in registros_tipo if r.litros)
            }

        # Datos para la gráfica Chart.js: litros totales por tipo de bitácora
        litros_por_tipo = {tipo.value: totales_por_tipo[tipo.value]['litros'] for tipo in TipoBitacoraEnum}

        # Comunidades oficiales de Atarjea para el formulario de Apoyos Ciudadanos
        comunidades = Comunidad.query.order_by(Comunidad.nombre.asc()).all()

        # Padrón real de unidades (vehículos/maquinaria) y operadores municipales
        vehiculos = VehiculoMunicipal.query.filter_by(categoria='VEHICULO', activo=True).order_by(VehiculoMunicipal.nombre.asc()).all()
        maquinarias = VehiculoMunicipal.query.filter_by(categoria='MAQUINARIA', activo=True).order_by(VehiculoMunicipal.nombre.asc()).all()
        operadores = OperadorMunicipal.query.filter_by(activo=True).order_by(OperadorMunicipal.nombre.asc()).all()

        # MÓDULO FINANCIERO: costo vigente del litro y gasto total del mes en pesos
        costo_litro_vigente = ConfiguracionCombustible.obtener_costo_vigente()
        total_gastado_mes = sum(float(r.costo_total) for r in registros_mes if r.costo_total)
        if not total_gastado_mes:
            # Respaldo: si registros antiguos no tienen costo_total calculado, se estima
            total_gastado_mes = total_litros_mes * costo_litro_vigente

        gasto_por_tipo = {}
        for tipo in TipoBitacoraEnum:
            registros_tipo_mes = [r for r in registros_mes if r.tipo_bitacora == tipo.value]
            gasto_por_tipo[tipo.value] = sum(float(r.costo_total) for r in registros_tipo_mes if r.costo_total)

        es_finanzas = current_user.es_admin() or current_user.es_presidente()

        # FASE 2: catálogos reales para autollenado (selects)
        unidades = Unidad.query.filter_by(activa=True).order_by(Unidad.area.asc(), Unidad.nombre.asc()).all()
        equipos = Equipo.query.filter_by(activa=True).order_by(Equipo.nombre.asc()).all()
        conductores = Conductor.query.filter_by(activo=True).order_by(Conductor.nombre.asc()).all()
        autorizadores = Autorizador.query.filter_by(activo=True).order_by(Autorizador.nombre.asc()).all()
        despachadores = Despachador.query.filter_by(activo=True).order_by(Despachador.nombre.asc()).all()
        motivos = Motivo.query.filter_by(activo=True).order_by(Motivo.tipo_bitacora.asc()).all()
        areas = Area.query.filter_by(activa=True).order_by(Area.nombre.asc()).all()
        gasolineras = Gasolinera.query.filter_by(activa=True).order_by(Gasolinera.nombre.asc()).all()

        # FASE 2: alertas activas (semáforo) para mostrar en el dashboard,
        # calculadas sobre los registros ACTIVOS más recientes
        alertas_por_registro = {}
        for r in registros[:50]:  # limitar cálculo a los 50 más recientes por rendimiento
            try:
                ctx = _construir_contexto_alertas(r, r.unidad, r.equipo)
                alertas_r = evaluar_registro(_registro_a_dict(r), ctx)
                if alertas_r:
                    alertas_por_registro[r.id] = alertas_r
            except Exception:
                pass

        # FASE 2 (legacy): nivel aproximado del contenedor según bitácoras
        # físicas antiguas; se conserva solo para no romper el Excel export.
        total_entradas = sum(float(a.litros_recibidos) for a in RegistroAbasto.query.all())
        total_despachado_activo = sum(float(r.litros or 0) for r in registros if r.estatus == 'ACTIVO')
        umbrales_vigentes = ConfiguracionUmbrales.obtener_vigente()
        capacidad_contenedor = umbrales_vigentes.get('capacidad_contenedor_litros', 1000)
        nivel_contenedor_aprox = max(0, total_entradas - total_despachado_activo) if total_entradas > 0 else None

        # FORMULARIO N° 10: Asignaciones de Combustible (ciclo de vida del
        # vale separado del despacho físico). Las alertas son siempre
        # visuales pasivas, nunca bloquean la creación ni el avance de estatus.
        asignaciones = AsignacionCombustible.query.order_by(AsignacionCombustible.fecha_creacion.desc()).all()
        asignaciones_exceso_rendimiento = [a for a in asignaciones if a.excede_umbral_rendimiento()]
        conductores_licencia_vencida = [c for c in conductores if c.licencia_vencida()]
        estatus_asignacion = EstatusAsignacionEnum

        # ---------------------------------------------------------------
        # INVENTARIO REAL DEL TANQUE (1,000 L): "Cada litro se registra,
        # se vigila y se comprueba". El sistema queda unificado al 100%
        # bajo el Formulario N° 10, por lo que el inventario disponible
        # ES EL ACUMULADO HISTÓRICO REAL:
        #   Litros Disponibles = SUMA de litros de TODAS las facturas de
        #   abasto registradas - SUMA de litros de las asignaciones Local,
        #   Semanal, Viajes y Apoyos Ciudadanos (EMITIDA, ENTREGADA o
        #   COMPROBADA descuentan de inmediato al guardarse, ya que este
        #   cálculo se recalcula en cada carga del panel).
        #
        #   REGLA ESTRICTA (EXCLUSIÓN FORÁNEA): las asignaciones con
        #   tipo_asignacion == 'FORANEA' (Cargas Foráneas) NUNCA restan
        #   litros del tanque municipal, porque esa carga ocurre física
        #   y administrativamente en gasolineras externas con convenio,
        #   no en el tanque de 1,000 L del corralón municipal.
        # Es un indicador visual pasivo: nunca bloquea la creación de un
        # nuevo vale aunque el inventario llegue a cero o sea negativo.
        # ---------------------------------------------------------------
        # ORDEN TÉCNICA MAESTRA - ARQUITECTURA MULTITANQUE (Gasolina,
        # Diésel, Urea con doble barra simultánea): se calcula aquí,
        # blindado con try/except interno, el estado independiente de
        # hasta 2 tanques por cada uno de los 3 fluidos. Nunca bloquea
        # ni interrumpe la carga del Dashboard ante cualquier dato
        # faltante o corrupto; ante error, cada fluido cae a un estado
        # "vacío" seguro.
        estado_multitanque = calcular_estado_multitanque()

        # MÓDULO DE REPORTE SEMANAL CONSOLIDADO: se calcula aquí mismo
        # (con su propio blindaje try/except interno) para que la
        # tarjeta-resumen esté disponible de inmediato en el Dashboard,
        # sin necesidad de una petición adicional del navegador.
        reporte_semanal = calcular_reporte_semanal_consolidado()

        TANQUE_CAPACIDAD_LITROS = 1000.0
        litros_abasto_total = sum(float(a.litros_recibidos) for a in RegistroAbasto.query.all())
        litros_autorizados_total = sum(
            float(a.litros_asignados or 0)
            for a in asignaciones
            if a.estatus != EstatusAsignacionEnum.CANCELADA.value
            and a.tipo_asignacion != TipoBitacoraEnum.FORANEA.value
        )
        tanque_litros_disponibles = min(
            TANQUE_CAPACIDAD_LITROS,
            max(0.0, litros_abasto_total - litros_autorizados_total)
        )
        tanque_porcentaje = round((tanque_litros_disponibles / TANQUE_CAPACIDAD_LITROS) * 100, 1)
        if tanque_porcentaje > 40:
            tanque_color = 'success'
        elif tanque_porcentaje >= 15:
            tanque_color = 'warning'
        else:
            tanque_color = 'danger'

        registros_abasto = RegistroAbasto.query.order_by(RegistroAbasto.fecha.desc()).limit(15).all()

        # ORDEN TÉCNICA MAESTRA - HISTORIAL DE ABASTO MULTIFLUIDO: entradas
        # de Gasolina/Diésel/Urea (cada una con su propio tanque y precio
        # por litro), mostradas dentro de la tarjeta "Multitanque".
        registros_abasto_fluido = RegistroAbastoFluido.query.order_by(RegistroAbastoFluido.fecha.desc()).limit(20).all()

        # KPIs y gráfica UNIFICADOS al Formulario N° 10 (ya no a las
        # bitácoras físicas por tipo, que quedaron en desuso).
        asignaciones_mes = [a for a in asignaciones if a.fecha_creacion and a.fecha_creacion.month == hoy.month and a.fecha_creacion.year == hoy.year]
        total_litros_mes_asignacion = sum(float(a.litros_asignados or 0) for a in asignaciones_mes)
        total_vales_mes_asignacion = len(asignaciones_mes)
        alertas_rendimiento_asignacion = len(asignaciones_exceso_rendimiento)

        litros_por_tipo_asignacion = {}
        folios_por_tipo_asignacion = {}
        for tipo in TipoBitacoraEnum:
            litros_por_tipo_asignacion[tipo.value] = sum(
                float(a.litros_asignados or 0) for a in asignaciones if a.tipo_asignacion == tipo.value
            )
            folios_por_tipo_asignacion[tipo.value] = len(
                [a for a in asignaciones if a.tipo_asignacion == tipo.value]
            )

        gasto_por_tipo_asignacion = {
            tipo: round(litros * costo_litro_vigente, 2) for tipo, litros in litros_por_tipo_asignacion.items()
        }
        total_gastado_mes_asignacion = round(total_litros_mes_asignacion * costo_litro_vigente, 2)

        # PANEL EJECUTIVO DE DISTRIBUCIÓN (Gráfica de Dona): nombres
        # completos institucionales + litros y folios por tipo, para
        # alimentar directamente el Donut Chart sin cálculos en el cliente.
        panel_ejecutivo_dona = {
            TipoBitacoraEnum.nombre_completo(tipo): {
                'litros': round(litros_por_tipo_asignacion.get(tipo, 0.0), 2),
                'folios': folios_por_tipo_asignacion.get(tipo, 0),
            }
            for tipo in litros_por_tipo_asignacion.keys()
        }

        return render_template('servicios_publicos.html',
                               asignaciones=asignaciones,
                               asignaciones_exceso_rendimiento=asignaciones_exceso_rendimiento,
                               conductores_licencia_vencida=conductores_licencia_vencida,
                               estatus_asignacion=estatus_asignacion,
                               registros_abasto=registros_abasto,
                               registros_abasto_fluido=registros_abasto_fluido,
                               total_litros_mes=total_litros_mes_asignacion,
                               total_vales_mes=total_vales_mes_asignacion,
                               alertas_rendimiento=alertas_rendimiento_asignacion,
                               litros_por_tipo=litros_por_tipo_asignacion,
                               panel_ejecutivo_dona=panel_ejecutivo_dona,
                               estado_multitanque=estado_multitanque,
                               tipos_fluido=TipoFluidoEnum,
                               reporte_semanal=reporte_semanal,
                               comunidades=comunidades,
                               costo_litro_vigente=costo_litro_vigente,
                               total_gastado_mes=total_gastado_mes_asignacion,
                               gasto_por_tipo=gasto_por_tipo_asignacion,
                               es_finanzas=es_finanzas,
                               tipos_bitacora=TipoBitacoraEnum,
                               unidades=unidades, equipos=equipos, conductores=conductores,
                               autorizadores=autorizadores, despachadores=despachadores,
                               motivos=motivos, areas=areas, gasolineras=gasolineras,
                               nivel_contenedor_aprox=nivel_contenedor_aprox,
                               capacidad_contenedor=capacidad_contenedor,
                               tanque_capacidad_litros=TANQUE_CAPACIDAD_LITROS,
                               tanque_litros_disponibles=tanque_litros_disponibles,
                               tanque_porcentaje=tanque_porcentaje,
                               tanque_color=tanque_color,
                               litros_abasto_total=litros_abasto_total,
                               litros_autorizados_total=litros_autorizados_total)
    except Exception as e:
        current_app.logger.error(f"Error en dashboard de Servicios Públicos: {str(e)}")
        flash('Error al cargar el panel de Servicios Públicos.', 'danger')
        return redirect(url_for('main.dashboard'))



@main.route('/servicios_publicos/registrar', methods=['POST'])
@login_required
@servicios_publicos_required
def registrar_combustible():
    """
    CERO BLOQUEOS OPERATIVOS: registra el despacho de combustible de
    cualquiera de las 5 bitácoras físicas. Cualquier dato capturado se
    guarda de inmediato; la validación de rendimiento es pasiva y solo
    genera una bandera visual, nunca impide el guardado.
    """
    try:
        tipo_bitacora = request.form.get('tipo_bitacora', '').strip().upper()
        tipos_validos = [t.value for t in TipoBitacoraEnum]
        if tipo_bitacora not in tipos_validos:
            flash('Tipo de bitácora no reconocido.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        def _to_float(valor):
            try:
                return float(valor) if valor not in (None, '') else None
            except (ValueError, TypeError):
                return None

        folio_vale = request.form.get('folio_vale', '').strip()
        destino_comision = request.form.get('destino_comision', '').strip() or None
        vehiculo_nombre = request.form.get('vehiculo_nombre', '').strip() or None
        color = request.form.get('color', '').strip() or None
        modelo = request.form.get('modelo', '').strip() or None
        placa = request.form.get('placa', '').strip() or None
        km_inicial = _to_float(request.form.get('km_inicial'))
        km_final = _to_float(request.form.get('km_final'))
        horas_trabajo = _to_float(request.form.get('horas_trabajo'))
        litros = _to_float(request.form.get('litros')) or 0.0
        comunidad = request.form.get('comunidad', '').strip() or None
        responsable_nombre = request.form.get('responsable_nombre', '').strip() or 'No especificado'

        # ---------------- FASE 2: BLOQUE COMÚN ----------------
        hora = request.form.get('hora', '').strip() or None
        area_solicitante = request.form.get('area_solicitante', '').strip() or None
        motivo = request.form.get('motivo', '').strip() or None
        tipo_combustible = request.form.get('tipo_combustible', '').strip() or None
        autoriza_nombre = request.form.get('autoriza_nombre', '').strip() or None
        despacha_nombre = request.form.get('despacha_nombre', '').strip() or None
        es_emergencia = request.form.get('es_emergencia') == 'on'
        es_captura_posterior = request.form.get('es_captura_posterior') == 'on'
        observaciones = request.form.get('observaciones', '').strip() or None

        autoriza_id = None
        if autoriza_nombre:
            aut = Autorizador.query.filter(func.lower(Autorizador.nombre) == autoriza_nombre.lower()).first()
            autoriza_id = aut.id if aut else None

        despacha_id = None
        if despacha_nombre:
            desp = Despachador.query.filter(func.lower(Despachador.nombre) == despacha_nombre.lower()).first()
            despacha_id = desp.id if desp else None

        # ---------------- FASE 2: Unidad/Equipo (catálogo real, autollenado) ----------------
        unidad_id = None
        unidad_obj = None
        unidad_nombre_form = request.form.get('unidad_nombre', '').strip() or None
        if unidad_nombre_form:
            unidad_obj = Unidad.query.filter(func.lower(Unidad.nombre) == unidad_nombre_form.lower()).first()
            if unidad_obj:
                unidad_id = unidad_obj.id
                vehiculo_nombre = vehiculo_nombre or unidad_obj.nombre
                placa = placa or unidad_obj.placa
                color = color or unidad_obj.color
                modelo = modelo or unidad_obj.modelo
                tipo_combustible = tipo_combustible or unidad_obj.tipo_combustible

        equipo_id = None
        equipo_obj = None
        equipo_nombre_form = request.form.get('equipo_nombre', '').strip() or None
        if equipo_nombre_form:
            equipo_obj = Equipo.query.filter(func.lower(Equipo.nombre) == equipo_nombre_form.lower()).first()
            if equipo_obj:
                equipo_id = equipo_obj.id
                vehiculo_nombre = vehiculo_nombre or equipo_obj.nombre
                tipo_combustible = tipo_combustible or equipo_obj.tipo_combustible

        conductor_id = None
        if responsable_nombre and responsable_nombre != 'No especificado':
            cond = Conductor.query.filter(func.lower(Conductor.nombre) == responsable_nombre.lower()).first()
            conductor_id = cond.id if cond else None

        # km_anterior / horometro_anterior se AUTOLLENAN desde el catálogo
        # ("capturar menos y calcular más"): el operador solo escribe el
        # valor ACTUAL del tablero; el sistema ya conoce el anterior.
        km_anterior = unidad_obj.ultimo_km if unidad_obj else None
        km_actual = _to_float(request.form.get('km_actual'))
        tanque_lleno = request.form.get('tanque_lleno') == 'on'
        folio_solicitud = request.form.get('folio_solicitud', '').strip() or None
        km_estimados_ruta = _to_float(request.form.get('km_estimados_ruta'))

        horometro_anterior = equipo_obj.ultimo_horometro if equipo_obj else None
        horometro_actual = _to_float(request.form.get('horometro_actual'))
        actividad = request.form.get('actividad', '').strip() or None
        ubicacion_obra = request.form.get('ubicacion_obra', '').strip() or None

        # ---------------- FASE 2: EXTERNO ----------------
        vehiculo_descripcion = request.form.get('vehiculo_descripcion', '').strip() or None
        dependencia_propietaria = request.form.get('dependencia_propietaria', '').strip() or None
        motivo_apoyo = request.form.get('motivo_apoyo', '').strip() or None
        solicitante_nombre = request.form.get('solicitante_nombre', '').strip() or None
        oficio_autorizacion = request.form.get('oficio_autorizacion', '').strip() or None

        # ---------------- FASE 2: FORANEA ----------------
        gasolinera = request.form.get('gasolinera', '').strip() or None
        monto_pesos = _to_float(request.form.get('monto_pesos'))
        km_salida = _to_float(request.form.get('km_salida'))
        km_regreso = _to_float(request.form.get('km_regreso'))
        tiene_factura = request.form.get('tiene_factura', '').strip().upper() or None

        # ---------------- FASE 2: CIUDADANO ----------------
        beneficiario_nombre = request.form.get('beneficiario_nombre', '').strip() or None
        beneficiario_curp = request.form.get('beneficiario_curp', '').strip().upper() or None
        telefono = request.form.get('telefono', '').strip() or None
        descripcion_breve = (request.form.get('descripcion_breve', '').strip() or None)
        if descripcion_breve:
            descripcion_breve = descripcion_breve[:200]

        # El Formulario 5 (Apoyos Ciudadanos) no captura "responsable_nombre"
        # por separado: el responsable es el propio beneficiario.
        if tipo_bitacora == 'CIUDADANO' and beneficiario_nombre and responsable_nombre == 'No especificado':
            responsable_nombre = beneficiario_nombre

        # PADRÓN REAL DE UNIDADES: si el vehículo/maquinaria viene del catálogo
        # (menú desplegable), se completan automáticamente placa/color/modelo
        # y se vincula el registro al vehiculo_id correspondiente (FK).
        vehiculo_id = None
        if vehiculo_nombre:
            vehiculo_catalogo = VehiculoMunicipal.query.filter(
                func.lower(VehiculoMunicipal.nombre) == vehiculo_nombre.lower()
            ).first()
            if vehiculo_catalogo:
                vehiculo_id = vehiculo_catalogo.id
                placa = placa or vehiculo_catalogo.placa
                color = color or vehiculo_catalogo.color
                modelo = modelo or vehiculo_catalogo.modelo

        # PADRÓN REAL DE OPERADORES: vincula el responsable al catálogo si existe
        operador_id = None
        if responsable_nombre and responsable_nombre != 'No especificado':
            operador_catalogo = OperadorMunicipal.query.filter(
                func.lower(OperadorMunicipal.nombre) == responsable_nombre.lower()
            ).first()
            if operador_catalogo:
                operador_id = operador_catalogo.id

        # El Formulario 3 (Vehículos Externos) captura "vehiculo_descripcion"
        # en lugar de un catálogo; se usa como nombre de vehículo a mostrar.
        if tipo_bitacora == 'EXTERNO' and vehiculo_descripcion and not vehiculo_nombre:
            vehiculo_nombre = vehiculo_descripcion

        nuevo_registro = BitacoraCombustible(
            tipo_bitacora=tipo_bitacora,
            fecha=datetime.utcnow(),
            folio_vale=folio_vale or f"S/F-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            destino_comision=destino_comision,
            vehiculo_nombre=vehiculo_nombre,
            color=color,
            modelo=modelo,
            placa=placa,
            vehiculo_id=vehiculo_id,
            operador_id=operador_id,
            km_inicial=km_inicial,
            km_final=km_final,
            horas_trabajo=horas_trabajo,
            litros=litros,
            comunidad=comunidad,
            responsable_nombre=responsable_nombre,
            usuario_id=current_user.id,
            # Bloque común (Fase 2)
            hora=hora, area_solicitante=area_solicitante, motivo=motivo,
            tipo_combustible=tipo_combustible, autoriza_id=autoriza_id, despacha_id=despacha_id,
            es_emergencia=es_emergencia, es_captura_posterior=es_captura_posterior,
            observaciones=observaciones, capturado_por=current_user.nombre,
            capturado_en=datetime.utcnow(), estatus='ACTIVO', es_demo=False,
            # Unidad/Equipo/Conductor
            unidad_id=unidad_id, equipo_id=equipo_id, conductor_id=conductor_id,
            # OFICIAL
            km_anterior=km_anterior, km_actual=km_actual, tanque_lleno=tanque_lleno,
            folio_solicitud=folio_solicitud, km_estimados_ruta=km_estimados_ruta,
            # MAQUINARIA
            horometro_anterior=horometro_anterior, horometro_actual=horometro_actual,
            actividad=actividad, ubicacion_obra=ubicacion_obra,
            # EXTERNO
            vehiculo_descripcion=vehiculo_descripcion, dependencia_propietaria=dependencia_propietaria,
            motivo_apoyo=motivo_apoyo, solicitante_nombre=solicitante_nombre,
            oficio_autorizacion=oficio_autorizacion,
            # FORANEA
            gasolinera=gasolinera, monto_pesos=monto_pesos, km_salida=km_salida,
            km_regreso=km_regreso, tiene_factura=tiene_factura,
            # CIUDADANO
            beneficiario_nombre=beneficiario_nombre, beneficiario_curp=beneficiario_curp,
            telefono=telefono, descripcion_breve=descripcion_breve
        )

        # "Capturar menos y calcular más": deriva km_recorridos, horas_trabajo
        # y precio_por_litro a partir de los datos crudos capturados.
        nuevo_registro.calcular_campos_derivados()

        # MÓDULO FINANCIERO: costo monetario del despacho (Litros x Costo Unitario)
        nuevo_registro.calcular_costo()

        # Fotografías (opcionales salvo donde se indica OBLIGATORIA; nunca
        # bloquean el registro aunque falten o fallen al guardarse)
        mapa_fotos = {
            'foto_odometro': 'odometro', 'foto_vale': 'vale',
            'foto_horometro': 'horometro', 'foto_ticket': 'ticket',
            'foto_solicitud': 'solicitud', 'foto_identificacion': 'identificacion'
        }
        for campo_bd, prefijo in mapa_fotos.items():
            if campo_bd in request.files:
                ruta = _guardar_archivo_combustible(request.files[campo_bd], prefijo)
                if ruta:
                    setattr(nuevo_registro, campo_bd, ruta)

        # VALIDACIÓN PASIVA LEGADA: solo bandera visual, nunca bloqueo
        nuevo_registro.calcular_rendimiento()
        nuevo_registro.generar_hash()

        # FASE 2 - evaluar_registro(): semáforo de alertas en español simple
        # (función PURA, probada con pruebas unitarias). NUNCA bloquea.
        contexto_alertas = _construir_contexto_alertas(nuevo_registro, unidad_obj, equipo_obj)
        alertas = evaluar_registro(_registro_a_dict(nuevo_registro), contexto_alertas)

        db.session.add(nuevo_registro)
        db.session.flush()

        # Actualizar el "último KM/horómetro" del catálogo (autollenado futuro)
        try:
            if unidad_obj and km_actual is not None:
                unidad_obj.ultimo_km = km_actual
            if equipo_obj and horometro_actual is not None:
                equipo_obj.ultimo_horometro = horometro_actual
        except Exception:
            pass

        # Bitácora de sistema con hash encadenado (inmutabilidad)
        BitacoraSistemaLog.registrar(
            accion='CREAR_BITACORA_COMBUSTIBLE',
            registro_id=nuevo_registro.id,
            usuario_id=current_user.id,
            detalle=f"Folio {nuevo_registro.folio_vale} ({tipo_bitacora}) creado por {current_user.nombre}."
        )

        # Trazabilidad total
        resumen_alertas = '; '.join(a['mensaje'] for a in alertas) if alertas else 'Sin alertas.'
        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Registro de despacho de combustible",
            tabla_afectada='bitacoras_combustible',
            registro_id=str(nuevo_registro.id),
            ip_address=request.remote_addr,
            detalle_cambio=(
                f"{current_user.nombre} registró un despacho de {litros} L en la bitácora "
                f"'{tipo_bitacora}' (folio {nuevo_registro.folio_vale}, responsable: {responsable_nombre}). "
                f"Alertas: {resumen_alertas}"
            )
        )
        db.session.add(auditoria)
        db.session.commit()

        # MÓDULO PORTABLE: respaldo automático en el Escritorio tras
        # registrar un despacho de combustible (CERO BLOQUEOS).
        respaldar_en_escritorio(motivo=f"Despacho de combustible folio {nuevo_registro.folio_vale}", usuario_nombre=current_user.nombre)

        if alertas:
            hay_rojas = any(a['color'] == 'rojo' for a in alertas)
            categoria_flash = 'danger' if hay_rojas else 'warning'
            mensajes = ' | '.join(a['mensaje'] for a in alertas)
            flash(f'Registro guardado (Folio {nuevo_registro.folio_vale}). Alertas: {mensajes}', categoria_flash)
        else:
            flash(f'Registro guardado exitosamente. Folio: {nuevo_registro.folio_vale}', 'success')

        return redirect(url_for('main.servicios_publicos'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al registrar combustible: {str(e)}")
        # CERO BLOQUEOS: aun ante un error inesperado, se informa sin tecnicismos
        flash('No se pudo guardar el registro. Verifique los datos capturados e intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))



def _copiar_estilo_celda(origen, destino):
    """Copia estilo completo (fuente, relleno, borde, formato) de una celda a otra, preservando el diseño oficial de la plantilla."""
    destino.font = copy(origen.font)
    destino.border = copy(origen.border)
    destino.fill = copy(origen.fill)
    destino.number_format = copy(origen.number_format)
    destino.alignment = copy(origen.alignment)


# ================================================================
# ORDEN TÉCNICA MAESTRA - INTEGRACIÓN DE LAS 11 PLANTILLAS OFICIALES:
# Cada una de las 11 bitácoras oficiales del Municipio de Atarjea tiene
# su propio archivo .xlsx con encabezados, logotipo (Administración
# 2024-2027) y disposición de columnas particular. Esta configuración
# centraliza, por tipo de bitácora, cuál archivo cargar, en qué fila
# inician/terminan los datos y en qué columna exacta va cada campo
# lógico, de modo que exportar_excel_combustible() NUNCA mezcle datos
# entre plantillas ni dependa de índices fijos genéricos.
# ================================================================
CONFIG_PLANTILLAS_BITACORA = {
    TipoBitacoraEnum.OFICIAL.value: {
        'archivo': 'BITACORA_VEHICULOS_OFICIALES_2.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 24,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'vehiculo': 4,
                     'color': 5, 'modelo': 6, 'placa': 7, 'km_inicial': 8,
                     'km_final': 9, 'litros': 10, 'folio': 11, 'responsable': 12},
        'col_litros': 10,
    },
    TipoBitacoraEnum.AUTOBUS.value: {
        'archivo': 'BITACORA_AUTOBUSES.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 21,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'vehiculo': 4,
                     'color': 5, 'modelo': 6, 'placa': 7, 'km_inicial': 8,
                     'km_final': 9, 'litros': 10, 'folio': 11, 'responsable': 12},
        'col_litros': 10,
    },
    TipoBitacoraEnum.PIPA.value: {
        'archivo': 'BITACORA_PIPAS.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 24,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'vehiculo': 4,
                     'color': 5, 'modelo': 6, 'placa': 7, 'km_inicial': 8,
                     'km_final': 9, 'litros': 10, 'folio': 11, 'responsable': 12},
        'col_litros': 10,
    },
    TipoBitacoraEnum.MAQUINARIA.value: {
        'archivo': 'BITACORA_MAQUINARIA_PESADA.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 24,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'vehiculo': 4,
                     'color': 5, 'modelo': 6, 'placa': 7, 'km_inicial': 8,
                     'km_final': 9, 'litros': 10, 'folio': 11, 'responsable': 12},
        'col_litros': 10,
    },
    TipoBitacoraEnum.EQUIPO_MENOR.value: {
        'archivo': 'BITACORA_EQUIPO_MENOR.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 29,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'tipo_marca': 4,
                     'color': 5, 'horas': 6, 'litros': 7, 'folio': 8, 'responsable': 9},
        'col_litros': 7,
    },
    TipoBitacoraEnum.EXTERNO.value: {
        'archivo': 'BITACORA_VEHICULOS_EXTERNOS_2.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 29,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'vehiculo_caract': 5,
                     'placa': 7, 'litros': 9, 'folio': 10, 'responsable': 11},
        'col_litros': 9,
    },
    TipoBitacoraEnum.FORANEA.value: {
        'archivo': 'BITACORA_CARGAS_FORANEAS_2.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 18,
        'columnas': {'fecha': 1, 'destino': 3, 'comision': 4, 'km_inicial': 5,
                     'km_final': 6, 'litros': 7, 'folio': 9, 'responsable': 10},
        'col_litros': 7,
    },
    TipoBitacoraEnum.CIUDADANO.value: {
        'archivo': 'BITACORA_APOYOS_CIUDADANOS_2.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 20,
        'columnas': {'fecha': 1, 'comunidad': 2, 'vehiculo': 3, 'color': 4,
                     'modelo': 5, 'placa': 6, 'litros': 7, 'folio': 8, 'responsable': 9},
        'col_litros': 7,
    },
    TipoBitacoraEnum.CAMION_BASURA.value: {
        # ORDEN TÉCNICA MAESTRA (sincronización de catálogo Excel): bitácora
        # propia "BITACORA_CAMION_BASURA.xlsx", igual que las demás 10
        # plantillas oficiales. La medición real del Camión de Basura sigue
        # siendo EXCLUSIVAMENTE por Horómetro (Horas de Trabajo), por lo que
        # las columnas KM Inicial/KM Final de esta plantilla se rellenan con
        # el valor de horas_trabajo() para preservar el total de la bitácora
        # física sin inventar un kilometraje que nunca se captura.
        'archivo': 'BITACORA_CAMION_BASURA.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 22,
        'columnas': {'fecha': 1, 'destino': 2, 'comision': 3, 'km_inicial': 4,
                     'km_final': 5, 'litros': 6, 'folio': 7, 'responsable': 8},
        'col_litros': 6,
    },
    TipoBitacoraEnum.UREA.value: {
        'archivo': 'BITACORA_UREA.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 24,
        'columnas': {'fecha': 1, 'motivo_uso': 2, 'vehiculo': 3, 'color': 4,
                     'modelo': 5, 'placa': 6, 'litros': 7, 'responsable': 8},
        'col_litros': 7,
    },
    TipoBitacoraEnum.LUBRICANTE.value: {
        'archivo': 'BITACORA_LUBRICANTE.xlsx',
        'fila_inicio_datos': 9, 'fila_total': 24,
        'columnas': {'fecha': 1, 'motivo_uso': 2, 'vehiculo': 3, 'color': 4,
                     'modelo': 5, 'placa': 6, 'litros': 7, 'responsable': 8},
        'col_litros': 7,
    },
}


def _datos_vehiculo_asignacion(a):
    """
    Resuelve de forma uniforme los datos físicos del vehículo/equipo de
    una Asignación de Combustible (nombre, color, modelo, placa),
    manejando tanto el catálogo de Unidad (KM) como el de Equipo
    (Horómetro, usado por CAMION_BASURA), sin lanzar excepciones.
    """
    vehiculo_nombre, color, modelo, placa = '', '', '', ''
    try:
        if (a.tipo_asignacion == 'CAMION_BASURA' or a.subtipo_asignacion == 'CAMION_BASURA') and a.equipo:
            vehiculo_nombre = a.equipo.nombre or ''
            placa = a.equipo.num_economico or ''
        elif a.vehiculo:
            vehiculo_nombre = f"{a.vehiculo.marca or ''} {a.vehiculo.tipo or a.vehiculo.linea or ''}".strip() or a.vehiculo.nombre
            color = a.vehiculo.color or ''
            modelo = a.vehiculo.modelo or ''
            placa = a.vehiculo.placa or ''
    except Exception:
        pass
    return vehiculo_nombre, color, modelo, placa


def _valor_campo_asignacion(a, campo):
    """
    Devuelve el valor a escribir en la celda de Excel para el campo
    lógico solicitado, resolviendo de forma segura cualquier dato
    faltante (nunca lanza excepción; cae a cadena vacía).
    """
    try:
        vehiculo_nombre, color, modelo, placa = _datos_vehiculo_asignacion(a)
        if campo in ('vehiculo', 'vehiculo_caract', 'tipo_marca'):
            return vehiculo_nombre
        if campo == 'fecha':
            return a.fecha_inicio.strftime('%d/%m/%Y') if a.fecha_inicio else ''
        if campo == 'destino':
            return a.itinerario_destino or ''
        if campo == 'comision':
            return a.tipo_recorrido or a.actividades or ''
        if campo == 'color':
            return color
        if campo == 'modelo':
            return modelo
        if campo == 'placa':
            return placa
        if campo == 'km_inicial':
            # CAMIÓN DE BASURA: su plantilla oficial reutiliza las columnas
            # "KM INICIAL/FINAL" del formato físico, pero la medición real
            # es EXCLUSIVAMENTE por Horómetro; se refleja el horómetro
            # real en esas columnas para no inventar kilometraje.
            if a.tipo_asignacion == 'CAMION_BASURA':
                return a.horometro_inicial if a.horometro_inicial is not None else ''
            return a.km_inicial if a.km_inicial is not None else ''
        if campo == 'km_final':
            if a.tipo_asignacion == 'CAMION_BASURA':
                return a.horometro_final if a.horometro_final is not None else ''
            return a.km_final if a.km_final is not None else ''
        if campo == 'horas':
            horas = a.horas_trabajo()
            return horas if horas is not None else ''
        if campo == 'litros':
            return float(a.litros_asignados or 0)
        if campo == 'folio':
            return a.folio_asignacion or ''
        if campo == 'responsable':
            return a.responsable_nombre or ''
        if campo == 'comunidad':
            return a.itinerario_destino or ''
        if campo == 'motivo_uso':
            return a.itinerario_destino or a.actividades or ''
    except Exception:
        return ''
    return ''


@main.route('/exportar_excel_combustible', methods=['GET'])
@login_required
@servicios_publicos_required
def exportar_excel_combustible():
    """
    ORDEN TÉCNICA MAESTRA - 11 PLANTILLAS OFICIALES EXACTAS:
    Carga OBLIGATORIAMENTE la plantilla oficial correspondiente al tipo
    de bitácora solicitado (ver CONFIG_PLANTILLAS_BITACORA) e inyecta
    los registros reales del Formulario N° 10 a partir de la fila 9 de
    esa plantilla específica, manteniendo intactos sus encabezados,
    logotipo y formato institucional del Municipio de Atarjea, Gto.
    (Administración 2024-2027). Nunca se mezclan datos entre plantillas
    ni se usa una plantilla genérica para un tipo distinto.
    """
    try:
        nombre_archivo_personalizado = request.args.get('nombre_archivo', '').strip()
        tipo_filtro = request.args.get('tipo_bitacora', '').strip().upper()

        if not tipo_filtro or tipo_filtro not in CONFIG_PLANTILLAS_BITACORA:
            flash('Seleccione una bitácora válida para exportar su plantilla oficial.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        config_plantilla = CONFIG_PLANTILLAS_BITACORA[tipo_filtro]

        query_asig = AsignacionCombustible.query.order_by(AsignacionCombustible.fecha_creacion.asc())
        query_asig = query_asig.filter_by(tipo_asignacion=tipo_filtro)
        asignaciones_todas = query_asig.all()

        if not asignaciones_todas:
            flash(f'No hay asignaciones registradas en "{TipoBitacoraEnum.nombre_completo(tipo_filtro)}" para exportar.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        ruta_plantilla = os.path.join(obtener_ruta_base_app(), config_plantilla['archivo'])
        if not os.path.exists(ruta_plantilla):
            flash(f'No se encontró la plantilla oficial "{config_plantilla["archivo"]}" en el proyecto.', 'danger')
            return redirect(url_for('main.servicios_publicos'))

        wb = load_workbook(ruta_plantilla)
        ws = wb.active

        FILA_INICIO_DATOS = config_plantilla['fila_inicio_datos']
        FILA_TOTAL_ORIGINAL = config_plantilla['fila_total']
        FILA_ESTILO_REFERENCIA = FILA_INICIO_DATOS
        COL_LITROS = config_plantilla['col_litros']
        mapa_columnas = config_plantilla['columnas']

        total_filas_necesarias = len(asignaciones_todas)
        filas_disponibles_originales = (FILA_TOTAL_ORIGINAL - 1) - FILA_INICIO_DATOS + 1

        # Si hay más registros que filas disponibles en la plantilla
        # original, se insertan filas adicionales ANTES de la fila
        # "TOTAL DE LITROS" para no perder ningún registro, replicando
        # el estilo oficial de la fila de referencia de ESA plantilla.
        if total_filas_necesarias > filas_disponibles_originales:
            filas_a_insertar = total_filas_necesarias - filas_disponibles_originales
            ws.insert_rows(FILA_TOTAL_ORIGINAL, amount=filas_a_insertar)
            for nueva_fila in range(FILA_TOTAL_ORIGINAL, FILA_TOTAL_ORIGINAL + filas_a_insertar):
                for col in range(1, ws.max_column + 1):
                    _copiar_estilo_celda(ws.cell(row=FILA_ESTILO_REFERENCIA, column=col), ws.cell(row=nueva_fila, column=col))

        fila_total_litros = FILA_INICIO_DATOS + max(total_filas_necesarias, filas_disponibles_originales)

        fila_actual = FILA_INICIO_DATOS
        for a in asignaciones_todas:
            for campo, columna in mapa_columnas.items():
                valor = _valor_campo_asignacion(a, campo)
                ws.cell(row=fila_actual, column=columna, value=valor)
            fila_actual += 1

        # Fórmula de suma de litros sobre el rango real de datos, en la
        # columna de litros EXACTA de esta plantilla (nunca una columna
        # fija genérica, ya que cada plantilla tiene disposición propia).
        fila_fin_datos = fila_actual - 1
        letra_col_litros = ws.cell(row=FILA_INICIO_DATOS, column=COL_LITROS).column_letter
        ws.cell(row=fila_total_litros, column=COL_LITROS,
                value=f"=SUM({letra_col_litros}{FILA_INICIO_DATOS}:{letra_col_litros}{fila_fin_datos})")

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        # Trazabilidad total
        nombre_bitacora_completo = TipoBitacoraEnum.nombre_completo(tipo_filtro)
        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Exportación de Bitácora Oficial de Combustible a Excel",
            tabla_afectada='asignaciones_combustible',
            registro_id='N/A',
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} exportó {len(asignaciones_todas)} asignación(es) de '{nombre_bitacora_completo}' a su plantilla oficial de Excel."
        )
        db.session.add(auditoria)
        db.session.commit()

        if nombre_archivo_personalizado:
            nombre_base = secure_filename(nombre_archivo_personalizado)
            if not nombre_base.lower().endswith('.xlsx'):
                nombre_base += '.xlsx'
        else:
            nombre_tipo_archivo = os.path.splitext(config_plantilla['archivo'])[0]
            nombre_base = f"{nombre_tipo_archivo}_Atarjea_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return send_file(
            output,
            as_attachment=True,
            download_name=nombre_base,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        # CERO CAÍDAS (ORDEN TÉCNICA MAESTRA): la plantilla oficial de
        # Excel nunca debe provocar un error 500. Ante cualquier folio
        # con datos faltantes/corruptos, o un problema al cargar la
        # plantilla, se informa con claridad al operador y se registra
        # el detalle técnico completo en el log para diagnóstico.
        db.session.rollback()
        current_app.logger.error(f"Error al exportar Excel de combustible: {str(e)}", exc_info=True)
        flash('No se pudo generar el reporte en Excel. Verifique los datos del folio e intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))



# ============================================
# MÓDULO FINANCIERO DE COMBUSTIBLE
# "Cuentas y Balance Financiero": visible solo para Admin/Alcaldía.
# ============================================

@main.route('/servicios_publicos/actualizar_costo_litro', methods=['POST'])
@login_required
@finanzas_combustible_required
def actualizar_costo_litro_combustible():
    """Actualiza el costo unitario vigente por litro de combustible."""
    try:
        nuevo_costo = request.form.get('costo_litro', '').strip()
        try:
            nuevo_costo = float(nuevo_costo)
        except (ValueError, TypeError):
            flash('El costo por litro debe ser un valor numérico válido.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        if nuevo_costo <= 0:
            flash('El costo por litro debe ser mayor a cero.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        configuracion = ConfiguracionCombustible(
            costo_litro=round(nuevo_costo, 2),
            fecha_actualizacion=datetime.utcnow(),
            actualizado_por_id=current_user.id
        )
        db.session.add(configuracion)
        db.session.flush()

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Actualización de costo unitario de combustible",
            tabla_afectada='configuracion_combustible',
            registro_id=str(configuracion.id),
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} actualizó el costo por litro a ${nuevo_costo:.2f} MXN."
        )
        db.session.add(auditoria)
        db.session.commit()

        flash(f'Costo por litro actualizado a ${nuevo_costo:.2f} MXN.', 'success')
        return redirect(url_for('main.servicios_publicos'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al actualizar costo de combustible: {str(e)}")
        flash('Ocurrió un error al actualizar el costo del combustible.', 'danger')
        return redirect(url_for('main.servicios_publicos'))




# ============================================
# ORDEN DE COMISIÓN Y SOLICITUD DE COMBUSTIBLE (PDF)
# Formato rápido para imprimir, con folio compartido entre el oficio
# firmado (Orden de Comisión) y el vale de despacho de combustible,
# manteniendo la trazabilidad entre ambos documentos físicos.
# ============================================

@main.route('/servicios_publicos/orden_comision/<int:registro_id>', methods=['GET'])
@login_required
@servicios_publicos_required
def generar_orden_comision(registro_id):
    """Genera el PDF de 'Orden de Comisión y Solicitud de Combustible' para un registro existente."""
    try:
        registro = BitacoraCombustible.query.get_or_404(registro_id)
        return _generar_pdf_orden_comision(registro)
    except Exception as e:
        current_app.logger.error(f"Error al generar Orden de Comisión: {str(e)}")
        flash('Ocurrió un error al generar la Orden de Comisión en PDF.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/orden_comision_rapida', methods=['POST'])
@login_required
@servicios_publicos_required
def generar_orden_comision_rapida():
    """
    Genera una Orden de Comisión en PDF a partir de datos del formulario
    SIN necesidad de haber guardado aún el despacho, comparte el mismo
    folio de vale capturado por el operador para vincular ambos documentos.
    """
    try:
        folio_vale = request.form.get('folio_vale', '').strip() or f"S/F-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        registro_temporal = BitacoraCombustible(
            tipo_bitacora=request.form.get('tipo_bitacora', 'OFICIAL').strip().upper(),
            folio_vale=folio_vale,
            destino_comision=request.form.get('destino_comision', '').strip() or None,
            vehiculo_nombre=request.form.get('vehiculo_nombre', '').strip() or None,
            placa=request.form.get('placa', '').strip() or None,
            comunidad=request.form.get('comunidad', '').strip() or None,
            responsable_nombre=request.form.get('responsable_nombre', '').strip() or 'No especificado',
            litros=float(request.form.get('litros') or 0),
            fecha=datetime.utcnow()
        )
        return _generar_pdf_orden_comision(registro_temporal)
    except Exception as e:
        current_app.logger.error(f"Error al generar Orden de Comisión rápida: {str(e)}")
        flash('Ocurrió un error al generar la Orden de Comisión en PDF.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


def _generar_pdf_orden_comision(registro):
    """Construye el documento PDF de Orden de Comisión y Solicitud de Combustible.
    ORDEN TÉCNICA MAESTRA: impreso en tamaño Oficio (216 x 340 mm)."""
    output = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=OFICIO_PAGESIZE, topMargin=40, bottomMargin=40)
    elementos = []

    titulo_style = ParagraphStyle('TituloOrden', parent=styles['Heading1'], fontSize=15,
                                   textColor=colors.HexColor('#1a237e'), alignment=1, spaceAfter=6)
    subtitulo_style = ParagraphStyle('SubtituloOrden', parent=styles['Heading2'], fontSize=11,
                                      textColor=colors.HexColor('#2c3e50'), alignment=1, spaceAfter=14)
    normal_style = styles['Normal']

    elementos.append(Paragraph("MUNICIPIO DE ATARJEA, GUANAJUATO", titulo_style))
    elementos.append(Paragraph("Dirección de Servicios Públicos Municipales", subtitulo_style))
    elementos.append(Paragraph("ORDEN DE COMISIÓN Y SOLICITUD DE COMBUSTIBLE", subtitulo_style))

    datos = [
        ['Folio (Vale/Oficio):', registro.folio_vale, 'Fecha:', registro.fecha.strftime('%d/%m/%Y') if registro.fecha else ''],
        ['Bitácora:', registro.tipo_bitacora, 'Comunidad/Destino:', registro.comunidad or registro.destino_comision or '-'],
        ['Vehículo/Maquinaria:', registro.vehiculo_nombre or '-', 'Placa:', registro.placa or '-'],
        ['Responsable/Operador:', registro.responsable_nombre, 'Litros Solicitados:', f"{registro.litros or 0:.2f} L"],
    ]
    tabla = Table(datos, colWidths=[130, 170, 110, 110])
    tabla.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabla)
    elementos.append(Paragraph("<br/>", normal_style))
    elementos.append(Paragraph(
        "Por medio del presente se autoriza la comisión descrita y se solicita el suministro de combustible "
        "detallado, conforme a las necesidades operativas de la Dirección de Servicios Públicos Municipales.",
        normal_style
    ))
    elementos.append(Paragraph("<br/><br/><br/>", normal_style))

    firmas = [
        ['_________________________', '_________________________'],
        ['Firma del Responsable', 'Firma de Autorización (Encargada/Alcaldía)'],
    ]
    tabla_firmas = Table(firmas, colWidths=[260, 260])
    tabla_firmas.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    elementos.append(tabla_firmas)

    doc.build(elementos)
    output.seek(0)

    nombre_archivo = f"Orden_Comision_{registro.folio_vale}.pdf"
    return send_file(output, as_attachment=False, download_name=nombre_archivo, mimetype='application/pdf')


@main.route('/servicios_publicos/cancelar/<int:registro_id>', methods=['POST'])
@login_required
@servicios_publicos_required
def cancelar_bitacora_combustible(registro_id):
    """
    INMUTABILIDAD: los registros ACTIVOS nunca se editan ni se borran.
    Esta ruta únicamente permite 'Cancelar' un registro con un motivo
    obligatorio; si el dato estaba mal, debe capturarse un NUEVO registro.
    """
    try:
        registro = BitacoraCombustible.query.get_or_404(registro_id)
        motivo_cancelacion = request.form.get('motivo_cancelacion', '').strip()

        if not motivo_cancelacion:
            flash('Debe indicar el motivo de la cancelación.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        if registro.estatus == 'CANCELADO':
            flash('Este registro ya se encontraba cancelado.', 'info')
            return redirect(url_for('main.servicios_publicos'))

        registro.cancelar(motivo_cancelacion, usuario_id=current_user.id)

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Cancelación de bitácora de combustible",
            tabla_afectada='bitacoras_combustible',
            registro_id=str(registro.id),
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} canceló el folio {registro.folio_vale}. Motivo: {motivo_cancelacion}"
        )
        db.session.add(auditoria)
        db.session.commit()

        flash(f'Registro (Folio {registro.folio_vale}) cancelado correctamente.', 'success')
        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al cancelar bitácora de combustible: {str(e)}")
        flash('Ocurrió un error al cancelar el registro.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/abasto/registrar', methods=['POST'])
@login_required
@servicios_publicos_required
def registrar_abasto():
    """Registra una ENTRADA de combustible al contenedor municipal (abasto)."""
    try:
        litros_recibidos = request.form.get('litros_recibidos', '').strip()
        try:
            litros_recibidos = float(litros_recibidos)
        except (ValueError, TypeError):
            flash('Los litros recibidos deben ser un número válido.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        def _num(valor):
            try:
                return float(valor) if valor not in (None, '') else None
            except (ValueError, TypeError):
                return None

        fecha_abasto_str = request.form.get('fecha_abasto', '').strip()
        try:
            fecha_abasto = datetime.strptime(fecha_abasto_str, '%Y-%m-%d') if fecha_abasto_str else datetime.utcnow()
        except ValueError:
            fecha_abasto = datetime.utcnow()

        precio_por_litro = _num(request.form.get('precio_por_litro'))
        monto_total = _num(request.form.get('monto_total'))
        if monto_total is None and precio_por_litro is not None:
            # El monto total se calcula automáticamente si no se captura
            monto_total = round(precio_por_litro * litros_recibidos, 2)

        nuevo_abasto = RegistroAbasto(
            fecha=fecha_abasto,
            proveedor=request.form.get('proveedor', '').strip() or None,
            municipio_origen=request.form.get('municipio_origen', '').strip() or None,
            litros_recibidos=litros_recibidos,
            precio_por_litro=precio_por_litro,
            monto_total=monto_total,
            documento=request.form.get('documento', '').strip().upper() or None,
            numero=request.form.get('numero', '').strip() or None,
            recibe=request.form.get('recibe', '').strip() or None,
            usuario_id=current_user.id,
            es_demo=False
        )

        if 'foto_documento' in request.files:
            ruta = _guardar_archivo_combustible(request.files['foto_documento'], 'abasto_doc')
            if ruta:
                nuevo_abasto.foto_documento = ruta
        if 'foto_nivel_contenedor' in request.files:
            ruta = _guardar_archivo_combustible(request.files['foto_nivel_contenedor'], 'abasto_nivel')
            if ruta:
                nuevo_abasto.foto_nivel_contenedor = ruta

        db.session.add(nuevo_abasto)
        db.session.flush()

        BitacoraSistemaLog.registrar(
            accion='CREAR_ABASTO_COMBUSTIBLE',
            registro_id=nuevo_abasto.id,
            usuario_id=current_user.id,
            detalle=f"{current_user.nombre} registró entrada de {litros_recibidos} L al contenedor."
        )
        db.session.commit()

        flash(f'Entrada de {litros_recibidos:.1f} L registrada exitosamente.', 'success')
        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al registrar abasto de combustible: {str(e)}")
        flash('Ocurrió un error al registrar la entrada de combustible.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/abasto_fluido/registrar', methods=['POST'])
@login_required
@servicios_publicos_required
def registrar_abasto_fluido():
    """
    ORDEN TÉCNICA MAESTRA - ARQUITECTURA MULTITANQUE: registra una
    ENTRADA de combustible (Gasolina, Diésel o Urea) a un tanque
    específico (1 o 2). CERO CAÍDAS: cualquier error se captura,
    revierte la transacción y se informa al operador sin colapsar.
    """
    try:
        def _num(valor):
            try:
                return float(valor) if valor not in (None, '') else None
            except (ValueError, TypeError):
                return None

        tipo_fluido = request.form.get('tipo_fluido', '').strip().upper()
        if tipo_fluido not in [t.value for t in TipoFluidoEnum]:
            flash('Seleccione un fluido válido (Gasolina, Diésel o Urea).', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        numero_tanque = request.form.get('numero_tanque', '1').strip()
        numero_tanque = int(numero_tanque) if numero_tanque in ('1', '2') else 1

        litros_recibidos = _num(request.form.get('litros_recibidos')) or 0.0
        if litros_recibidos <= 0:
            flash('Indique una cantidad de litros válida para registrar el abasto.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        costo_litro = _num(request.form.get('costo_litro'))
        fecha_abasto_str = request.form.get('fecha_abasto', '').strip()
        try:
            fecha_abasto = datetime.strptime(fecha_abasto_str, '%Y-%m-%d') if fecha_abasto_str else datetime.utcnow()
        except ValueError:
            fecha_abasto = datetime.utcnow()

        nuevo_abasto = RegistroAbastoFluido(
            tipo_fluido=tipo_fluido,
            numero_tanque=numero_tanque,
            fecha=fecha_abasto,
            litros_recibidos=litros_recibidos,
            costo_litro=costo_litro,
            proveedor=request.form.get('proveedor', '').strip() or None,
            documento=request.form.get('documento', '').strip().upper() or None,
            numero_documento=request.form.get('numero_documento', '').strip() or None,
            recibe=request.form.get('recibe', '').strip() or None,
            usuario_id=current_user.id,
            es_demo=False
        )
        nuevo_abasto.calcular_costo_total()

        # Activa automáticamente el Tanque 2 de respaldo del fluido en
        # cuanto recibe su primera entrada registrada (doble barra
        # simultánea visible de inmediato en el Dashboard).
        if numero_tanque == 2:
            config_t2 = ConfiguracionTanque.obtener_o_crear(
                tipo_fluido, 2, capacidad_default=CAPACIDAD_TANQUE_DEFAULT.get(tipo_fluido, 1000.0)
            )
            config_t2.activo = True

        db.session.add(nuevo_abasto)
        db.session.commit()

        BitacoraSistemaLog.registrar(
            accion='CREAR_ABASTO_FLUIDO',
            registro_id=nuevo_abasto.id,
            usuario_id=current_user.id,
            detalle=f"{current_user.nombre} registró entrada de {litros_recibidos} L de {TipoFluidoEnum.nombre_completo(tipo_fluido)} (Tanque {numero_tanque})."
        )
        db.session.commit()

        flash(f'Entrada de {litros_recibidos:.1f} L de {TipoFluidoEnum.nombre_completo(tipo_fluido)} (Tanque {numero_tanque}) registrada exitosamente.', 'success')
        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al registrar abasto de fluido: {str(e)}", exc_info=True)
        flash('No se pudo registrar la entrada de combustible. Verifique los datos e intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/tanque/activar', methods=['POST'])
@login_required
@servicios_publicos_required
def activar_tanque_respaldo():
    """
    ORDEN TÉCNICA MAESTRA - DOBLE TANQUE SIMULTÁNEO: activa/desactiva
    manualmente el Tanque 2 (Secundario/Provisional) de un fluido (ej.
    cuando el Tanque 1 Principal llega a nivel crítico). CERO CAÍDAS.

    COHERENCIA CON EL TANQUE SECUENCIAL AUTOMÁTICO: si el Tanque 2 se
    desactiva justo cuando ya había sido promovido a Principal (porque
    el Tanque 1 se agotó), el Tanque 1 recupera el rol de Principal para
    que el fluido nunca quede sin ningún tanque marcado como Principal.
    """
    try:
        tipo_fluido = request.form.get('tipo_fluido', '').strip().upper()
        if tipo_fluido not in [t.value for t in TipoFluidoEnum]:
            flash('Fluido no reconocido.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        config_t2 = ConfiguracionTanque.obtener_o_crear(
            tipo_fluido, 2, capacidad_default=CAPACIDAD_TANQUE_DEFAULT.get(tipo_fluido, 1000.0)
        )
        config_t2.activo = not bool(config_t2.activo)

        if not config_t2.activo and config_t2.es_principal:
            config_t2.es_principal = False
            config_t1 = ConfiguracionTanque.obtener_o_crear(
                tipo_fluido, 1, capacidad_default=CAPACIDAD_TANQUE_DEFAULT.get(tipo_fluido, 1000.0)
            )
            config_t1.es_principal = True
            config_t1.activo = True

        db.session.commit()

        estado_txt = 'activado' if config_t2.activo else 'desactivado'
        flash(f'Tanque 2 (Secundario/Provisional) de {TipoFluidoEnum.nombre_completo(tipo_fluido)} {estado_txt} correctamente.', 'success')
        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al activar/desactivar tanque de respaldo: {str(e)}", exc_info=True)
        flash('No se pudo actualizar el estado del tanque de respaldo.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/reporte_semanal', methods=['GET'])
@login_required
@servicios_publicos_required
def reporte_semanal_consolidado():
    """
    ORDEN TÉCNICA MAESTRA - MÓDULO DE REPORTE SEMANAL CONSOLIDADO:
    vista dedicada que muestra, de forma ampliada, el corte de los
    últimos 7 días unificando las 11 bitácoras oficiales. CERO CAÍDAS.
    """
    try:
        reporte = calcular_reporte_semanal_consolidado()
        return render_template('reporte_semanal.html', reporte=reporte)
    except Exception as e:
        current_app.logger.error(f"Error al generar el Reporte Semanal Consolidado: {str(e)}", exc_info=True)
        flash('No se pudo generar el Reporte Semanal Consolidado. Intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


@main.route('/servicios_publicos/borrar_datos_demo', methods=['POST'])
@login_required
@admin_required
def borrar_datos_demo_combustible():
    """Elimina permanentemente todos los registros marcados es_demo=True
    del Módulo de Combustible (bitácoras y abastos). Solo Administrador."""
    try:
        bitacoras_demo = BitacoraCombustible.query.filter_by(es_demo=True).all()
        abastos_demo = RegistroAbasto.query.filter_by(es_demo=True).all()

        cantidad_bitacoras = len(bitacoras_demo)
        cantidad_abastos = len(abastos_demo)

        for b in bitacoras_demo:
            db.session.delete(b)
        for a in abastos_demo:
            db.session.delete(a)

        BitacoraSistemaLog.registrar(
            accion='BORRAR_DATOS_DEMO_COMBUSTIBLE',
            registro_id=None,
            usuario_id=current_user.id,
            detalle=f"{current_user.nombre} eliminó {cantidad_bitacoras} bitácora(s) y {cantidad_abastos} abasto(s) demo."
        )
        db.session.commit()

        flash(f'Se eliminaron {cantidad_bitacoras} registro(s) de bitácora y {cantidad_abastos} de abasto marcados como DEMO.', 'success')
        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al borrar datos demo de combustible: {str(e)}")
        flash('Ocurrió un error al borrar los datos demo.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


# ============================================
# FORMULARIO N° 10 - ASIGNACIÓN DE COMBUSTIBLE
# Separa el ciclo de vida del vale (EMITIDA -> ENTREGADA -> COMPROBADA)
# del despacho físico real. "Cada litro se registra, se vigila y se
# comprueba". Ninguna validación de este módulo bloquea el guardado ni
# el avance de estatus; solo genera alertas visuales pasivas.
# ============================================

@main.route('/servicios_publicos/asignacion/crear', methods=['POST'])
@login_required
@servicios_publicos_required
def crear_asignacion_combustible():
    """Crea una nueva Asignación de Combustible (Formulario N° 10) con folio consecutivo automático."""
    try:
        def _to_float(valor):
            try:
                return float(valor) if valor not in (None, '') else None
            except (ValueError, TypeError):
                return None

        unidad_organizacional = request.form.get('unidad_organizacional', '').strip() or None
        tipo_asignacion = request.form.get('tipo_asignacion', 'OFICIAL').strip().upper()
        itinerario_destino = request.form.get('itinerario_destino', '').strip() or None
        responsable_nombre = request.form.get('responsable_nombre', '').strip() or 'No especificado'
        responsable_celular = request.form.get('responsable_celular', '').strip() or None
        litros_asignados = _to_float(request.form.get('litros_asignados')) or 0.0
        tipo_combustible = request.form.get('tipo_combustible', '').strip() or None
        km_inicial = _to_float(request.form.get('km_inicial'))
        km_final = _to_float(request.form.get('km_final'))

        # FORMATO OFICIAL DEL FORMULARIO N° 10 (rediseño)
        tipo_recorrido = request.form.get('tipo_recorrido', '').strip() or None
        actividades = request.form.get('actividades', '').strip() or None
        director_area = request.form.get('director_area', '').strip() or None

        # CAMPO OBLIGATORIO DE AUTORIZACIÓN (CERO BLOQUEOS: se recomienda
        # capturarlo, pero un vale nunca se rechaza por faltar este dato).
        quien_autoriza = request.form.get('quien_autoriza', '').strip() or None

        # SUBTIPO (MAQUINARIA: CAMION_BASURA, CIUDADANO: TRASLADO|
        # VALE_GASOLINA|VIAJES_AGUA) y horómetro obligatorio para camiones
        # de basura (nunca bloquea: si no aplica, simplemente queda vacío).
        subtipo_asignacion = request.form.get('subtipo_asignacion', '').strip().upper() or None
        horometro_inicial = _to_float(request.form.get('horometro_inicial'))
        horometro_final = _to_float(request.form.get('horometro_final'))

        # DESTINO DEL APOYO DE AGUA (submenú obligatorio cuando el TIPO
        # de bitácora es PIPA/"Camión Pipas": Vivienda Particular,
        # Institución Educativa, Institución de Salud o Apoyo Comunitario).
        # Nunca bloquea el guardado si no aplica o no se especifica.
        destino_apoyo_agua = request.form.get('destino_apoyo_agua', '').strip().upper() or None

        fecha_solicitud_str = request.form.get('fecha_solicitud', '').strip()
        try:
            fecha_solicitud = datetime.strptime(fecha_solicitud_str, '%Y-%m-%d') if fecha_solicitud_str else datetime.utcnow()
        except ValueError:
            fecha_solicitud = datetime.utcnow()

        # FECHAS CON FORMATO NATIVO HTML (<input type="date">, YYYY-MM-DD)
        # para que el navegador nunca rechace una fecha válida: la fecha
        # de comisión se captura por separado de la hora (HH:MM) y se
        # combinan aquí. Se mantiene tolerancia al formato anterior
        # (datetime-local) por si algún cliente viejo aún lo envía.
        fecha_inicio_str = request.form.get('fecha_inicio', '').strip()
        hora_inicio_str = request.form.get('hora_inicio', '').strip() or '08:00'
        fecha_fin_str = request.form.get('fecha_fin', '').strip()
        try:
            if fecha_inicio_str and 'T' in fecha_inicio_str:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%dT%H:%M')
            elif fecha_inicio_str:
                fecha_inicio = datetime.strptime(f"{fecha_inicio_str} {hora_inicio_str}", '%Y-%m-%d %H:%M')
            else:
                fecha_inicio = datetime.utcnow()
        except ValueError:
            fecha_inicio = datetime.utcnow()
        try:
            if fecha_fin_str and 'T' in fecha_fin_str:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%dT%H:%M')
            elif fecha_fin_str:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
            else:
                fecha_fin = None
        except ValueError:
            fecha_fin = None

        # CAPTURA MANUAL DE CHOFERES (ORDEN TÉCNICA MAESTRA, punto 4): el
        # campo ahora es de texto libre (teclado), ya no un <select> del
        # catálogo. Si el nombre capturado no existe todavía en el
        # catálogo de conductores, se da de alta automáticamente para
        # preservar la trazabilidad (nunca bloquea el guardado del vale).
        chofer_nombre = request.form.get('chofer_nombre', '').strip() or None
        chofer_id = None
        if chofer_nombre:
            try:
                chofer_obj = Conductor.query.filter(func.lower(Conductor.nombre) == chofer_nombre.lower()).first()
                if not chofer_obj:
                    chofer_obj = Conductor(nombre=chofer_nombre, activo=True)
                    db.session.add(chofer_obj)
                    db.session.flush()
                chofer_id = chofer_obj.id
            except Exception as e:
                current_app.logger.warning(f"No se pudo registrar/vincular al chofer '{chofer_nombre}': {str(e)}")
                chofer_id = None

        # El vehículo puede llegar por ID del catálogo real (select nuevo
        # del Formulario N° 10 rediseñado) o, por compatibilidad, por
        # nombre exacto (formularios anteriores).
        vehiculo_id_form = request.form.get('vehiculo_id', '').strip()
        vehiculo_nombre = request.form.get('vehiculo_nombre', '').strip() or None
        vehiculo_id = None
        vehiculo_obj = None
        if vehiculo_id_form.isdigit():
            vehiculo_obj = Unidad.query.get(int(vehiculo_id_form))
        elif vehiculo_nombre:
            vehiculo_obj = Unidad.query.filter(func.lower(Unidad.nombre) == vehiculo_nombre.lower()).first()
        if vehiculo_obj:
            vehiculo_id = vehiculo_obj.id
            if not tipo_combustible:
                tipo_combustible = vehiculo_obj.tipo_combustible
            if km_inicial is None:
                km_inicial = vehiculo_obj.ultimo_km

        # MÉTRICA ESTRICTA (HORAS): el camión de basura se selecciona del
        # catálogo de Equipo (medición por horómetro), NUNCA del catálogo
        # de Unidad (KM). equipo_id y vehiculo_id son mutuamente excluyentes
        # en la práctica según el subtipo, pero nunca se bloquea el guardado.
        equipo_id_form = request.form.get('equipo_id', '').strip()
        equipo_id = None
        equipo_obj = None
        if equipo_id_form.isdigit():
            equipo_obj = Equipo.query.get(int(equipo_id_form))
        if equipo_obj:
            equipo_id = equipo_obj.id
            tipo_combustible_equipo = request.form.get('tipo_combustible_equipo', '').strip() or None
            if tipo_asignacion == 'CAMION_BASURA' or subtipo_asignacion == 'CAMION_BASURA':
                tipo_combustible = tipo_combustible_equipo or equipo_obj.tipo_combustible

        # CAPTURA POR HORAS EN EQUIPO MENOR (ORDEN TÉCNICA MAESTRA, punto 4):
        # la bitácora de Equipo Menor (herramienta motorizada) NUNCA se mide
        # por kilometraje; se captura EXCLUSIVAMENTE "Horas de Uso /
        # Operación". Se reutiliza el par horometro_inicial/horometro_final
        # (horometro_inicial=0.0) para aprovechar horas_trabajo() ya
        # existente en el modelo, sin duplicar lógica ni columnas nuevas.
        # Nunca bloquea el guardado si el dato llega vacío.
        horas_uso_equipo_menor = _to_float(request.form.get('horas_uso_equipo_menor'))
        if tipo_asignacion == 'EQUIPO_MENOR':
            km_inicial = None
            km_final = None
            if horas_uso_equipo_menor is not None:
                horometro_inicial = 0.0
                horometro_final = horas_uso_equipo_menor

        folio_asignacion = generar_folio_asignacion()

        nueva_asignacion = AsignacionCombustible(
            folio_asignacion=folio_asignacion,
            unidad_organizacional=unidad_organizacional,
            tipo_asignacion=tipo_asignacion,
            itinerario_destino=itinerario_destino,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            fecha_solicitud=fecha_solicitud,
            tipo_recorrido=tipo_recorrido,
            actividades=actividades,
            director_area=director_area,
            quien_autoriza=quien_autoriza,
            subtipo_asignacion=subtipo_asignacion,
            horometro_inicial=horometro_inicial,
            horometro_final=horometro_final,
            destino_apoyo_agua=destino_apoyo_agua,
            responsable_nombre=responsable_nombre,
            responsable_celular=responsable_celular,
            chofer_id=chofer_id,
            vehiculo_id=vehiculo_id,
            equipo_id=equipo_id,
            litros_asignados=litros_asignados,
            tipo_combustible=tipo_combustible,
            estatus=EstatusAsignacionEnum.AUTORIZADO.value,
            km_inicial=km_inicial,
            km_final=km_final,
            usuario_id=current_user.id,
            es_demo=False
        )
        db.session.add(nueva_asignacion)
        db.session.flush()

        # VALIDACIÓN DE RENDIMIENTO (alerta visual pasiva, nunca bloquea)
        excede = nueva_asignacion.excede_umbral_rendimiento()

        BitacoraSistemaLog.registrar(
            accion='CREAR_ASIGNACION_COMBUSTIBLE',
            registro_id=nueva_asignacion.id,
            usuario_id=current_user.id,
            detalle=f"Folio {folio_asignacion} creado por {current_user.nombre} ({litros_asignados} L)."
        )

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Creación de Asignación de Combustible (Formulario N° 10)",
            tabla_afectada='asignaciones_combustible',
            registro_id=str(nueva_asignacion.id),
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} generó la asignación {folio_asignacion} por {litros_asignados} L."
        )
        db.session.add(auditoria)
        db.session.commit()

        # MÓDULO PORTABLE: respaldo automático en el Escritorio tras
        # autorizar un vale/asignación de combustible (CERO BLOQUEOS).
        respaldar_en_escritorio(motivo=f"Asignación de combustible {folio_asignacion}", usuario_nombre=current_user.nombre)

        # ORDEN TÉCNICA MAESTRA - DESCUENTO AUTOMÁTICO DE LITROS: en cuanto
        # se autoriza/guarda el vale, el inventario del tanque del fluido
        # correspondiente (Gasolina/Diésel/Urea) queda descontado de
        # inmediato (calcular_estado_multitanque() recalcula en vivo sobre
        # TODAS las asignaciones activas, incluida esta recién creada), por
        # lo que el Dashboard muestra las barras y litros ya actualizados
        # sin necesidad de refrescar manualmente. Se informa aquí el saldo
        # resultante del tanque afectado para visibilidad inmediata.
        aviso_tanque = ''
        try:
            fluido_afectado = _resolver_tipo_fluido_asignacion(nueva_asignacion)
            if fluido_afectado:
                estado_tanques = calcular_estado_multitanque()
                datos_fluido = estado_tanques.get(fluido_afectado)
                if datos_fluido and datos_fluido.get('tanques'):
                    litros_restantes = sum(t['litros_disponibles'] for t in datos_fluido['tanques'] if t.get('activo'))
                    aviso_tanque = f" Tanque de {datos_fluido['nombre']} actualizado: {litros_restantes:.1f} L disponibles."
        except Exception as e:
            current_app.logger.warning(f"No se pudo calcular el saldo del tanque tras la asignación {folio_asignacion}: {str(e)}")

        if excede:
            flash(f'Asignación {folio_asignacion} creada. ALERTA: los litros asignados exceden el rendimiento teórico de la unidad.{aviso_tanque}', 'warning')
        else:
            flash(f'Asignación {folio_asignacion} creada exitosamente.{aviso_tanque}', 'success')

        return redirect(url_for('main.servicios_publicos'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al crear asignación de combustible: {str(e)}")
        flash('No se pudo crear la asignación. Verifique los datos capturados e intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))



@main.route('/servicios_publicos/asignacion/cambiar_estatus/<int:asignacion_id>', methods=['POST'])
@login_required
@servicios_publicos_required
def cambiar_estatus_asignacion(asignacion_id):
    """
    Transición de estatus del Formulario N° 10: Autorizado -> En Proceso
    -> Revisión (o Cancelada en cualquier momento, con motivo
    obligatorio). Nunca bloquea el avance.
    """
    try:
        asignacion = AsignacionCombustible.query.get_or_404(asignacion_id)
        nuevo_estatus = request.form.get('nuevo_estatus', '').strip()
        estatus_validos = [e.value for e in EstatusAsignacionEnum]

        if nuevo_estatus not in estatus_validos:
            flash('Estatus no reconocido.', 'warning')
            return redirect(url_for('main.servicios_publicos'))

        if nuevo_estatus == EstatusAsignacionEnum.CANCELADA.value:
            motivo_cancelacion = request.form.get('motivo_cancelacion', '').strip() or 'Sin motivo especificado'
            asignacion.cancelar(motivo_cancelacion, usuario_id=current_user.id)
        else:
            asignacion.avanzar_estatus(nuevo_estatus, usuario_id=current_user.id)

        auditoria = AuditoriaLog(
            user_id=current_user.id,
            accion="Cambio de estatus de Asignación de Combustible",
            tabla_afectada='asignaciones_combustible',
            registro_id=str(asignacion.id),
            ip_address=request.remote_addr,
            detalle_cambio=f"{current_user.nombre} cambió el folio {asignacion.folio_asignacion} a estatus '{nuevo_estatus}'."
        )
        db.session.add(auditoria)
        db.session.commit()

        flash(f'Folio {asignacion.folio_asignacion} actualizado a "{nuevo_estatus}".', 'success')

        return redirect(url_for('main.servicios_publicos'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al cambiar estatus de asignación: {str(e)}")
        flash('Ocurrió un error al actualizar el estatus de la asignación.', 'danger')
        return redirect(url_for('main.servicios_publicos'))



@main.route('/servicios_publicos/asignacion/pdf/<int:asignacion_id>', methods=['GET'])
@login_required
@servicios_publicos_required
def generar_pdf_asignacion(asignacion_id):
    """Genera el reporte PDF oficial del Formulario N° 10 (Asignación de
    Combustible), con espacios para firma de Director, Chofer y Fiscal
    de Combustible. ORDEN TÉCNICA MAESTRA: impreso en tamaño Oficio
    (216 x 340 mm), el formato oficial de documentos gubernamentales."""
    try:
        asignacion = AsignacionCombustible.query.get_or_404(asignacion_id)

        output = BytesIO()
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(output, pagesize=OFICIO_PAGESIZE, topMargin=40, bottomMargin=40)
        elementos = []

        titulo_style = ParagraphStyle('TituloAsig', parent=styles['Heading1'], fontSize=15,
                                       textColor=colors.HexColor('#1a237e'), alignment=1, spaceAfter=6)
        subtitulo_style = ParagraphStyle('SubtituloAsig', parent=styles['Heading2'], fontSize=11,
                                          textColor=colors.HexColor('#2c3e50'), alignment=1, spaceAfter=6)
        leyenda_style = ParagraphStyle('LeyendaAsig', parent=styles['Normal'], fontSize=9,
                                        textColor=colors.HexColor('#616161'), alignment=1, spaceAfter=14, italic=True)
        normal_style = styles['Normal']

        elementos.append(Paragraph("MUNICIPIO DE ATARJEA, GUANAJUATO", titulo_style))
        elementos.append(Paragraph("Dirección de Servicios Públicos Municipales", subtitulo_style))
        elementos.append(Paragraph("ASIGNACIÓN DE COMBUSTIBLE", subtitulo_style))
        elementos.append(Paragraph("&quot;Cada litro se registra, se vigila y se comprueba&quot;", leyenda_style))

        datos = [
            ['Folio de Asignación:', asignacion.folio_asignacion, 'Estatus:', asignacion.estatus],
            ['Fecha de Solicitud:', asignacion.fecha_solicitud.strftime('%d/%m/%Y') if asignacion.fecha_solicitud else '-',
             'Tipo de Asignación:', asignacion.tipo_recorrido or asignacion.tipo_asignacion],
            ['Unidad Organizacional:', asignacion.unidad_organizacional or '-', 'Director de Área:', asignacion.director_area or '-'],
            ['Destino:', asignacion.itinerario_destino or '-', 'Litros Entregados:', f"{asignacion.litros_asignados:.2f} L"],
            ['Fecha de Comisión:', asignacion.fecha_inicio.strftime('%d/%m/%Y %H:%M') if asignacion.fecha_inicio else '-',
             'Fecha Fin:', asignacion.fecha_fin.strftime('%d/%m/%Y %H:%M') if asignacion.fecha_fin else '-'],
            ['Responsable:', asignacion.responsable_nombre, 'Celular:', asignacion.responsable_celular or '-'],
            ['Chofer Asignado:', asignacion.chofer.nombre if asignacion.chofer else '-',
             'Vehículo Asignado:', f"{asignacion.vehiculo.nombre} - {asignacion.vehiculo.placa or 'S/P'}" if asignacion.vehiculo else '-'],
            ['Tipo de Combustible:', asignacion.tipo_combustible or '-', 'KM Inicial:', str(asignacion.km_inicial) if asignacion.km_inicial is not None else '-'],
            ['Quién Autoriza:', asignacion.quien_autoriza or '-', 'Subtipo:', asignacion.subtipo_asignacion or '-'],
            ['Destino Apoyo de Agua:', (asignacion.destino_apoyo_agua.replace('_', ' ').title() if asignacion.destino_apoyo_agua else '-'), '', ''],
            ['Actividades:', asignacion.actividades or '-', '', ''],
        ]
        tabla = Table(datos, colWidths=[120, 170, 100, 120])
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
        ]))
        elementos.append(tabla)
        elementos.append(Paragraph("<br/>", normal_style))
        elementos.append(Paragraph(
            "Por medio del presente Formulario N° 10 se autoriza la asignación de combustible "
            "descrita, conforme a las necesidades operativas de la Dirección de Servicios Públicos "
            "Municipales. El responsable se obliga a comprobar el uso del combustible asignado al "
            "concluir la comisión o itinerario correspondiente.",
            normal_style
        ))
        elementos.append(Paragraph("<br/><br/><br/>", normal_style))

        firmas = [
            ['_________________________', '_________________________', '_________________________'],
            [asignacion.quien_autoriza or 'Quien Autoriza', 'Chofer / Responsable', 'Fiscal de Combustible'],
        ]
        tabla_firmas = Table(firmas, colWidths=[175, 175, 175])
        tabla_firmas.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elementos.append(tabla_firmas)

        doc.build(elementos)
        output.seek(0)

        nombre_archivo = f"Formulario10_Asignacion_{asignacion.folio_asignacion}.pdf"
        return send_file(output, as_attachment=False, download_name=nombre_archivo, mimetype='application/pdf')

    except Exception as e:
        # CERO CAÍDAS (ORDEN TÉCNICA MAESTRA): ante cualquier dato faltante
        # o corrupto, el sistema NUNCA debe mostrar un error 500; siempre
        # regresa al panel con un mensaje claro y registra el detalle
        # técnico en el log para que el equipo de soporte pueda revisarlo.
        current_app.logger.error(f"Error al generar PDF del Formulario N° 10 (asignación #{asignacion_id}): {str(e)}", exc_info=True)
        flash('No se pudo generar el reporte PDF. Verifique los datos del folio e intente nuevamente.', 'danger')
        return redirect(url_for('main.servicios_publicos'))


