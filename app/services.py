# -*- coding: utf-8 -*-
"""
Servicios para el Sistema de Apoyos Municipales.
Incluye validaciones, verificaciones y utilidades para el manejo de datos.
"""
from datetime import datetime, timedelta
import re
from sqlalchemy import func, and_, or_
from app import db
from app.models import Ciudadano, Solicitud, Programa, Comunidad
from app.logger_config import app_logger, audit_logger

# Constantes del sistema
TIPOS_APOYO = [
    "Despensa",
    "Apoyo Económico",
    "Medicamento",
    "Material de Construcción",
    "Beca Educativa",
    "Apoyo para Vivienda"
]

DEPENDENCIAS = [
    "DIF",
    "Tesorería",
    "Desarrollo Social",
    "Presidencia",
    "Educación",
    "Obras Públicas"
]

COMUNIDADES_ATARJEA = [
    "Atarjea (Cabecera Municipal)",
    "Mangas Cuatas",
    "El Carricillo",
    "Álamos",
    "La Tapona",
    "El Charco",
    "Aldama",
    "El Toro",
    "El Banco",
    "La Joya",
    "El Chilarito",
    "San Antón"
]

# Validaciones de datos
def validar_datos(tipo_apoyo, dependencia, monto):
    """
    Valida que los datos básicos de un apoyo sean correctos.
    
    Args:
        tipo_apoyo: Tipo de apoyo solicitado
        dependencia: Dependencia que otorga el apoyo
        monto: Monto del apoyo
        
    Returns:
        tuple: (bool, str) - (éxito, mensaje)
    """
    if tipo_apoyo not in TIPOS_APOYO:
        return False, "Tipo de apoyo inválido"

    if dependencia not in DEPENDENCIAS:
        return False, "Dependencia inválida"

    try:
        monto = float(monto)
        if monto <= 0:
            return False, "Monto inválido"
    except:
        return False, "Monto debe ser numérico"

    return True, ""

def validar_curp(curp):
    """
    Valida que un CURP tenga el formato correcto.
    
    Args:
        curp: CURP a validar
        
    Returns:
        tuple: (bool, str) - (éxito, mensaje)
    """
    if not curp:
        return False, "CURP no puede estar vacío"
    
    # Convertir a mayúsculas
    curp = curp.upper()
    
    # Patrón CURP: 4 letras, 6 números (fecha), 1 letra (sexo), 2 letras (estado), 
    # 3 letras (consonantes internas), 1 número o letra (homoclave), 1 número (dígito verificador)
    patron = r'^[A-Z]{4}[0-9]{6}[HM][A-Z]{5}[0-9A-Z][0-9]$'
    
    if not re.match(patron, curp):
        return False, "Formato de CURP inválido"
    
    # Validación adicional: verificar que la fecha sea válida
    try:
        anio = int(curp[4:6])
        mes = int(curp[6:8])
        dia = int(curp[8:10])
        
        # Ajustar el año (asumiendo que 00-22 es 2000-2022, y 23-99 es 1923-1999)
        if anio < 23:
            anio += 2000
        else:
            anio += 1900
            
        # Verificar fecha válida
        datetime(anio, mes, dia)
    except ValueError:
        return False, "La fecha en el CURP no es válida"
    
    return True, ""

def validar_rfc(rfc):
    """
    Valida que un RFC tenga el formato correcto.
    
    Args:
        rfc: RFC a validar
        
    Returns:
        tuple: (bool, str) - (éxito, mensaje)
    """
    if not rfc:
        return True, ""  # RFC es opcional
    
    # Convertir a mayúsculas
    rfc = rfc.upper()
    
    # Patrón RFC persona física: 4 letras, 6 números (fecha), 3 caracteres (homoclave)
    patron_fisica = r'^[A-Z]{4}[0-9]{6}[A-Z0-9]{3}$'
    
    # Patrón RFC persona moral: 3 letras, 6 números (fecha), 3 caracteres (homoclave)
    patron_moral = r'^[A-Z]{3}[0-9]{6}[A-Z0-9]{3}$'
    
    if not (re.match(patron_fisica, rfc) or re.match(patron_moral, rfc)):
        return False, "Formato de RFC inválido"
    
    return True, ""

def verificar_duplicado_curp(curp, programa_id, dias=30):
    """
    Verifica si un ciudadano con el CURP dado ya tiene una solicitud 
    del mismo tipo de programa en los últimos días.
    
    Args:
        curp: CURP del ciudadano
        programa_id: ID del programa solicitado
        dias: Número de días hacia atrás para verificar (default: 30)
        
    Returns:
        tuple: (bool, str) - (es_duplicado, mensaje)
    """
    # Buscar al ciudadano por CURP
    ciudadano = Ciudadano.buscar_por_curp(curp)
    if not ciudadano:
        return False, ""  # No es duplicado si el ciudadano no existe
    
    # Verificar si tiene solicitudes recientes del mismo programa
    fecha_limite = datetime.utcnow() - timedelta(days=dias)
    
    solicitud_existente = Solicitud.query.filter(
        Solicitud.ciudadano_id == ciudadano.id,
        Solicitud.programa_id == programa_id,
        Solicitud.fecha_solicitud >= fecha_limite
    ).first()
    
    if solicitud_existente:
        programa = Programa.query.get(programa_id)
        return True, f"El ciudadano ya tiene una solicitud para '{programa.nombre}' en los últimos {dias} días"
    
    return False, ""

def obtener_estadisticas_dashboard():
    """
    Obtiene las estadísticas para el dashboard principal.
    
    Returns:
        dict: Diccionario con las estadísticas
    """
    # Presupuesto ejercido (solo apoyos aprobados)
    presupuesto_ejercido = db.session.query(func.sum(Solicitud.monto)).filter(
        Solicitud.status == 'Aprobado'
    ).scalar() or 0
    
    # Total de beneficiarios únicos
    total_beneficiarios = Ciudadano.query.count()
    
    # Solicitudes pendientes
    solicitudes_pendientes = Solicitud.query.filter(Solicitud.status == 'Pendiente').count()
    
    # Alertas de duplicidad
    alertas_duplicidad = Solicitud.query.filter(Solicitud.status == 'Alerta: Posible Duplicado').count()
    
    # Datos para gráfica de montos por comunidad
    datos_comunidades = db.session.query(
        Comunidad.nombre,
        func.sum(Solicitud.monto).label('total_monto')
    ).join(Ciudadano, Ciudadano.comunidad_id == Comunidad.id)\
     .join(Solicitud, Solicitud.ciudadano_id == Ciudadano.id)\
     .filter(Solicitud.status == 'Aprobado')\
     .group_by(Comunidad.id)\
     .order_by(func.sum(Solicitud.monto).desc())\
     .all()
    
    # Datos para gráfica de solicitudes por estatus
    datos_estatus = db.session.query(
        Solicitud.status,
        func.count(Solicitud.id).label('total')
    ).group_by(Solicitud.status)\
     .all()
    
    return {
        'presupuesto_ejercido': presupuesto_ejercido,
        'total_beneficiarios': total_beneficiarios,
        'solicitudes_pendientes': solicitudes_pendientes,
        'alertas_duplicidad': alertas_duplicidad,
        'datos_comunidades': datos_comunidades,
        'datos_estatus': datos_estatus
    }

def obtener_fecha():
    """
    Obtiene la fecha actual en formato YYYY-MM-DD.
    
    Returns:
        str: Fecha actual formateada
    """
    return datetime.now().strftime("%Y-%m-%d")

def registrar_auditoria(usuario_id, accion, tabla, registro_id=None, detalles=None, ip_address=None):
    """
    Registra una acción en el log de auditoría.
    
    Args:
        usuario_id: ID del usuario que realiza la acción
        accion: Descripción de la acción realizada
        tabla: Tabla afectada
        registro_id: ID del registro afectado (opcional)
        detalles: Detalles adicionales (opcional)
        ip_address: Dirección IP del usuario (opcional)
    """
    from app.models import AuditoriaLog
    
    log = AuditoriaLog(
        usuario_id=usuario_id,
        accion=accion,
        tabla=tabla,
        registro_id=registro_id,
        detalles=detalles,
        ip_address=ip_address
    )
    
    db.session.add(log)
    try:
        db.session.commit()
        audit_logger.info(f"Auditoría: {accion} en {tabla} por usuario {usuario_id}")
    except Exception as e:
        db.session.rollback()
        app_logger.error(f"Error al registrar auditoría: {str(e)}")
