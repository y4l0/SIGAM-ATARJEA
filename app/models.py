from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import enum

db = SQLAlchemy()

class RolUsuario(enum.Enum):
    ADMIN = "Admin"
    PRESIDENTE = "Presidente"
    DIRECTOR = "Director"
    OPERADOR = "Operador"
    SERVICIOS_PUBLICOS = "ServiciosPublicos"

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default=RolUsuario.DIRECTOR.value)
    dependencia_id = db.Column(db.Integer, db.ForeignKey('dependencias.id'), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación con dependencia
    dependencia = db.relationship('Dependencia', backref='usuarios')
    
    def __repr__(self):
        return f'<Usuario {self.email}>'
    
    def get_id(self):
        return str(self.id)
    
    def es_admin(self):
        return (self.rol or '').lower() == RolUsuario.ADMIN.value.lower()
    
    def es_presidente(self):
        return (self.rol or '').lower() == RolUsuario.PRESIDENTE.value.lower()
    
    def es_director(self):
        return (self.rol or '').lower() == RolUsuario.DIRECTOR.value.lower()
    
    def es_operador(self):
        return (self.rol or '').lower() == RolUsuario.OPERADOR.value.lower()
    
    def es_servicios_publicos(self):
        return (self.rol or '').lower() == RolUsuario.SERVICIOS_PUBLICOS.value.lower()
    
    def puede_cerrar_ejercicio(self):
        """Solo el Presidente Municipal o un Admin pueden cerrar el ejercicio anual."""
        return self.es_admin() or self.es_presidente()

    def tiene_vision_total(self):
        """
        CORRECCIÓN CRÍTICA DE AISLAMIENTO/MÉTRICAS: criterio ÚNICO Y
        CENTRALIZADO de "visión ejecutiva total" (ve TODAS las
        dependencias, sin filtrar por dependencia_id). Antes, numerosas
        rutas de exportación (Excel), reportes y consulta de adjuntos
        usaban `if not current_user.es_admin():` como único criterio
        para decidir si filtrar por dependencia. Esto excluía al rol
        Presidente (Alcalde) de la visión total: como su dependencia_id
        es NULL, terminaba filtrado por `dependencia_id IS NULL`, que
        NUNCA coincide con ninguna solicitud real, devolviendo SIEMPRE
        cero registros en exportaciones/métricas aunque sí existan datos
        en la base de datos. Usar este método en vez de es_admin() a
        secas evita ese hueco y mantiene el aislamiento estricto para
        Director/Operador/ServiciosPublicos.
        """
        return self.es_admin() or self.es_presidente()

class Ciudadano(db.Model):
    __tablename__ = 'ciudadanos'
    
    CURP = db.Column(db.String(18), primary_key=True)
    Nombre = db.Column(db.String(100), nullable=False)
    Apellido_Paterno = db.Column(db.String(100), nullable=False)
    Apellido_Materno = db.Column(db.String(100), nullable=True)
    RFC = db.Column(db.String(13), nullable=True)
    Genero = db.Column(db.String(1), nullable=True)
    Fecha_Nacimiento = db.Column(db.Date, nullable=True)
    Direccion = db.Column(db.String(200), nullable=True)
    Telefono = db.Column(db.String(20), nullable=True)
    Colonia = db.Column(db.String(100), nullable=True)
    Codigo_Postal = db.Column(db.String(10), nullable=True)
    Edad = db.Column(db.Integer, nullable=True)
    Discapacidad = db.Column(db.Boolean, default=False)
    
    # Relación con solicitudes
    solicitudes = db.relationship('Solicitud', backref='ciudadano', lazy=True)
    
    def __repr__(self):
        return f'<Ciudadano {self.CURP}>'
    
    def nombre_completo(self):
        return f'{self.Nombre} {self.Apellido_Paterno} {self.Apellido_Materno or ""}'.strip()

class EstatusEnum(enum.Enum):
    PENDIENTE = "Pendiente"
    APROBADO = "Aprobado"
    RECHAZADO = "Rechazado"
    OTORGADO = "Otorgado"

class TipoApoyoEnum(enum.Enum):
    """Tipos de apoyo institucionales fijos"""
    ALIMENTARIO = "Alimentario"
    EDUCATIVO = "Educativo"
    SALUD = "A la Salud"
    VIVIENDA = "A la Vivienda"
    MOVILIDAD = "Apoyo a la Movilidad"
    FORTALECIMIENTO_COMUNITARIO = "Fortalecimiento Comunitario y Cohesión Social"


class TipoBeneficiarioEnum(enum.Enum):
    """
    CLASIFICACIÓN DE BENEFICIARIOS: exactamente 3 opciones permitidas
    para identificar si el apoyo se otorga a una persona individual, a
    un grupo organizado o a una comunidad completa.
    """
    PARTICULAR = "Particular"
    GRUPO = "Grupo"
    COMUNIDAD = "Comunidad"

class Solicitud(db.Model):
    __tablename__ = 'solicitudes'
    
    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(20), unique=True, nullable=True)  # Folio único generado automáticamente
    CURP = db.Column(db.String(18), db.ForeignKey('ciudadanos.CURP'), nullable=False)
    Comunidad = db.Column(db.String(100), nullable=False)
    Programa = db.Column(db.String(100), nullable=False)
    Tipo_Apoyo = db.Column(db.String(100), nullable=False, default=TipoApoyoEnum.ALIMENTARIO.value)
    Monto = db.Column(db.Numeric(10, 2), nullable=True)  # Monto total (calculado automáticamente a partir del desglose por fuente)

    # DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO (4 apartados
    # independientes): Federal, Estatal, Municipal y del Beneficiario.
    # Cada apartado es opcional e independiente; el campo `Monto` se
    # mantiene como el TOTAL calculado automáticamente (suma de los 4)
    # para no romper la compatibilidad con reportes, gráficas y Excel
    # existentes que ya consultan `Solicitud.Monto`.
    Monto_Federal = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    Monto_Estatal = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    Monto_Municipal = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    Monto_Beneficiario = db.Column(db.Numeric(10, 2), nullable=True, default=0)

    # MONTOS ESTIMADOS: sección independiente de los "Montos Generales"
    # (los 4 campos anteriores). Permite capturar un monto proyectado o
    # aproximado del apoyo (cuando el monto definitivo aún no se conoce
    # con exactitud), separado visual y funcionalmente del monto real/
    # general ya ejercido. Totalmente opcional y editable en cualquier
    # momento; NUNCA se mezcla automáticamente con `Monto` (total general).
    Monto_Estimado = db.Column(db.Numeric(10, 2), nullable=True, default=0)

    # CLASIFICACIÓN DE BENEFICIARIOS: identifica si el apoyo corresponde
    # a una persona particular, un grupo organizado o una comunidad
    # completa. Editable en cualquier momento posterior al registro.
    Tipo_Beneficiario = db.Column(db.String(20), nullable=True, default=TipoBeneficiarioEnum.PARTICULAR.value)

    Dependencia = db.Column(db.String(100), nullable=True)  # Campo legacy
    dependencia_id = db.Column(db.Integer, db.ForeignKey('dependencias.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    Fecha_Solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    Estatus = db.Column(db.String(20), default=EstatusEnum.PENDIENTE.value)
    
    # Campos de auditoría para Autorizar/Rechazar
    usuario_autorizador = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    puesto_autorizador = db.Column(db.String(100), nullable=True)
    
    # Relación con usuario que creó la solicitud (especificamos foreign_keys para evitar ambigüedad)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], backref='solicitudes_creadas')
    
    # Relación con usuario autorizador
    autorizador = db.relationship('Usuario', foreign_keys=[usuario_autorizador], backref='solicitudes_autorizadas')
    
    # Relación con adjuntos
    adjuntos = db.relationship('AdjuntoSolicitud', backref='solicitud_relacion', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Solicitud {self.id} - {self.CURP}>'
    
    def tiene_documentos_completos(self):
        """Verifica si la solicitud tiene al menos un documento cargado"""
        return len(self.adjuntos) > 0

    def calcular_monto_total(self):
        """
        DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO: calcula y
        actualiza automáticamente `self.Monto` (total) como la suma de
        los 4 apartados independientes (Federal + Estatal + Municipal +
        Beneficiario). Se invoca siempre que se crea o edita una
        solicitud, garantizando que el total nunca quede desincronizado
        del desglose real capturado. Trata None como 0 para que montos
        parcialmente capturados no rompan la suma.
        """
        federal = float(self.Monto_Federal or 0)
        estatal = float(self.Monto_Estatal or 0)
        municipal = float(self.Monto_Municipal or 0)
        beneficiario = float(self.Monto_Beneficiario or 0)
        self.Monto = round(federal + estatal + municipal + beneficiario, 2)
        return self.Monto

    def monto_general(self):
        """Alias explícito del monto TOTAL de 'Montos Generales' (Federal+Estatal+Municipal+Beneficiario)."""
        return float(self.Monto or 0)

    def monto_estimado(self):
        """Monto de la sección independiente 'Montos Estimados'. Trata None como 0."""
        return float(self.Monto_Estimado or 0)

    def monto_gran_total(self):
        """
        LÓGICA DE SUMATORIA EN REPORTES Y MÉTRICAS: "Gran Total" combinado
        de Montos Generales + Montos Estimados, usado quien necesite ver
        el panorama completo (general y proyectado) en un solo número,
        sin alterar `self.Monto` (que sigue siendo exclusivamente el
        total de los 4 apartados generales, para no romper reportes y
        gráficas existentes que ya consultan `Solicitud.Monto`).
        """
        return round(self.monto_general() + self.monto_estimado(), 2)

    def generar_folio_secuencial(self):
        """Genera folio secuencial automático (base inicial: 1900006757)"""
        if self.folio:
            return self.folio
            
        # Buscar el último folio generado
        from app import db
        from sqlalchemy import func
        
        # Obtener el último folio numérico
        ultima_solicitud = Solicitud.query.order_by(Solicitud.id.desc()).first()
        
        if ultima_solicitud and ultima_solicitud.folio:
            try:
                # Extraer solo los números del folio
                ultimo_folio = ultima_solicitud.folio
                if ultimo_folio.isdigit():
                    nuevo_numero = int(ultimo_folio) + 1
                    self.folio = str(nuevo_numero)
                    return self.folio
                else:
                    # Folio no es solo números, extraer números si tiene formato ATJ-XXXX
                    if '-' in ultimo_folio:
                        partes = ultimo_folio.split('-')
                        numero = partes[-1]
                        if numero.isdigit():
                            nuevo_numero = int(numero) + 1
                            self.folio = f"{partes[0]}-{nuevo_numero}"
                            return self.folio
            except:
                pass
        
        # Base inicial según instrucción
        self.folio = "1900006757"
        return self.folio
    
    def registrar_auditoria(self, usuario_id, accion, detalles=None, ip_address=None):
        """Registra una acción de auditoría para esta solicitud"""
        from app import db
        from datetime import datetime
        
        auditoria = AuditLog(
            usuario_id=usuario_id,
            accion=accion,
            tabla='solicitudes',
            registro_id=str(self.id),
            detalles=detalles,
            fecha=datetime.utcnow()
        )
        db.session.add(auditoria)
        return auditoria

class Dependencia(db.Model):
    __tablename__ = 'dependencias'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text, nullable=True)
    
    # Relación con solicitudes
    solicitudes = db.relationship('Solicitud', backref='dependencia', lazy=True)
    
    def __repr__(self):
        return f'<Dependencia {self.nombre}>'

class Comunidad(db.Model):
    __tablename__ = 'comunidades'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<Comunidad {self.nombre}>'

class TipoDocumentoMunicipal(enum.Enum):
    """Tipos de documentos requeridos para solicitudes de apoyo"""
    IDENTIFICACION_OFICIAL = "Identificación Oficial"
    COMPROBANTE_DOMICILIO = "Comprobante de Domicilio"
    EVIDENCIA_FOTOGRAFICA = "Evidencia Fotográfica del Apoyo"
    RECETA_MEDICA = "Receta Médica"
    ACTA_NACIMIENTO = "Acta de Nacimiento"
    CURP_DOCUMENTO = "CURP"
    OTRO_DOCUMENTO = "Otro Documento"

class AdjuntoSolicitud(db.Model):
    """Documentos adjuntos a solicitudes de apoyo municipal"""
    __tablename__ = 'adjuntos_solicitud'
    
    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'), nullable=False, index=True)
    tipo_documento = db.Column(db.String(50), nullable=False)
    categoria_documento = db.Column(db.String(30), nullable=False)  # identificacion, comprobante, evidencia
    nombre_original = db.Column(db.String(255), nullable=False)
    nombre_archivo = db.Column(db.String(255), nullable=False, unique=True)
    ruta_archivo = db.Column(db.String(500), nullable=False)
    tamano_bytes = db.Column(db.Integer, nullable=False)
    tipo_mime = db.Column(db.String(100), nullable=True)
    extension = db.Column(db.String(10), nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    usuario_carga_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    hash_archivo = db.Column(db.String(64), nullable=True)  # SHA-256 para integridad
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f'<Adjunto {self.id} - {self.tipo_documento} ({self.extension})>'
    
    def obtener_informacion_archivo(self):
        """Retorna información estructurada del archivo"""
        return {
            'id': self.id,
            'tipo': self.tipo_documento,
            'categoria': self.categoria_documento,
            'nombre_original': self.nombre_original,
            'nombre_archivo': self.nombre_archivo,
            'tamano_bytes': self.tamano_bytes,
            'tamano_humano': self._formatear_tamano(self.tamano_bytes),
            'extension': self.extension,
            'tipo_mime': self.tipo_mime,
            'fecha_carga': self.fecha_carga.isoformat() if self.fecha_carga else None
        }
    
    @staticmethod
    def _formatear_tamano(tamano_bytes):
        """Formatea el tamaño en bytes a formato legible"""
        for unidad in ['B', 'KB', 'MB', 'GB']:
            if tamano_bytes < 1024.0:
                return f"{tamano_bytes:.2f} {unidad}"
            tamano_bytes /= 1024.0
        return f"{tamano_bytes:.2f} TB"
    
    def verificar_integridad(self):
        """Verifica la integridad del archivo (implementación futura)"""
        # TODO: Implementar verificación de hash SHA-256
        return True

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    accion = db.Column(db.String(100), nullable=False)
    tabla = db.Column(db.String(100), nullable=False)
    registro_id = db.Column(db.String(100), nullable=False)
    detalles = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    usuario = db.relationship('Usuario', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.id} - {self.accion}>'

class AuditoriaLog(db.Model):
    """Modelo para registrar acciones de auditoría en el sistema con más detalles"""
    __tablename__ = 'auditoria_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    accion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)
    detalle_cambio = db.Column(db.Text, nullable=True)
    tabla_afectada = db.Column(db.String(100), nullable=True)
    registro_id = db.Column(db.String(100), nullable=True)
    
    # Índice para búsquedas rápidas por fecha
    __table_args__ = (
        db.Index('idx_auditoria_fecha', fecha.desc()),
        db.Index('idx_auditoria_usuario', user_id),
    )
    
    def __repr__(self):
        return f'<AuditoriaLog {self.id} - {self.accion[:30]}>'

class CierreEjercicio(db.Model):
    """
    Registro histórico e inmutable de cada Cierre de Ejercicio Anual.
    Cada cierre congela el presupuesto total ejercido y genera un
    respaldo (backup) físico de la base de datos para el Órgano de Control.
    """
    __tablename__ = 'cierres_ejercicio'

    id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False, unique=True)
    fecha_cierre = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    presupuesto_total_ejercido = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_solicitudes_aprobadas = db.Column(db.Integer, nullable=False, default=0)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    ruta_backup = db.Column(db.String(500), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    usuario = db.relationship('Usuario', backref='cierres_realizados')

    def __repr__(self):
        return f'<CierreEjercicio {self.anio} - ${self.presupuesto_total_ejercido}>'


class VehiculoMunicipal(db.Model):
    """
    Padrón/Catálogo real de las unidades del municipio (vehículos
    oficiales y maquinaria) que alimenta los menús desplegables del
    formulario de captura de combustible, evitando campos de texto libre.
    """
    __tablename__ = 'vehiculos_municipales'

    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(20), nullable=False, default='VEHICULO')  # VEHICULO o MAQUINARIA
    nombre = db.Column(db.String(150), nullable=False)
    placa = db.Column(db.String(20), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    modelo = db.Column(db.String(50), nullable=True)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<VehiculoMunicipal {self.nombre} - {self.placa or "S/P"}>'


class OperadorMunicipal(db.Model):
    """Padrón de operadores/responsables de Servicios Públicos Municipales
    que alimenta el menú desplegable de 'Conductor/Responsable'."""
    __tablename__ = 'operadores_municipales'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    puesto = db.Column(db.String(100), nullable=True)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<OperadorMunicipal {self.nombre}>'


class ConfiguracionCombustible(db.Model):
    """
    Configuración financiera del Módulo de Combustible: costo unitario
    vigente por litro, usado para calcular el costo monetario de cada
    despacho (Litros x Costo Unitario) sin bloquear jamás la captura.
    Solo debe existir un registro activo a la vez.
    """
    __tablename__ = 'configuracion_combustible'

    id = db.Column(db.Integer, primary_key=True)
    costo_litro = db.Column(db.Numeric(10, 2), nullable=False, default=24.50)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)

    def __repr__(self):
        return f'<ConfiguracionCombustible ${self.costo_litro}/L>'

    @staticmethod
    def obtener_costo_vigente():
        """Devuelve el costo por litro vigente; si no hay configuración, usa $24.50 por defecto."""
        config = ConfiguracionCombustible.query.order_by(ConfiguracionCombustible.id.desc()).first()
        return float(config.costo_litro) if config else 24.50


class Unidad(db.Model):
    """Catálogo de vehículos municipales con medición por KM (OFICIAL/EXTERNO/FORANEA/CIUDADANO)."""
    __tablename__ = 'catalogo_unidades'

    id = db.Column(db.Integer, primary_key=True)
    num_economico = db.Column(db.String(30), nullable=True)
    placa = db.Column(db.String(20), nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    modelo = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    tipo_combustible = db.Column(db.String(20), nullable=True, default='Gasolina')
    capacidad_tanque = db.Column(db.Float, nullable=True, default=60.0)
    tipo_medicion = db.Column(db.String(10), nullable=False, default='KM')  # KM | HORAS | NINGUNO
    ultimo_km = db.Column(db.Float, nullable=True, default=0.0)
    activa = db.Column(db.Boolean, default=True)

    # FORMULARIO N° 10: rendimiento base esperado de la unidad, usado para
    # calcular los litros TEÓRICOS que debería consumir un itinerario y
    # compararlos contra los litros realmente asignados (alerta pasiva).
    # Su unidad depende de tipo_medicion: km/L si es 'KM', L/hora si es 'HORAS'.
    rendimiento_base = db.Column(db.Float, nullable=True, default=10.0)

    # PADRÓN REAL DEL PARQUE VEHICULAR MUNICIPAL (importado desde el
    # archivo oficial "PARQUE VEHICULARCORREGIDO.xlsx"): área a la que
    # está adscrita la unidad, marca, tipo/clase/línea del fabricante y
    # número de serie (VIN), usados para mostrar el detalle real del
    # vehículo en el Formulario N° 10 y en los catálogos del sistema.
    area = db.Column(db.String(150), nullable=True)
    marca = db.Column(db.String(80), nullable=True)
    tipo = db.Column(db.String(80), nullable=True)
    clase = db.Column(db.String(80), nullable=True)
    linea = db.Column(db.String(80), nullable=True)
    serie = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Unidad {self.nombre} - {self.placa or "S/P"}>'


class Equipo(db.Model):
    """Catálogo de maquinaria pesada municipal con medición por HORAS (horómetro)."""
    __tablename__ = 'catalogo_equipos'

    id = db.Column(db.Integer, primary_key=True)
    num_economico = db.Column(db.String(30), nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    tipo_combustible = db.Column(db.String(20), nullable=True, default='Diésel')
    capacidad_tanque = db.Column(db.Float, nullable=True, default=100.0)
    ultimo_horometro = db.Column(db.Float, nullable=True, default=0.0)
    activa = db.Column(db.Boolean, default=True)

    # FORMULARIO N° 10: rendimiento base esperado del equipo en L/hora,
    # análogo a Unidad.rendimiento_base (km/L) pero para maquinaria
    # medida por horómetro (ej. Camión de Basura). Usado para la alerta
    # pasiva de exceso de rendimiento; nunca bloquea el guardado.
    rendimiento_base_horas = db.Column(db.Float, nullable=True, default=8.0)

    def __repr__(self):
        return f'<Equipo {self.nombre}>'


class Conductor(db.Model):
    """Catálogo de choferes/operadores responsables de las unidades."""
    __tablename__ = 'catalogo_conductores'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    puesto = db.Column(db.String(100), nullable=True)
    activo = db.Column(db.Boolean, default=True)

    # FORMULARIO N° 10: vigencia de la licencia de manejo del chofer,
    # usada para mostrar una alerta visual pasiva si está vencida al
    # momento de asignarle combustible (nunca bloquea la asignación).
    licencia_numero = db.Column(db.String(50), nullable=True)
    licencia_vigencia = db.Column(db.Date, nullable=True)

    def __repr__(self):
        return f'<Conductor {self.nombre}>'

    def licencia_vencida(self):
        """True si la licencia de manejo ya venció (alerta pasiva, nunca bloqueante)."""
        if not self.licencia_vigencia:
            return False
        from datetime import date
        return self.licencia_vigencia < date.today()


class Autorizador(db.Model):
    """Catálogo de personas que autorizan los despachos de combustible."""
    __tablename__ = 'catalogo_autorizadores'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    puesto = db.Column(db.String(100), nullable=True)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Autorizador {self.nombre}>'


class Despachador(db.Model):
    """Catálogo de personas que despachan físicamente el combustible."""
    __tablename__ = 'catalogo_despachadores'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Despachador {self.nombre}>'


class Motivo(db.Model):
    """Catálogo de motivos de despacho, segmentado por tipo de bitácora."""
    __tablename__ = 'catalogo_motivos'

    id = db.Column(db.Integer, primary_key=True)
    tipo_bitacora = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Motivo {self.tipo_bitacora}: {self.nombre}>'


class Area(db.Model):
    """Catálogo de áreas/dependencias solicitantes del combustible."""
    __tablename__ = 'catalogo_areas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    activa = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Area {self.nombre}>'


class Gasolinera(db.Model):
    """Catálogo de gasolineras usadas en cargas foráneas."""
    __tablename__ = 'catalogo_gasolineras'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    ubicacion = db.Column(db.String(200), nullable=True)
    activa = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Gasolinera {self.nombre}>'


class ConfiguracionUmbrales(db.Model):
    """
    Umbrales configurables para el semáforo de alertas pasivas del
    Módulo de Combustible (ver app/combustible_logic.py). Solo el
    registro más reciente está vigente.
    """
    __tablename__ = 'configuracion_umbrales_combustible'

    id = db.Column(db.Integer, primary_key=True)
    rendimiento_pct_bajo_mediana = db.Column(db.Integer, default=30)
    cargas_aprendizaje_minimas = db.Column(db.Integer, default=5)
    dias_min_entre_cargas = db.Column(db.Integer, default=2)
    pct_precio_fuera_promedio = db.Column(db.Integer, default=40)
    dias_ciudadano_apoyo_previo = db.Column(db.Integer, default=30)
    dias_sin_foto_tablero = db.Column(db.Integer, default=30)
    capacidad_contenedor_litros = db.Column(db.Integer, default=1000)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow)

    def a_dict(self):
        return {
            'rendimiento_pct_bajo_mediana': self.rendimiento_pct_bajo_mediana,
            'cargas_aprendizaje_minimas': self.cargas_aprendizaje_minimas,
            'dias_min_entre_cargas': self.dias_min_entre_cargas,
            'pct_precio_fuera_promedio': self.pct_precio_fuera_promedio,
            'dias_ciudadano_apoyo_previo': self.dias_ciudadano_apoyo_previo,
            'dias_sin_foto_tablero': self.dias_sin_foto_tablero,
            'capacidad_contenedor_litros': self.capacidad_contenedor_litros,
        }

    @staticmethod
    def obtener_vigente():
        from .combustible_logic import obtener_umbrales_default
        config = ConfiguracionUmbrales.query.order_by(ConfiguracionUmbrales.id.desc()).first()
        return config.a_dict() if config else obtener_umbrales_default()


class TipoFluidoEnum(enum.Enum):
    """
    ORDEN TÉCNICA MAESTRA - ARQUITECTURA MULTITANQUE: los 3 fluidos que
    el Municipio de Atarjea controla de forma independiente en el
    Módulo de Servicios Públicos, cada uno con capacidad de operar con
    hasta 2 tanques simultáneos (ver ConfiguracionTanque).
    """
    GASOLINA = "GASOLINA"
    DIESEL = "DIESEL"
    UREA = "UREA"

    @classmethod
    def nombre_completo(cls, valor):
        nombres = {
            cls.GASOLINA.value: "Gasolina",
            cls.DIESEL.value: "Diésel",
            cls.UREA.value: "Urea / Fluido Automotriz",
        }
        return nombres.get(valor, valor)


class ConfiguracionTanque(db.Model):
    """
    ORDEN TÉCNICA MAESTRA - DOBLE TANQUE SIMULTÁNEO: configuración de
    cada tanque físico (hasta 2 por fluido) que el panel de Servicios
    Públicos debe graficar de forma independiente. Tabla NUEVA (no
    altera ninguna tabla existente), por lo que se crea de forma segura
    con db.create_all() sin requerir migración manual de columnas.
    """
    __tablename__ = 'configuracion_tanques'

    id = db.Column(db.Integer, primary_key=True)
    tipo_fluido = db.Column(db.String(20), nullable=False, default=TipoFluidoEnum.GASOLINA.value)
    numero_tanque = db.Column(db.Integer, nullable=False, default=1)  # 1 o 2
    capacidad_litros = db.Column(db.Float, nullable=False, default=1000.0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    # ORDEN TÉCNICA MAESTRA - TANQUE SECUENCIAL AUTOMÁTICO: indica cuál de
    # los 2 tanques físicos del fluido es actualmente el "Principal"
    # (suministro primario) frente al "Secundario/Provisional" (respaldo).
    # Por defecto el Tanque 1 nace como Principal; si se agota, el sistema
    # promueve automáticamente al Tanque 2 (ver calcular_estado_
    # multitanque en routes.py), sin intervención manual.
    es_principal = db.Column(db.Boolean, nullable=False, default=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tipo_fluido', 'numero_tanque', name='uq_tanque_fluido_numero'),
    )

    @staticmethod
    def obtener_o_crear(tipo_fluido, numero_tanque, capacidad_default=1000.0):
        """
        CERO CAÍDAS: devuelve la configuración del tanque solicitado; si
        no existe, la crea con capacidad por defecto (el Tanque 1 nace
        como Principal). Nunca lanza excepción: ante cualquier error de
        BD regresa un objeto "en memoria" (no persistido) para que el
        Dashboard jamás colapse.
        """
        try:
            config = ConfiguracionTanque.query.filter_by(
                tipo_fluido=tipo_fluido, numero_tanque=numero_tanque
            ).first()
            if not config:
                config = ConfiguracionTanque(
                    tipo_fluido=tipo_fluido,
                    numero_tanque=numero_tanque,
                    capacidad_litros=capacidad_default,
                    activo=(numero_tanque == 1),
                    es_principal=(numero_tanque == 1)
                )
                db.session.add(config)
                db.session.commit()
            return config
        except Exception:
            db.session.rollback()
            config = ConfiguracionTanque(
                tipo_fluido=tipo_fluido, numero_tanque=numero_tanque,
                capacidad_litros=capacidad_default, activo=(numero_tanque == 1),
                es_principal=(numero_tanque == 1)
            )
            return config


class RegistroAbastoFluido(db.Model):
    """
    ORDEN TÉCNICA MAESTRA - ABASTO MULTIFLUIDO: entradas de combustible
    (Gasolina, Diésel o Urea) a un tanque específico (1 o 2). Tabla
    NUEVA e independiente de RegistroAbasto (legado, siempre Gasolina/
    Tanque 1), por lo que NO requiere ALTER TABLE ni migración de la
    base de datos ya existente.
    """
    __tablename__ = 'registros_abasto_fluido'

    id = db.Column(db.Integer, primary_key=True)
    tipo_fluido = db.Column(db.String(20), nullable=False, default=TipoFluidoEnum.GASOLINA.value)
    numero_tanque = db.Column(db.Integer, nullable=False, default=1)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    litros_recibidos = db.Column(db.Float, nullable=False, default=0.0)
    costo_litro = db.Column(db.Numeric(10, 2), nullable=True)
    costo_total = db.Column(db.Numeric(10, 2), nullable=True)
    proveedor = db.Column(db.String(150), nullable=True)
    documento = db.Column(db.String(20), nullable=True)
    numero_documento = db.Column(db.String(50), nullable=True)
    recibe = db.Column(db.String(150), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo = db.Column(db.Boolean, default=False)

    def calcular_costo_total(self):
        """CERO CAÍDAS: calcula costo_total = litros x costo_litro, nunca lanza excepción."""
        try:
            if self.costo_litro and self.litros_recibidos:
                self.costo_total = round(float(self.litros_recibidos) * float(self.costo_litro), 2)
        except Exception:
            self.costo_total = self.costo_total or 0
        return self.costo_total

    def __repr__(self):
        return f"<RegistroAbastoFluido {self.tipo_fluido} T{self.numero_tanque} {self.litros_recibidos}L>"



class RegistroAbasto(db.Model):
    """
    Registro de ENTRADAS de combustible al contenedor/cisterna municipal
    (abasto desde proveedor). El Dashboard calcula el nivel aproximado
    del contenedor como: suma de entradas - suma de litros de vales ACTIVOS.
    """
    __tablename__ = 'registros_abasto'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    proveedor = db.Column(db.String(150), nullable=True)
    municipio_origen = db.Column(db.String(100), nullable=True)
    litros_recibidos = db.Column(db.Float, nullable=False)
    precio_por_litro = db.Column(db.Numeric(10, 2), nullable=True)
    monto_total = db.Column(db.Numeric(10, 2), nullable=True)
    documento = db.Column(db.String(20), nullable=True)  # TICKET | FACTURA | NINGUNO
    numero = db.Column(db.String(50), nullable=True)
    recibe = db.Column(db.String(150), nullable=True)
    foto_documento = db.Column(db.String(500), nullable=True)
    foto_nivel_contenedor = db.Column(db.String(500), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    es_demo = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<RegistroAbasto {self.fecha} - {self.litros_recibidos} L>'

    # ALIAS DE COMPATIBILIDAD: el campo real de almacenamiento es `numero`
    # (reutilizado para folio de factura o remisión), pero se expone como
    # `numero_factura` para alinear la nomenclatura solicitada por la
    # orden técnica sin duplicar la columna ni crear un modelo redundante
    # (regla de "Cero Redundancia").
    @property
    def numero_factura(self):
        return self.numero

    @numero_factura.setter
    def numero_factura(self, valor):
        self.numero = valor


class BitacoraSistemaLog(db.Model):
    """
    Bitácora de sistema con HASH ENCADENADO (similar a una cadena de
    bloques simplificada): cada registro incluye el hash del anterior,
    de modo que si alguien intenta alterar el historial, la cadena deja
    de coincidir. Usada para inmutabilidad (creación/cancelación).
    """
    __tablename__ = 'bitacora_sistema_combustible'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accion = db.Column(db.String(50), nullable=False)
    registro_id = db.Column(db.Integer, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    detalle = db.Column(db.Text, nullable=True)
    hash_anterior = db.Column(db.String(64), nullable=True)
    hash_actual = db.Column(db.String(64), nullable=False)

    def __repr__(self):
        return f'<BitacoraSistemaLog {self.accion} #{self.registro_id}>'

    @staticmethod
    def calcular_hash(hash_anterior, accion, registro_id, detalle, fecha):
        import hashlib
        cadena = f"{hash_anterior or ''}|{accion}|{registro_id}|{detalle}|{fecha.isoformat() if fecha else ''}"
        return hashlib.sha256(cadena.encode('utf-8')).hexdigest()

    @staticmethod
    def registrar(accion, registro_id, usuario_id, detalle):
        """Agrega un evento a la cadena de auditoría. NUNCA bloquea: ante
        cualquier error solo retorna None."""
        try:
            ultimo = BitacoraSistemaLog.query.order_by(BitacoraSistemaLog.id.desc()).first()
            hash_anterior = ultimo.hash_actual if ultimo else None
            fecha = datetime.utcnow()
            hash_actual = BitacoraSistemaLog.calcular_hash(hash_anterior, accion, registro_id, detalle, fecha)
            entrada = BitacoraSistemaLog(
                fecha=fecha, accion=accion, registro_id=registro_id,
                usuario_id=usuario_id, detalle=detalle,
                hash_anterior=hash_anterior, hash_actual=hash_actual
            )
            db.session.add(entrada)
            return entrada
        except Exception:
            return None


class EstatusAsignacionEnum(enum.Enum):
    """
    ORDEN TÉCNICA MAESTRA (simplificación de estados): el ciclo de vida
    operativo del Formulario N° 10 maneja EXCLUSIVAMENTE tres estados
    visibles para el usuario: Autorizado -> En Proceso -> Revisión.
    'Revisión' es la etapa final donde se despliega el resumen completo
    de la asignación y se habilita la opción de Cancelar.

    CANCELADA se conserva como estado terminal de AUDITORÍA (nunca se
    borra un registro, solo se cancela con motivo obligatorio, conforme
    al principio de inmutabilidad/trazabilidad total), pero no es una
    de las "tres" etapas del flujo normal: solo se alcanza mediante la
    acción explícita de Cancelar.
    """
    AUTORIZADO = "Autorizado"
    EN_PROCESO = "En Proceso"
    REVISION = "Revisión"
    CANCELADA = "Cancelada"


class AsignacionCombustible(db.Model):
    """
    FORMULARIO N° 10 - Asignación de Combustible.

    Separa el ciclo de vida del vale (EMITIDA -> ENTREGADA -> COMPROBADA)
    del propio despacho físico (BitacoraCombustible), permitiendo
    planificar y controlar itinerarios/comisiones con un folio propio
    (ASIG-2026-XXXX), validación de rendimiento teórico vs. litros
    asignados, y seguimiento de vales vencidos pendientes de comprobar.
    NINGUNA validación de esta tabla bloquea su creación o avance de
    estatus; solo genera alertas visuales pasivas.
    """
    __tablename__ = 'asignaciones_combustible'

    id = db.Column(db.Integer, primary_key=True)
    folio_asignacion = db.Column(db.String(30), nullable=False, unique=True)
    unidad_organizacional = db.Column(db.String(150), nullable=True)
    tipo_asignacion = db.Column(db.String(20), nullable=False, default='OFICIAL')  # OFICIAL|MAQUINARIA|EXTERNO|FORANEA|CIUDADANO
    itinerario_destino = db.Column(db.String(200), nullable=True)
    fecha_inicio = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=True)
    responsable_nombre = db.Column(db.String(150), nullable=False)
    responsable_celular = db.Column(db.String(20), nullable=True)

    # FORMATO OFICIAL DEL FORMULARIO N° 10 (rediseño): fecha en que se
    # solicita el vale (distinta de fecha_inicio, que es la fecha de la
    # comisión), tipo de recorrido según el formato físico (Recorrido
    # Semanal / Local / Viajes), actividades a realizar durante la
    # comisión y nombre del Director de Área que autoriza.
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    tipo_recorrido = db.Column(db.String(30), nullable=True)  # Recorrido Semanal | Local | Viajes
    actividades = db.Column(db.Text, nullable=True)
    director_area = db.Column(db.String(150), nullable=True)

    # CAMPO OBLIGATORIO DE AUTORIZACIÓN: quién autoriza el vale de
    # combustible (Presidente Municipal, Secretario Particular, Director
    # de Área, etc., tomado del catálogo Autorizador). Se imprime en el
    # PDF oficial del Formulario N° 10.
    quien_autoriza = db.Column(db.String(150), nullable=True)

    chofer_id = db.Column(db.Integer, db.ForeignKey('catalogo_conductores.id'), nullable=True)
    vehiculo_id = db.Column(db.Integer, db.ForeignKey('catalogo_unidades.id'), nullable=True)
    chofer = db.relationship('Conductor', backref='asignaciones_combustible')
    vehiculo = db.relationship('Unidad', backref='asignaciones_combustible')

    # CATÁLOGO DE MAQUINARIA PESADA (medición por HORÓMETRO): usado
    # EXCLUSIVAMENTE cuando subtipo_asignacion == 'CAMION_BASURA'. Se
    # mantiene separado de `vehiculo_id` (Unidad, medición por KM) para
    # que ningún camión de basura pueda capturarse por kilometraje ni
    # ningún vehículo ligero/oficial pueda capturarse por horas.
    equipo_id = db.Column(db.Integer, db.ForeignKey('catalogo_equipos.id'), nullable=True)
    equipo = db.relationship('Equipo', backref='asignaciones_combustible')

    litros_asignados = db.Column(db.Float, nullable=False, default=0.0)
    tipo_combustible = db.Column(db.String(20), nullable=True, default='Gasolina')
    estatus = db.Column(db.String(20), nullable=False, default=EstatusAsignacionEnum.AUTORIZADO.value)

    # Motivo obligatorio de cancelación (inmutabilidad/auditoría): un
    # registro CANCELADO nunca se borra, solo se marca con el motivo.
    motivo_cancelacion = db.Column(db.Text, nullable=True)

    km_inicial = db.Column(db.Float, nullable=True)
    km_final = db.Column(db.Float, nullable=True)

    # SUBTIPO: distingue variantes dentro de MAQUINARIA (PIPA | CAMION_BASURA)
    # o dentro de CIUDADANO (TRASLADO | VALE_GASOLINA | VIAJES_AGUA). Los
    # camiones de basura se controlan OBLIGATORIAMENTE por horómetro, nunca
    # por kilometraje; las pipas siguen el formato de solicitud tradicional
    # (KM). Nunca bloquea el guardado si no aplica.
    subtipo_asignacion = db.Column(db.String(40), nullable=True)
    horometro_inicial = db.Column(db.Float, nullable=True)
    horometro_final = db.Column(db.Float, nullable=True)

    # DESTINO DEL APOYO DE AGUA (submenú obligatorio cuando tipo_asignacion
    # == 'PIPA', la bitácora "Camión Pipas"): Vivienda Particular |
    # Institución Educativa | Institución de Salud | Apoyo Comunitario.
    # Ver DestinoApoyoAguaEnum. No aplica a otros tipos ni bloquea el
    # guardado si no se especifica.
    destino_apoyo_agua = db.Column(db.String(40), nullable=True)

    def horas_trabajo(self):
        """Horas de trabajo reales (horómetro final - inicial), usadas
        obligatoriamente para los camiones de basura."""
        if self.horometro_inicial is not None and self.horometro_final is not None:
            return round(self.horometro_final - self.horometro_inicial, 2)
        return None

    # Trazabilidad
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo = db.Column(db.Boolean, default=False)

    # Vinculación opcional con el despacho físico real una vez comprobado
    bitacora_id = db.Column(db.Integer, db.ForeignKey('bitacoras_combustible.id'), nullable=True)
    bitacora = db.relationship('BitacoraCombustible', backref='asignacion_origen')

    def __repr__(self):
        return f'<AsignacionCombustible {self.folio_asignacion} - {self.estatus}>'

    def km_recorridos(self):
        """Distancia recorrida real, si ya se registraron ambos kilometrajes."""
        if self.km_inicial is not None and self.km_final is not None:
            return round(self.km_final - self.km_inicial, 2)
        return None

    def litros_teoricos(self):
        """
        Litros TEÓRICOS esperados según el rendimiento base de la unidad
        y la distancia recorrida (km/L), o -para CAMION_BASURA- según el
        rendimiento base del equipo y las Horas de Trabajo (L/hora). Si
        no hay datos suficientes de ninguno de los dos, se deja en None
        ya que no hay forma de estimarlo sin un valor de referencia.
        """
        try:
            # COMPATIBILIDAD: CAMION_BASURA ahora es bitácora propia
            # (tipo_asignacion), pero registros legados podían traerlo
            # como subtipo dentro de MAQUINARIA; se reconocen ambos casos.
            if self.tipo_asignacion == 'CAMION_BASURA' or self.subtipo_asignacion == 'CAMION_BASURA':
                rendimiento_horas = self.equipo.rendimiento_base_horas if self.equipo and self.equipo.rendimiento_base_horas else None
                horas = self.horas_trabajo()
                if rendimiento_horas and horas and rendimiento_horas > 0:
                    return round(horas * rendimiento_horas, 2)
                return None

            rendimiento = self.vehiculo.rendimiento_base if self.vehiculo and self.vehiculo.rendimiento_base else None
            km_rec = self.km_recorridos()
            if rendimiento and km_rec and rendimiento > 0:
                return round(km_rec / rendimiento, 2)
        except Exception:
            pass
        return None

    def excede_umbral_rendimiento(self, umbral_pct=20):
        """
        Compara litros_asignados contra litros_teoricos(). Si los litros
        asignados exceden el umbral porcentual sobre lo teórico, retorna
        True (alerta visual), pero NUNCA bloquea el guardado ni el avance
        de estatus de la asignación.
        """
        try:
            teoricos = self.litros_teoricos()
            if teoricos and teoricos > 0 and self.litros_asignados:
                exceso_pct = (float(self.litros_asignados) - teoricos) / teoricos * 100.0
                return exceso_pct > umbral_pct
        except Exception:
            pass
        return False

    def avanzar_estatus(self, nuevo_estatus, usuario_id=None):
        """
        Transición de estatus Autorizado -> En Proceso -> Revisión (o
        Cancelada en cualquier momento). Registra el cambio en la
        bitácora de sistema con hash encadenado; nunca bloquea.
        """
        anterior = self.estatus
        self.estatus = nuevo_estatus
        BitacoraSistemaLog.registrar(
            accion='CAMBIO_ESTATUS_ASIGNACION_COMBUSTIBLE',
            registro_id=self.id,
            usuario_id=usuario_id,
            detalle=f"Folio {self.folio_asignacion}: {anterior} -> {nuevo_estatus}"
        )

    def cancelar(self, motivo_cancelacion, usuario_id=None):
        """
        Cancela la asignación con motivo obligatorio (inmutabilidad: el
        registro nunca se borra). Registra el cambio en auditoría.
        """
        anterior = self.estatus
        self.estatus = EstatusAsignacionEnum.CANCELADA.value
        self.motivo_cancelacion = motivo_cancelacion
        BitacoraSistemaLog.registrar(
            accion='CANCELAR_ASIGNACION_COMBUSTIBLE',
            registro_id=self.id,
            usuario_id=usuario_id,
            detalle=f"Folio {self.folio_asignacion}: {anterior} -> CANCELADA. Motivo: {motivo_cancelacion}"
        )


class TipoBitacoraEnum(enum.Enum):
    """
    ORDEN TÉCNICA MAESTRA - INTEGRACIÓN DE LAS 11 BITÁCORAS OFICIALES:
    las 11 bitácoras físicas oficiales del Municipio de Atarjea que este
    módulo digitaliza, cada una con su propia plantilla de Excel oficial
    (ver CONFIG_PLANTILLAS_BITACORA en routes.py) y manteniendo
    exactamente los mismos campos que el personal de Servicios Públicos
    ya llena a mano.

    CAMBIOS RESPECTO A LA VERSIÓN ANTERIOR (6 tipos):
    - "Equipo Ligero" se renombra a EQUIPO_MENOR (mismo significado,
      nuevo nombre institucional según la bitácora oficial).
    - "Camión Pipas" (antes subtipo PIPA dentro de MAQUINARIA) se
      PROMUEVE a tipo de bitácora propio (PIPA), ya que tiene su propia
      plantilla oficial independiente de Maquinaria Pesada.
    - Se agregan AUTOBUS (Autobuses Escolares/Pasajeros), UREA (Fluido
      Automotriz para Maquinaria Pesada) y LUBRICANTE (Aceite de Motor
      para Maquinaria Pesada).
    - ORDEN TÉCNICA MAESTRA (sincronización de catálogo Excel): "Camión
      de Basura" (antes subtipo CAMION_BASURA dentro de MAQUINARIA) se
      PROMUEVE a tipo de bitácora propio (CAMION_BASURA) para que la
      exportación a Excel use su propia plantilla oficial
      "BITACORA_CAMION_BASURA.xlsx". La medición sigue siendo
      EXCLUSIVAMENTE por Horómetro (Horas de Trabajo), nunca por
      kilometraje, reutilizando subtipo_asignacion/horometro_inicial/
      horometro_final tal como ya funcionaba.

    Dentro de MAQUINARIA y CIUDADANO existen subtipos más finos (ver
    SubtipoMaquinariaEnum y SubtipoCiudadanoEnum) capturados en el
    campo AsignacionCombustible.subtipo_asignacion.
    """
    OFICIAL = "OFICIAL"
    AUTOBUS = "AUTOBUS"
    PIPA = "PIPA"
    MAQUINARIA = "MAQUINARIA"
    EQUIPO_MENOR = "EQUIPO_MENOR"
    EXTERNO = "EXTERNO"
    FORANEA = "FORANEA"
    CIUDADANO = "CIUDADANO"
    CAMION_BASURA = "CAMION_BASURA"
    UREA = "UREA"
    LUBRICANTE = "LUBRICANTE"

    # NOMBRES COMPLETOS INSTITUCIONALES: usados en selectores, filtros,
    # tablas, exportación a Excel y en la Gráfica de Dona Ejecutiva, para
    # que el Alcalde y el personal de Servicios Públicos siempre vean la
    # denominación oficial completa (nunca la clave interna en MAYÚSCULAS).
    @classmethod
    def nombre_completo(cls, valor):
        nombres = {
            cls.OFICIAL.value: "Vehículos Oficiales",
            cls.AUTOBUS.value: "Autobuses Escolares / Pasajeros",
            cls.PIPA.value: "Camión Pipas",
            cls.MAQUINARIA.value: "Maquinaria Pesada",
            cls.EQUIPO_MENOR.value: "Equipo Menor",
            cls.EXTERNO.value: "Vehículos Externos",
            cls.FORANEA.value: "Cargas Foráneas",
            cls.CIUDADANO.value: "Apoyos Ciudadanos",
            cls.CAMION_BASURA.value: "Camión de Basura",
            cls.UREA.value: "Fluido Automotriz / UREA (Maquinaria Pesada)",
            cls.LUBRICANTE.value: "Lubricantes / Aceite de Motor (Maquinaria Pesada)",
        }
        return nombres.get(valor, valor)


class SubtipoMaquinariaEnum(enum.Enum):
    """
    Subtipos dentro de la bitácora MAQUINARIA (Maquinaria Pesada).
    CORRECCIÓN: PIPA se retiró de este Enum porque ahora es un tipo de
    bitácora propio (TipoBitacoraEnum.PIPA) con su propia plantilla
    oficial. Los camiones de basura se controlan OBLIGATORIAMENTE por
    horómetro; el resto de la maquinaria pesada usa kilometraje.
    """
    CAMION_BASURA = "CAMION_BASURA"


class SubtipoCiudadanoEnum(enum.Enum):
    """Las 3 modalidades de Apoyo Ciudadano de combustible."""
    TRASLADO = "TRASLADO"
    VALE_GASOLINA = "VALE_GASOLINA"
    VIAJES_AGUA = "VIAJES_AGUA"


class DestinoApoyoAguaEnum(enum.Enum):
    """Submenú obligatorio cuando el tipo de bitácora es PIPA (Camión
    Pipas): a dónde se dirige el viaje de agua."""
    VIVIENDA_PARTICULAR = "VIVIENDA_PARTICULAR"
    INSTITUCION_EDUCATIVA = "INSTITUCION_EDUCATIVA"
    INSTITUCION_SALUD = "INSTITUCION_SALUD"
    APOYO_COMUNITARIO = "APOYO_COMUNITARIO"


class BitacoraCombustible(db.Model):
    """
    Registro digital de las 5 bitácoras físicas de control de combustible
    del corralón municipal (Dirección de Servicios Públicos Municipales).

    PRINCIPIO DE DISEÑO: Captura idéntica a la papelería física. Ningún
    campo de este modelo bloquea el despacho de combustible; la validación
    de rendimiento (alerta_rendimiento) se calcula de forma pasiva y
    únicamente genera una bandera visual para el Alcalde y la Encargada
    de Servicios Públicos, nunca un bloqueo operativo.
    """
    __tablename__ = 'bitacoras_combustible'

    id = db.Column(db.Integer, primary_key=True)
    tipo_bitacora = db.Column(db.String(20), nullable=False, default=TipoBitacoraEnum.OFICIAL.value)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    folio_vale = db.Column(db.String(50), nullable=False)
    destino_comision = db.Column(db.String(200), nullable=True)
    vehiculo_nombre = db.Column(db.String(150), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    modelo = db.Column(db.String(50), nullable=True)
    placa = db.Column(db.String(20), nullable=True)
    km_inicial = db.Column(db.Float, nullable=True)
    km_final = db.Column(db.Float, nullable=True)
    horas_trabajo = db.Column(db.Float, nullable=True)
    litros = db.Column(db.Float, nullable=False)
    comunidad = db.Column(db.String(100), nullable=True)
    responsable_nombre = db.Column(db.String(150), nullable=False)
    foto_odometro = db.Column(db.String(500), nullable=True)
    foto_vale = db.Column(db.String(500), nullable=True)
    alerta_rendimiento = db.Column(db.Boolean, default=False, nullable=False)

    # Padrón real de unidades/operadores (menús desplegables, no texto libre)
    vehiculo_id = db.Column(db.Integer, db.ForeignKey('vehiculos_municipales.id'), nullable=True)
    operador_id = db.Column(db.Integer, db.ForeignKey('operadores_municipales.id'), nullable=True)
    vehiculo = db.relationship('VehiculoMunicipal', backref='bitacoras_combustible')
    operador = db.relationship('OperadorMunicipal', backref='bitacoras_combustible')

    # Módulo financiero: costo monetario del despacho (Litros x Costo Unitario)
    costo_litro_aplicado = db.Column(db.Numeric(10, 2), nullable=True)
    costo_total = db.Column(db.Numeric(10, 2), nullable=True)

    # ---------------- FASE 2: BLOQUE COMÚN ----------------
    hora = db.Column(db.String(10), nullable=True)
    area_solicitante = db.Column(db.String(150), nullable=True)
    motivo = db.Column(db.String(150), nullable=True)
    tipo_combustible = db.Column(db.String(20), nullable=True)
    autoriza_id = db.Column(db.Integer, db.ForeignKey('catalogo_autorizadores.id'), nullable=True)
    despacha_id = db.Column(db.Integer, db.ForeignKey('catalogo_despachadores.id'), nullable=True)
    autoriza = db.relationship('Autorizador', backref='bitacoras_autorizadas')
    despacha = db.relationship('Despachador', backref='bitacoras_despachadas')
    es_emergencia = db.Column(db.Boolean, default=False)
    es_captura_posterior = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text, nullable=True)
    capturado_por = db.Column(db.String(150), nullable=True)
    capturado_en = db.Column(db.DateTime, default=datetime.utcnow)
    estatus = db.Column(db.String(20), nullable=False, default='ACTIVO')  # ACTIVO | CANCELADO
    motivo_cancelacion = db.Column(db.Text, nullable=True)
    es_demo = db.Column(db.Boolean, default=False)
    hash_registro = db.Column(db.String(64), nullable=True)

    # ---------------- FASE 2: catálogos nuevos (Unidad/Equipo) ----------------
    unidad_id = db.Column(db.Integer, db.ForeignKey('catalogo_unidades.id'), nullable=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey('catalogo_equipos.id'), nullable=True)
    conductor_id = db.Column(db.Integer, db.ForeignKey('catalogo_conductores.id'), nullable=True)
    unidad = db.relationship('Unidad', backref='bitacoras_unidad')
    equipo = db.relationship('Equipo', backref='bitacoras_equipo')
    conductor = db.relationship('Conductor', backref='bitacoras_conductor')

    # ---------------- FASE 2: campos específicos OFICIAL ----------------
    km_anterior = db.Column(db.Float, nullable=True)
    km_actual = db.Column(db.Float, nullable=True)
    km_recorridos = db.Column(db.Float, nullable=True)
    tanque_lleno = db.Column(db.Boolean, nullable=True)
    folio_solicitud = db.Column(db.String(50), nullable=True)
    km_estimados_ruta = db.Column(db.Float, nullable=True)

    # ---------------- FASE 2: campos específicos MAQUINARIA ----------------
    horometro_anterior = db.Column(db.Float, nullable=True)
    horometro_actual = db.Column(db.Float, nullable=True)
    actividad = db.Column(db.String(200), nullable=True)
    ubicacion_obra = db.Column(db.String(200), nullable=True)
    foto_horometro = db.Column(db.String(500), nullable=True)

    # ---------------- FASE 2: campos específicos EXTERNO ----------------
    vehiculo_descripcion = db.Column(db.String(200), nullable=True)
    dependencia_propietaria = db.Column(db.String(150), nullable=True)
    motivo_apoyo = db.Column(db.String(200), nullable=True)
    solicitante_nombre = db.Column(db.String(150), nullable=True)
    oficio_autorizacion = db.Column(db.String(100), nullable=True)

    # ---------------- FASE 2: campos específicos FORANEA ----------------
    fecha_salida = db.Column(db.DateTime, nullable=True)
    fecha_regreso = db.Column(db.DateTime, nullable=True)
    km_salida = db.Column(db.Float, nullable=True)
    km_regreso = db.Column(db.Float, nullable=True)
    gasolinera = db.Column(db.String(150), nullable=True)
    monto_pesos = db.Column(db.Numeric(10, 2), nullable=True)
    precio_por_litro = db.Column(db.Numeric(10, 2), nullable=True)
    tiene_factura = db.Column(db.String(20), nullable=True)  # TICKET | FACTURA | NINGUNO
    foto_ticket = db.Column(db.String(500), nullable=True)

    # ---------------- FASE 2: campos específicos CIUDADANO ----------------
    beneficiario_nombre = db.Column(db.String(150), nullable=True)
    beneficiario_curp = db.Column(db.String(18), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    descripcion_breve = db.Column(db.String(200), nullable=True)
    apoyo_previo = db.Column(db.Boolean, nullable=True)
    foto_solicitud = db.Column(db.String(500), nullable=True)
    foto_identificacion = db.Column(db.String(500), nullable=True)

    # Trazabilidad: usuario que capturó el registro (auditoría)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario = db.relationship('Usuario', backref='bitacoras_combustible_capturadas')

    def __repr__(self):
        return f'<BitacoraCombustible {self.id} - {self.tipo_bitacora} - Folio {self.folio_vale}>'

    def calcular_rendimiento(self):
        """
        VALIDACIÓN PASIVA DE RENDIMIENTO (nunca bloqueante):
        - Vehículos (OFICIAL/EXTERNO/FORANEA/CIUDADANO): km/l fuera del
          rango razonable (3 a 18 km/l) genera bandera.
        - Maquinaria (MAQUINARIA): litros/hora fuera de rango razonable
          (3 a 25 L/h) genera bandera.
        Esta función solo asigna self.alerta_rendimiento; jamás impide
        guardar el registro.
        """
        try:
            self.alerta_rendimiento = False

            if not self.litros or self.litros <= 0:
                return self.alerta_rendimiento

            if self.tipo_bitacora == TipoBitacoraEnum.MAQUINARIA.value:
                if self.horas_trabajo and self.horas_trabajo > 0:
                    litros_por_hora = self.litros / self.horas_trabajo
                    if litros_por_hora < 3 or litros_por_hora > 25:
                        self.alerta_rendimiento = True
            else:
                if self.km_inicial is not None and self.km_final is not None:
                    km_recorridos = self.km_final - self.km_inicial
                    if km_recorridos > 0:
                        rendimiento_km_l = km_recorridos / self.litros
                        if rendimiento_km_l < 3 or rendimiento_km_l > 18:
                            self.alerta_rendimiento = True
                    elif km_recorridos <= 0:
                        # Kilometraje incoherente (no bloquea, solo alerta)
                        self.alerta_rendimiento = True
        except Exception:
            # Cualquier error en el cálculo NUNCA debe impedir el guardado
            self.alerta_rendimiento = False

        return self.alerta_rendimiento

    def rendimiento_calculado(self):
        """Retorna un texto descriptivo del rendimiento para mostrar en el dashboard."""
        try:
            if self.tipo_bitacora == TipoBitacoraEnum.MAQUINARIA.value:
                if self.horas_trabajo and self.horas_trabajo > 0 and self.litros:
                    return f"{(self.litros / self.horas_trabajo):.2f} L/hora"
            else:
                if self.km_inicial is not None and self.km_final is not None and self.litros:
                    km_recorridos = self.km_final - self.km_inicial
                    if km_recorridos > 0:
                        return f"{(km_recorridos / self.litros):.2f} km/L"
            return "N/A"
        except Exception:
            return "N/A"

    def calcular_costo(self, costo_litro=None):
        """
        MÓDULO FINANCIERO: calcula el costo monetario del despacho
        (Litros x Costo Unitario del Combustible). Nunca lanza excepción
        ni bloquea el guardado del registro; ante cualquier error deja
        el costo en 0.
        """
        try:
            if costo_litro is None:
                costo_litro = ConfiguracionCombustible.obtener_costo_vigente()

            self.costo_litro_aplicado = round(float(costo_litro), 2)
            self.costo_total = round(float(self.litros or 0) * float(costo_litro), 2)
        except Exception:
            self.costo_litro_aplicado = 0
            self.costo_total = 0

        return self.costo_total

    def calcular_campos_derivados(self):
        """
        FASE 2 - "Capturar menos y calcular más": deriva km_recorridos,
        horas_trabajo y precio_por_litro a partir de los datos crudos
        capturados por el operador. Nunca lanza excepciones.
        """
        try:
            if self.km_anterior is not None and self.km_actual is not None:
                self.km_recorridos = round(self.km_actual - self.km_anterior, 2)
                # Mantener compatibilidad con los campos legados del dashboard
                self.km_inicial = self.km_anterior
                self.km_final = self.km_actual

            if self.horometro_anterior is not None and self.horometro_actual is not None:
                self.horas_trabajo = round(self.horometro_actual - self.horometro_anterior, 2)

            if self.tipo_bitacora == TipoBitacoraEnum.FORANEA.value:
                if self.monto_pesos and self.litros and float(self.litros) > 0:
                    self.precio_por_litro = round(float(self.monto_pesos) / float(self.litros), 2)
        except Exception:
            pass

    def generar_hash(self):
        """Genera un hash SHA-256 del contenido inmutable del registro,
        usado para detectar alteraciones posteriores (inmutabilidad)."""
        try:
            import hashlib
            cadena = (
                f"{self.tipo_bitacora}|{self.folio_vale}|{self.litros}|"
                f"{self.responsable_nombre}|{self.fecha.isoformat() if self.fecha else ''}"
            )
            self.hash_registro = hashlib.sha256(cadena.encode('utf-8')).hexdigest()
        except Exception:
            self.hash_registro = None
        return self.hash_registro

    def cancelar(self, motivo_cancelacion, usuario_id=None):
        """
        INMUTABILIDAD: un registro ACTIVO nunca se edita ni se borra.
        Solo puede 'Cancelarse' con un motivo obligatorio; si el dato
        estaba mal, se debe crear un NUEVO registro con la corrección.
        """
        self.estatus = 'CANCELADO'
        self.motivo_cancelacion = motivo_cancelacion
        BitacoraSistemaLog.registrar(
            accion='CANCELAR_BITACORA_COMBUSTIBLE',
            registro_id=self.id,
            usuario_id=usuario_id,
            detalle=f"Folio {self.folio_vale} cancelado. Motivo: {motivo_cancelacion}"
        )
