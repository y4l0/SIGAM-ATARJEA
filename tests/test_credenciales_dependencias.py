# -*- coding: utf-8 -*-
"""
tests/test_credenciales_dependencias.py

CORRECCIÓN CRÍTICA DE AUTENTICACIÓN - SINCRONIZACIÓN DE CREDENCIALES DE
LAS 10 CUENTAS INSTITUCIONALES DE DEPENDENCIA SIN AFECTAR REGISTROS.

Este módulo valida, usando el test_client() de Flask (login real, el
mismo flujo que usa cualquier Director en producción):

  1. Las 10 cuentas institucionales del catálogo oficial (DIF,
     Procuraduría, Desarrollo Rural, Casa de la Cultura, Desarrollo
     Social, Prevención, Deportes, Presidencia Municipal, Secretaría
     del Ayuntamiento y Protección Civil) existen en la base de datos
     y SIEMPRE pueden iniciar sesión con su contraseña oficial.
  2. El hash almacenado es Werkzeug real (nunca texto plano) y
     `check_password_hash` lo valida correctamente.
  3. Cada cuenta queda vinculada a su dependencia correspondiente.
  4. PRESERVACIÓN ABSOLUTA DE DATOS: la sincronización de credenciales
     (ejecutada al importar app/run) NUNCA borra ni modifica las
     tablas de solicitudes, bitácoras o asignaciones de combustible.

Ejecutar con:
    python -m pytest tests/test_credenciales_dependencias.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import check_password_hash

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud, BitacoraCombustible, AsignacionCombustible


# Catálogo oficial de las 10 cuentas institucionales (email -> contraseña
# oficial), idéntico al consolidado en run.py::inicializar_usuarios_y_dependencias().
CUENTAS_OFICIALES = {
    'atarjea2016@gmail.com': ('difm2427', 'DIF Municipal'),
    'procatarjea@gmail.com': ('procuraduria2427', 'Procuraduría'),
    'ruralatarjea@gmail.com': ('drural2427', 'Dirección de Desarrollo Rural y Económico'),
    'casadelaculturaatarjea@gmail.com': ('cdecultura2427', 'Casa de la Cultura'),
    'desarrollo-social@atarjea.gob.mx': ('dsocial2427', 'Dirección de Desarrollo Social'),
    'atarjeaprevencionmo6@gmail.com': ('prevencion2427', 'Prevención'),
    'Kimbybueno84@gmail.com': ('ddeportes2427', 'Dirección de Deportes'),
    'presidenciamunicipala@gmail.com': ('pmunicipal2427', 'Presidencia Municipal'),
    'sayuntamiento@gmail.com': ('sayuntamiento2427', 'Secretaría del Ayuntamiento'),
    'proteccionatarjea2021@gmail.com': ('dproteccionc2427', 'Protección Civil'),
}


class TestCredencialesDependencias(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    # ---------------- REQUERIMIENTO 1 Y 2: LOGIN REAL + HASH WERKZEUG ----------------

    def test_01_las_10_cuentas_institucionales_existen_y_tienen_hash_valido(self):
        """Cada una de las 10 cuentas oficiales debe existir con un hash
        Werkzeug que valide correctamente su contraseña oficial."""
        with self.app.app_context():
            for email, (password, _dep_nombre) in CUENTAS_OFICIALES.items():
                usuario = Usuario.query.filter(
                    db.func.lower(Usuario.email) == email.lower()
                ).first()
                self.assertIsNotNone(usuario, f"La cuenta institucional '{email}' debe existir siempre.")
                self.assertTrue(usuario.activo, f"La cuenta '{email}' debe estar activa.")
                self.assertNotEqual(usuario.password, password, f"La contraseña de '{email}' NUNCA debe guardarse en texto plano.")
                self.assertTrue(
                    check_password_hash(usuario.password, password),
                    f"El hash almacenado para '{email}' debe coincidir con la contraseña oficial '{password}'."
                )

    def test_02_cada_cuenta_institucional_puede_iniciar_sesion_realmente(self):
        """Login real (test_client) con cada una de las 10 cuentas oficiales debe ser exitoso (200, sin error)."""
        for email, (password, _dep_nombre) in CUENTAS_OFICIALES.items():
            client = self.app.test_client()
            resp = client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200, f"El login de '{email}' debe responder 200.")
            self.assertNotIn(b'Credenciales incorrectas', resp.data, f"El login de '{email}' NO debe mostrar 'Credenciales incorrectas'.")
            self.assertNotIn(b'Internal Server Error', resp.data)

    def test_03_login_con_mayusculas_minusculas_distintas_en_el_correo_funciona(self):
        """El login debe ser insensible a mayúsculas/minúsculas en el correo (normalización real de producción)."""
        resp = self._login('ATARJEA2016@GMAIL.COM', 'difm2427')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Credenciales incorrectas', resp.data)

    # ---------------- REQUERIMIENTO 3: VINCULACIÓN CORRECTA A DEPENDENCIA ----------------

    def test_04_cada_cuenta_institucional_esta_vinculada_a_su_dependencia(self):
        """Cada cuenta debe estar vinculada a su dependencia oficial correspondiente."""
        with self.app.app_context():
            for email, (_password, dep_nombre) in CUENTAS_OFICIALES.items():
                usuario = Usuario.query.filter(
                    db.func.lower(Usuario.email) == email.lower()
                ).first()
                self.assertIsNotNone(usuario.dependencia_id, f"La cuenta '{email}' debe tener una dependencia asignada.")
                dependencia = Dependencia.query.get(usuario.dependencia_id)
                self.assertIsNotNone(dependencia)
                self.assertEqual(dependencia.nombre, dep_nombre)

    def test_05_presidencia_municipal_tiene_rol_admin(self):
        """La cuenta de Presidencia Municipal debe conservar su rol Admin (control total)."""
        with self.app.app_context():
            usuario = Usuario.query.filter(
                db.func.lower(Usuario.email) == 'presidenciamunicipala@gmail.com'
            ).first()
            self.assertTrue(usuario.es_admin())

    # ---------------- REQUERIMIENTO 4: PRESERVACIÓN ABSOLUTA DE DATOS ----------------

    def test_06_sincronizacion_de_credenciales_no_altera_el_historial_de_solicitudes(self):
        """La sincronización de usuarios/credenciales NUNCA debe alterar el
        número de solicitudes, bitácoras o asignaciones ya existentes."""
        with self.app.app_context():
            total_solicitudes_antes = Solicitud.query.count()
            total_bitacoras_antes = BitacoraCombustible.query.count()
            total_asignaciones_antes = AsignacionCombustible.query.count()

        # Reimportar/crear la app de nuevo ejecuta otra vez la
        # sincronización de usuarios (idempotente); debe dar el mismo resultado.
        from app import create_app as _create_app_de_nuevo
        app_recreada = _create_app_de_nuevo()
        with app_recreada.app_context():
            total_solicitudes_despues = Solicitud.query.count()
            total_bitacoras_despues = BitacoraCombustible.query.count()
            total_asignaciones_despues = AsignacionCombustible.query.count()

        self.assertEqual(total_solicitudes_antes, total_solicitudes_despues,
                          "El número de solicitudes NUNCA debe cambiar por sincronizar credenciales.")
        self.assertEqual(total_bitacoras_antes, total_bitacoras_despues,
                          "El número de bitácoras de combustible NUNCA debe cambiar por sincronizar credenciales.")
        self.assertEqual(total_asignaciones_antes, total_asignaciones_despues,
                          "El número de asignaciones de combustible NUNCA debe cambiar por sincronizar credenciales.")


if __name__ == '__main__':
    unittest.main()
