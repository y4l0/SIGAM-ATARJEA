 from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import Index, func

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='admin')
    solicitudes = db.relationship('Solicitud', backref='user', lazy=True)
    auditorias = db.relationship('AuditoriaLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Comunidad(db.Model):
    """
    Modelo para representar comunidades o localidades del municipio.
    Cada comunidad puede tener múltiples solicitudes asociadas.
    """
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    codigo_postal = db.Column(db.String(5), nullable=False)
    region = db.Column(db.String(50), nullable=True)
    solicitudes = db.relationship('Solicitud', backref='comunidad_ref', lazy=True)
    
    # Índice para búsquedas rápidas por nombre
    __table_args__ = (
        Index('idx_comunidad_nombre', func.lower(nombre)),
    )
    
    def __repr__(self):
        return f"<Comunidad {self.nombre}>"

class Solicitud(db.Model):
    """
    Modelo principal para representar solicitudes de apoyo.
    Contiene toda la información del beneficiario y el apoyo solicitado.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Folio único generado automáticamente
    folio = db.Column(db.String(20), unique=True, nullable=True, index=True)
    
    # Datos Personales
    nombre = db.Column(db.String(100), nullable=False)
    apellido_paterno = db.Column(db.String(50), nullable=False)
    apellido_materno = db.Column(db.String(50), nullable=False)
    
    # Identidad
    curp = db.Column(db.String(18), nullable=False, index=True)
    genero = db.Column(db.String(1), nullable=False)  # 'M' o 'F'
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    rfc = db.Column(db.String(13), nullable=True)
    
    # Ubicación
    comunidad_id = db.Column(db.Integer, db.ForeignKey('comunidad.id'), nullable=False)
    
    # Contacto y Apoyo
    telefono = db.Column(db.String(15), nullable=True)
    programa = db.Column(db.String(100), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    
    # Estado y fechas
    estado = db.Column(db.String(50), default='Pendiente')
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Índices para búsquedas rápidas
    __table_args__ = (
        Index('idx_solicitud_curp', curp),
        Index('idx_solicitud_nombre_completo', func.lower(nombre), func.lower(apellido_paterno), func.lower(apellido_materno)),
        Index('idx_solicitud_estado', estado),
        Index('idx_solicitud_fecha', fecha_solicitud.desc()),
    )
    
    def generar_folio(self):
        """
        Genera folio único secuencial para la solicitud.
        Primer folio: 1900006757, incrementando en +1 cada nueva solicitud.
        """
        if self.folio:
            return self.folio
            
        # Obtener el número de solicitudes existentes
        from app import db
        from sqlalchemy import func
        
        # Consultar la última solicitud para determinar el folio base
        ultima_solicitud = db.session.query(Solicitud).order_by(Solicitud.id.desc()).first()
        
        if ultima_solicitud and ultima_solicitud.folio:
            try:
                # Extraer número del folio anterior
                ultimo_numero = int(ultima_solicitud.folio)
                nuevo_numero = ultimo_numero + 1
            except ValueError:
                nuevo_numero = 1900006757
        else:
            nuevo_numero = 1900006757
            
        self.folio = str(nuevo_numero)
        return self.folio
        
    def __repr__(self):
        return f"<Solicitud {self.id} - {self.nombre} {self.apellido_paterno}>"

class AuditoriaLog(db.Model):
    """
    Modelo para registrar acciones de auditoría en el sistema.
    Fundamental para la trazabilidad y seguridad del sistema.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    accion = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    detalles = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    
    # Índice para búsquedas rápidas por fecha
    __table_args__ = (
        Index('idx_auditoria_timestamp', timestamp.desc()),
    )
    
    def __repr__(self):
        return f"<AuditoriaLog {self.id} - {self.accion[:30]}>"