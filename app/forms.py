# -*- coding: utf-8 -*-
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, FloatField, DateField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError
from app.services import validar_curp, validar_rfc, COMUNIDADES_ATARJEA, DEPENDENCIAS

class LoginForm(FlaskForm):
    """Formulario de inicio de sesión"""
    email = StringField('Correo Electrónico', validators=[
        DataRequired(message="El correo electrónico es obligatorio"),
        Email(message="Formato de correo electrónico inválido")
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message="La contraseña es obligatoria")
    ])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')

class RegistroForm(FlaskForm):
    """Formulario de registro de usuarios"""
    email = StringField('Correo Electrónico', validators=[
        DataRequired(message="El correo electrónico es obligatorio"),
        Email(message="Formato de correo electrónico inválido")
    ])
    nombre = StringField('Nombre', validators=[
        DataRequired(message="El nombre es obligatorio")
    ])
    apellido_paterno = StringField('Apellido Paterno', validators=[
        DataRequired(message="El apellido paterno es obligatorio")
    ])
    apellido_materno = StringField('Apellido Materno', validators=[Optional()])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message="La contraseña es obligatoria"),
        Length(min=8, message="La contraseña debe tener al menos 8 caracteres")
    ])
    password2 = PasswordField('Repetir Contraseña', validators=[
        DataRequired(message="Debe confirmar la contraseña"),
        EqualTo('password', message="Las contraseñas deben coincidir")
    ])
    rol = SelectField('Rol', choices=[
        ('Capturista', 'Capturista'),
        ('Director', 'Director'),
        ('Admin', 'Administrador')
    ])
    submit = SubmitField('Registrar')

class SolicitudApoyoForm(FlaskForm):
    """Formulario de solicitud de apoyo con validaciones estrictas"""
    # Panel 1: Datos personales
    nombre = StringField('Nombre', validators=[
        DataRequired(message="El nombre es obligatorio")
    ])
    apellido_paterno = StringField('Apellido Paterno', validators=[
        DataRequired(message="El apellido paterno es obligatorio")
    ])
    apellido_materno = StringField('Apellido Materno', validators=[Optional()])
    curp = StringField('CURP', validators=[
        DataRequired(message="El CURP es obligatorio"), 
        Length(min=18, max=18, message="El CURP debe tener 18 caracteres"),
        Regexp('^[A-Z0-9]+$', message="El CURP solo debe contener letras mayúsculas y números")
    ])
    genero = SelectField('Género', choices=[('M', 'Masculino'), ('F', 'Femenino')])
    fecha_nacimiento = DateField('Fecha de Nacimiento', validators=[
        DataRequired(message="La fecha de nacimiento es obligatoria")
    ])
    rfc = StringField('RFC', validators=[
        Optional(),
        Length(min=10, max=13, message="El RFC debe tener entre 10 y 13 caracteres"),
        Regexp('^[A-Z0-9]+$', message="El RFC solo debe contener letras mayúsculas y números")
    ])
    
    # Panel 2: Ubicación
    comunidad = SelectField('Comunidad', coerce=int, validators=[
        DataRequired(message="Debe seleccionar una comunidad")
    ])
    codigo_postal = StringField('Código Postal', validators=[
        Optional(),
        Length(min=5, max=5, message="El código postal debe tener 5 dígitos"),
        Regexp('^[0-9]+$', message="El código postal solo debe contener números")
    ])
    telefono = StringField('Teléfono', validators=[
        Optional(),
        Length(min=10, max=15, message="El teléfono debe tener entre 10 y 15 dígitos"),
        Regexp('^[0-9]+$', message="El teléfono solo debe contener números")
    ])
    
    # Panel 3: Datos del apoyo
    programa = SelectField('Programa', coerce=int, validators=[
        DataRequired(message="Debe seleccionar un programa")
    ])
    monto = FloatField('Monto', validators=[
        DataRequired(message="El monto es obligatorio")
    ])
    dependencia = SelectField('Dependencia', choices=[
        (dep, dep) for dep in DEPENDENCIAS
    ], validators=[
        DataRequired(message="Debe seleccionar una dependencia")
    ])
    comentarios = TextAreaField('Comentarios', validators=[Optional()])
    
    submit = SubmitField('Registrar Solicitud')
    
    def validate_curp(self, field):
        """Validación personalizada para el CURP"""
        valido, mensaje = validar_curp(field.data)
        if not valido:
            raise ValidationError(mensaje)
    
    def validate_rfc(self, field):
        """Validación personalizada para el RFC"""
        if field.data:  # Solo validar si se proporciona un RFC
            valido, mensaje = validar_rfc(field.data)
            if not valido:
                raise ValidationError(mensaje)

class BusquedaForm(FlaskForm):
    """Formulario de búsqueda general"""
    termino = StringField('Término de búsqueda', validators=[
        DataRequired(message="Ingrese un término de búsqueda")
    ])
    submit = SubmitField('Buscar')

class AprobacionSolicitudForm(FlaskForm):
    """Formulario para aprobar o rechazar solicitudes"""
    solicitud_id = HiddenField('ID de Solicitud', validators=[DataRequired()])
    accion = SelectField('Acción', choices=[
        ('Aprobado', 'Aprobar'),
        ('Rechazado', 'Rechazar')
    ], validators=[DataRequired()])
    comentarios = TextAreaField('Comentarios', validators=[Optional()])
    submit = SubmitField('Confirmar')

class FiltroSolicitudesForm(FlaskForm):
    """Formulario para filtrar solicitudes"""
    status = SelectField('Estado', choices=[
        ('', 'Todos'),
        ('Pendiente', 'Pendiente'),
        ('Aprobado', 'Aprobado'),
        ('Rechazado', 'Rechazado'),
        ('Alerta: Posible Duplicado', 'Alerta: Posible Duplicado')
    ], validators=[Optional()])
    comunidad = SelectField('Comunidad', validators=[Optional()])
    programa = SelectField('Programa', validators=[Optional()])
    fecha_desde = DateField('Fecha Desde', validators=[Optional()])
    fecha_hasta = DateField('Fecha Hasta', validators=[Optional()])
    submit = SubmitField('Filtrar')
