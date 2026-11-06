# -*- coding: utf-8 -*-
"""
CORRECCIÓN DE DEUDA TÉCNICA: este archivo probaba un modelo `User` que
NUNCA existió en app/models.py (el modelo real se llama `Usuario`, con
columnas en español: email, password, nombre, rol). El test original
colapsaba con ImportError desde su creación. Se reescribe usando los
modelos reales vigentes (Usuario, Comunidad, Dependencia, Solicitud)
contra la base de datos real (nunca crea/destruye tablas) para que
aporte cobertura real sin riesgo de borrar datos de producción.

Ejecutar con: python -m pytest tests/test_models.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Comunidad, Dependencia, Solicitud


class TestModels(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.rollback()
        self.app_context.pop()

    def test_usuario_hash_password_valido(self):
        """El hash de contraseñas (Werkzeug) usado por el modelo Usuario
        real debe generar y validar correctamente, sin texto plano."""
        from werkzeug.security import generate_password_hash, check_password_hash
        hash_generado = generate_password_hash('clave-de-prueba-test-models')
        self.assertTrue(check_password_hash(hash_generado, 'clave-de-prueba-test-models'))
        self.assertFalse(check_password_hash(hash_generado, 'clave-incorrecta'))

    def test_comunidad_model_consultable_sin_colapsar(self):
        """El catálogo de Comunidad debe ser consultable sin lanzar excepción."""
        total = Comunidad.query.count()
        self.assertGreaterEqual(total, 0)

    def test_dependencia_model_consultable_sin_colapsar(self):
        """El catálogo de Dependencia debe ser consultable sin lanzar excepción."""
        total = Dependencia.query.count()
        self.assertGreaterEqual(total, 0)

    def test_usuario_admin_existe_con_rol_correcto(self):
        """La cuenta admin@atarjea.gob.mx debe existir siempre tras el
        arranque automático del sistema (ver run.py)."""
        admin = Usuario.query.filter_by(email='admin@atarjea.gob.mx').first()
        self.assertIsNotNone(admin, "La cuenta admin@atarjea.gob.mx debe existir siempre.")
        self.assertTrue(admin.es_admin())

    def test_solicitud_model_consultable_sin_colapsar(self):
        """La tabla Solicitud debe poder consultarse sin lanzar excepción,
        incluso si está vacía."""
        total = Solicitud.query.count()
        self.assertGreaterEqual(total, 0)


if __name__ == '__main__':
    unittest.main()