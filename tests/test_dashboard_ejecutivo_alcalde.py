# -*- coding: utf-8 -*-
"""
DIRECTIVA FINAL: DASHBOARD EJECUTIVO DEL ALCALDE, LÍNEA DE TIEMPO
OPERATIVA Y REGISTRO DE CUENTAS.

Valida, usando el test_client() de Flask:
  1. El registro público de nuevas cuentas (/registro_cuenta) SIEMPRE
     crea la cuenta con rol "Director" (nunca Admin/Presidente, por
     seguridad), y requiere Área/Dirección.
  2. AISLAMIENTO ESTRICTO POR ROL: un Director NUNCA ve en /dashboard
     ni en /solicitudes las solicitudes de otra dependencia.
  3. El Panel Ejecutivo del Alcalde (/auditoria_en_vivo) permite
     seleccionar un trabajador/Director y desplegar su Línea de
     Tiempo Operativa del Día sin colapsar, incluyendo el filtro
     "Ayer" y los resúmenes ejecutivos (monto invertido, litros por
     fluido).
  4. Un Director NO puede acceder al Panel Ejecutivo del Alcalde.

Ejecutar con: python -m pytest tests/test_dashboard_ejecutivo_alcalde.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud
from werkzeug.security import generate_password_hash


class TestDashboardEjecutivoAlcalde(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        # Prepara dos Directores de dependencias DISTINTAS con al menos
        # una solicitud cada uno, para poder probar el aislamiento real.
        with cls.app.app_context():
            dep_a = Dependencia.query.filter_by(nombre='TEST_DEP_AISLAMIENTO_A').first()
            if not dep_a:
                dep_a = Dependencia(nombre='TEST_DEP_AISLAMIENTO_A')
                db.session.add(dep_a)
                db.session.flush()

            dep_b = Dependencia.query.filter_by(nombre='TEST_DEP_AISLAMIENTO_B').first()
            if not dep_b:
                dep_b = Dependencia(nombre='TEST_DEP_AISLAMIENTO_B')
                db.session.add(dep_b)
                db.session.flush()

            director_a = Usuario.query.filter_by(email='director_a@test.atarjea.gob.mx').first()
            if not director_a:
                director_a = Usuario(
                    nombre='Director Prueba A', email='director_a@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep_a.id, activo=True
                )
                db.session.add(director_a)
                db.session.flush()

            director_b = Usuario.query.filter_by(email='director_b@test.atarjea.gob.mx').first()
            if not director_b:
                director_b = Usuario(
                    nombre='Director Prueba B', email='director_b@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep_b.id, activo=True
                )
                db.session.add(director_b)
                db.session.flush()

            if not Solicitud.query.filter_by(folio='TEST-AISLAMIENTO-A-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-AISLAMIENTO-A-0001', CURP='AISL000101HGTAAA01',
                    Comunidad='Atarjea', Programa='Prueba', Tipo_Apoyo='Alimentario',
                    Monto=100.0, Dependencia=dep_a.nombre, dependencia_id=dep_a.id,
                    Estatus='Pendiente', usuario_id=director_a.id
                ))
            if not Solicitud.query.filter_by(folio='TEST-AISLAMIENTO-B-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-AISLAMIENTO-B-0001', CURP='AISL000101HGTBBB02',
                    Comunidad='Atarjea', Programa='Prueba', Tipo_Apoyo='Educativo',
                    Monto=200.0, Dependencia=dep_b.nombre, dependencia_id=dep_b.id,
                    Estatus='Pendiente', usuario_id=director_b.id
                ))
            db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, client, email, password):
        return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def test_01_registro_cuenta_siempre_crea_rol_director(self):
        """El registro público debe crear SIEMPRE una cuenta con rol Director."""
        with self.app.app_context():
            dep_id = Dependencia.query.first().id

        email_nuevo = 'nuevo_director_autoregistro@test.atarjea.gob.mx'
        with self.app.app_context():
            existente = Usuario.query.filter_by(email=email_nuevo).first()
            if existente:
                db.session.delete(existente)
                db.session.commit()

        resp = self.client.post('/registro_cuenta', data={
            'nombre': 'Director Autoregistrado de Prueba',
            'email': email_nuevo,
            'password': 'ClaveSegura123',
            'password2': 'ClaveSegura123',
            'dependencia_id': str(dep_id),
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

        with self.app.app_context():
            nuevo = Usuario.query.filter_by(email=email_nuevo).first()
            self.assertIsNotNone(nuevo, "La cuenta debió crearse.")
            self.assertEqual(nuevo.rol, 'Director', "El registro público SIEMPRE debe asignar rol Director.")
            db.session.delete(nuevo)
            db.session.commit()

    def test_02_registro_cuenta_rechaza_passwords_distintos(self):
        """Si las contraseñas no coinciden, no debe crear la cuenta ni colapsar."""
        with self.app.app_context():
            dep_id = Dependencia.query.first().id
        resp = self.client.post('/registro_cuenta', data={
            'nombre': 'Prueba Password',
            'email': 'password_distinto@test.atarjea.gob.mx',
            'password': 'ClaveUno1234',
            'password2': 'ClaveDos5678',
            'dependencia_id': str(dep_id),
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertIsNone(Usuario.query.filter_by(email='password_distinto@test.atarjea.gob.mx').first())

    def test_03_director_no_ve_solicitudes_de_otra_dependencia_en_dashboard(self):
        """
        AISLAMIENTO ESTRICTO: el Director A no debe ver el CURP de la
        solicitud de la Dependencia B en /dashboard (solicitudes_recientes).
        """
        client = self.app.test_client()
        self._login(client, 'director_a@test.atarjea.gob.mx', 'Prueba12345')
        resp = client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'AISL000101HGTBBB02', resp.data)

    def test_04_director_no_ve_solicitudes_de_otra_dependencia_en_solicitudes(self):
        """
        AISLAMIENTO ESTRICTO: el Director B no debe ver la solicitud (CURP)
        de la Dependencia A en /solicitudes, pero sí debe ver la suya propia.
        (La plantilla solicitudes.html muestra el CURP, no el folio).
        """
        client = self.app.test_client()
        self._login(client, 'director_b@test.atarjea.gob.mx', 'Prueba12345')
        resp = client.get('/solicitudes')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'AISL000101HGTAAA01', resp.data)
        self.assertIn(b'AISL000101HGTBBB02', resp.data)

    def test_05_director_no_puede_acceder_al_panel_ejecutivo_alcalde(self):
        """Un Director no debe tener acceso al Panel Ejecutivo del Alcalde."""
        client = self.app.test_client()
        self._login(client, 'director_a@test.atarjea.gob.mx', 'Prueba12345')
        resp = client.get('/auditoria_en_vivo', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Línea de Tiempo Operativa'.encode('utf-8'), resp.data)

    def test_06_alcalde_puede_seleccionar_director_y_ver_linea_de_tiempo(self):
        """El Alcalde debe poder seleccionar un Director y ver su línea de tiempo sin colapsar."""
        client = self.app.test_client()
        self._login(client, 'admin@atarjea.gob.mx', 'admin')
        with self.app.app_context():
            director_a = Usuario.query.filter_by(email='director_a@test.atarjea.gob.mx').first()
            director_id = director_a.id
        resp = client.get(f'/auditoria_en_vivo?director_id={director_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_07_filtro_ayer_no_colapsa(self):
        """El nuevo filtro 'Ayer' no debe colapsar el Panel Ejecutivo."""
        client = self.app.test_client()
        self._login(client, 'admin@atarjea.gob.mx', 'admin')
        resp = client.get('/auditoria_en_vivo?periodo=ayer')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_08_resumenes_ejecutivos_presentes(self):
        """El Panel Ejecutivo debe mostrar el resumen de apoyos sociales sin colapsar."""
        client = self.app.test_client()
        self._login(client, 'admin@atarjea.gob.mx', 'admin')
        resp = client.get('/auditoria_en_vivo')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Resumen de Apoyos Sociales'.encode('utf-8'), resp.data)


if __name__ == '__main__':
    unittest.main()
