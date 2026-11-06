#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registrar_usuarios_dependencias.py

Script de actualización ÚNICO (idempotente) para registrar/garantizar las
cuentas oficiales de las Direcciones/Dependencias municipales que SÍ cuentan
con correo electrónico institucional asignado (se omiten intencionalmente
las dependencias que aún no tienen correo).

Para cada dependencia:
  - Se busca (o crea, si aún no existe en el catálogo) el registro en la
    tabla `dependencias`, respetando los nombres oficiales ya existentes
    cuando hay coincidencia (DIF, Deportes, Desarrollo Social, Desarrollo
    Rural y Económico) y creando el registro nuevo únicamente para las
    dependencias que todavía no estaban en el catálogo (Procuraduría,
    Casa de la Cultura, Prevención, Protección Civil).
  - Se crea (o actualiza, si ya existía) el Usuario con rol "Director"
    (ve únicamente las solicitudes de su propia dependencia), vinculado
    a esa dependencia mediante `dependencia_id`, con la contraseña
    cifrada mediante `generate_password_hash` (Werkzeug) -nunca en texto
    plano-, y con el campo `nombre` igual al nombre exacto de la
    dependencia/dirección.
  - Se registra la acción en `AuditoriaLog` (trazabilidad total) con el
    detalle del cambio, usando como actor la cuenta de Administrador del
    sistema (ejecución administrativa por script autorizado).

Uso:
    python registrar_usuarios_dependencias.py

Es seguro ejecutar este script varias veces: si el usuario ya existe,
solo se actualiza (contraseña, nombre, rol, dependencia y estado activo),
sin duplicar registros.
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Usuario, Dependencia, AuditoriaLog
from werkzeug.security import generate_password_hash


# Mapeo de dependencia -> nombre oficial en el catálogo. Las que ya
# existen previamente en `run.py::inicializar_usuarios_y_dependencias()`
# se referencian con su nombre EXACTO para no duplicar el catálogo; las
# que no existían se crean con su nombre institucional correspondiente.
CUENTAS_A_REGISTRAR = [
    {
        "clave": "DIF",
        "dependencia_nombre": "DIF Municipal",
        "email": "atarjea2016@gmail.com",
        "password": "difm2427",
    },
    {
        "clave": "PROCURADURIA",
        "dependencia_nombre": "Procuraduría",
        "email": "procatarjea@gmail.com",
        "password": "procuraduria2427",
    },
    {
        "clave": "DESARROLLO RURAL",
        "dependencia_nombre": "Dirección de Desarrollo Rural y Económico",
        "email": "ruralatarjea@gmail.com",
        "password": "drural2427",
    },
    {
        "clave": "CASA DE LA CULTURA",
        "dependencia_nombre": "Casa de la Cultura",
        "email": "casadelaculturaatarjea@gmail.com",
        "password": "cdecultura2427",
    },
    {
        "clave": "DESARROLLO SOCIAL",
        "dependencia_nombre": "Dirección de Desarrollo Social",
        "email": "desarrollo-social@atarjea.gob.mx",
        "password": "dsocial2427",
    },
    {
        "clave": "PREVENCION",
        "dependencia_nombre": "Prevención",
        "email": "atarjeaprevencionmo6@gmail.com",
        "password": "prevencion2427",
    },
    {
        "clave": "DEPORTES",
        "dependencia_nombre": "Dirección de Deportes",
        "email": "Kimbybueno84@gmail.com",
        "password": "ddeportes2427",
    },
    {
        "clave": "PROTECCION CIVIL",
        "dependencia_nombre": "Protección Civil",
        "email": "proteccionatarjea2021@gmail.com",
        "password": "dproteccionc2427",
    },
]

ROL_ASIGNADO = "Director"  # Cada director ve únicamente las solicitudes de su dependencia.


def registrar_usuarios():
    """Crea/actualiza dependencias y usuarios dentro del contexto de la app Flask."""
    app = create_app()
    with app.app_context():
        try:
            # Actor de auditoría: el Administrador oficial del sistema,
            # ya que esta acción se ejecuta mediante script administrativo
            # autorizado (fuera de una sesión HTTP con current_user).
            admin = Usuario.query.filter_by(email="admin@atarjea.gob.mx").first()
            admin_id = admin.id if admin else None

            creados, actualizados, dependencias_creadas = [], [], []

            for cuenta in CUENTAS_A_REGISTRAR:
                nombre_dep = cuenta["dependencia_nombre"]
                email = cuenta["email"].strip().lower()
                password_hash = generate_password_hash(cuenta["password"])

                # 1) Garantizar la Dependencia en el catálogo
                dependencia = Dependencia.query.filter_by(nombre=nombre_dep).first()
                if not dependencia:
                    dependencia = Dependencia(nombre=nombre_dep)
                    db.session.add(dependencia)
                    db.session.flush()  # Obtener dependencia.id antes del commit
                    dependencias_creadas.append(nombre_dep)

                # 2) Crear o actualizar el Usuario
                usuario = Usuario.query.filter(
                    db.func.lower(Usuario.email) == email
                ).first()

                if not usuario:
                    usuario = Usuario(
                        nombre=nombre_dep,
                        email=email,
                        password=password_hash,
                        rol=ROL_ASIGNADO,
                        dependencia_id=dependencia.id,
                        activo=True,
                    )
                    db.session.add(usuario)
                    db.session.flush()
                    creados.append((nombre_dep, email))
                    detalle = (
                        f"Script administrativo creó la cuenta de la dependencia "
                        f"'{nombre_dep}' (rol '{ROL_ASIGNADO}') con correo '{email}'."
                    )
                else:
                    usuario.nombre = nombre_dep
                    usuario.password = password_hash
                    usuario.rol = ROL_ASIGNADO
                    usuario.dependencia_id = dependencia.id
                    usuario.activo = True
                    actualizados.append((nombre_dep, email))
                    detalle = (
                        f"Script administrativo actualizó la cuenta de la dependencia "
                        f"'{nombre_dep}' (rol '{ROL_ASIGNADO}') con correo '{email}' "
                        f"(contraseña restablecida)."
                    )

                db.session.flush()

                # 3) Trazabilidad total: registrar el alta/actualización en AuditoriaLog
                if admin_id is not None:
                    db.session.add(AuditoriaLog(
                        user_id=admin_id,
                        accion="Registro masivo de usuario por dependencia (script)",
                        tabla_afectada="usuarios",
                        registro_id=str(usuario.id),
                        ip_address="127.0.0.1",
                        detalle_cambio=detalle,
                        fecha=datetime.utcnow(),
                    ))

            db.session.commit()

            print("=" * 72)
            print("  REGISTRO DE CUENTAS OFICIALES POR DEPENDENCIA")
            print("=" * 72)
            print(f"  Dependencias nuevas creadas en el catálogo: {len(dependencias_creadas)}")
            for d in dependencias_creadas:
                print(f"    - {d}")
            print(f"  Usuarios creados:      {len(creados)}")
            for n, e in creados:
                print(f"    - {n}: {e}")
            print(f"  Usuarios actualizados: {len(actualizados)}")
            for n, e in actualizados:
                print(f"    - {n}: {e}")
            print("=" * 72)
            print("  Contraseñas almacenadas únicamente como hash (Werkzeug).")
            print("=" * 72)

        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] No se pudo completar el registro de usuarios: {str(e)}")
            raise


if __name__ == "__main__":
    registrar_usuarios()
