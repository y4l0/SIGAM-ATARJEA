# -*- coding: utf-8 -*-
"""
tests/test_correcciones_batch_nov2026.py

BATCH DE CORRECCIONES SIGAM ATARJEA (noviembre 2026) - valida, usando el
test_client() de Flask, los siguientes puntos:

  1. Dashboard principal: el KPI de Presupuesto Ejercido consolida
     Monto General + Monto Estimado (Gran Total).
  2. Catálogo de Tipo de Beneficiario incluye "Escuela" y "Clínica".
  3. Parque Vehicular Municipal visible en Servicios Públicos y campos
     "Quién Autoriza"/"Director de Área" como texto libre.
  4. Cálculo automático de Edad a partir de la Fecha de Nacimiento.
  5. Catálogo dinámico de Tipo de Apoyo por dependencia.
  6. Etiqueta "Observaciones" sustituye a "Referencia".
  7. Ninguna gráfica de Chart.js de tipo 'pie' o 'doughnut' permanece.

Ejecutar con:
    python -m pytest tests/test_correcciones_batch_nov2026.py -v
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud, TipoBeneficiarioEnum


class TestCorreccionesBatchNov2026(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            dep = Dependencia.query.filter_by(nombre='TEST_DEP_BATCH_NOV2026').first()
            if not dep:
                dep = Dependencia(nombre='TEST_DEP_BATCH_NOV2026')
                db.session.add(dep)
                db.session.flush()

            director = Usuario.query.filter_by(email='director_batch_nov2026@test.atarjea.gob.mx').first()
            if not director:
                from werkzeug.security import generate_password_hash
                director = Usuario(
                    nombre='Director Prueba Batch', email='director_batch_nov2026@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep.id, activo=True
                )
                db.session.add(director)
                db.session.flush()

            if not Solicitud.query.filter_by(folio='TEST-BATCH-NOV2026-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-BATCH-NOV2026-0001', CURP='BNVX000101HGTAAA01',
                    Comunidad='Atarjea', Programa='Prueba Batch', Tipo_Apoyo='Alimentario',
                    Monto=1000.0, Monto_Federal=1000.0, Monto_Estimado=250.0,
                    Dependencia=dep.nombre, dependencia_id=dep.id,
                    Estatus='Aprobado', usuario_id=director.id
                ))
                db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    # ---------------- PUNTO 1: PRESUPUESTO CONSOLIDADO ----------------

    def test_01_dashboard_muestra_desglose_general_y_estimado(self):
        """El Dashboard principal debe desglosar Presupuesto General y Estimado."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('Presupuesto Ejercido (Gran Total)', html)
        self.assertIn('General:', html)
        self.assertIn('Estimado:', html)

    # ---------------- PUNTO 2: CATÁLOGO ESCUELA/CLÍNICA ----------------

    def test_02_enum_tipo_beneficiario_incluye_escuela_y_clinica(self):
        """El Enum TipoBeneficiarioEnum debe incluir Escuela y Clínica."""
        valores = [e.value for e in TipoBeneficiarioEnum]
        self.assertIn('Escuela', valores)
        self.assertIn('Clínica', valores)

    def test_03_formulario_solicitar_apoyo_incluye_escuela_y_clinica(self):
        """El formulario de Solicitud debe ofrecer Escuela y Clínica como Tipo de Beneficiario."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('<option value="Escuela">Escuela</option>', html)
        self.assertIn('Clínica', html)

    def test_04_panel_servicios_publicos_incluye_escuela_y_clinica(self):
        """El Panel de Servicios Públicos también debe ofrecer Escuela y Clínica."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertIn('Escuela', html)
        self.assertIn('Clínica', html)

    # ---------------- PUNTO 3: PARQUE VEHICULAR Y TEXTO LIBRE ----------------

    def test_05_panel_servicios_publicos_muestra_parque_vehicular(self):
        """El Parque Vehicular Municipal debe estar visible en el panel."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertIn('Parque Vehicular Municipal', html)

    def test_06_quien_autoriza_y_director_area_son_texto_libre(self):
        """Quién Autoriza y Director de Área deben ser <input> con datalist, no <select> obligatorio."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertIn('name="quien_autoriza" list="lista-quien-autoriza"', html)
        self.assertIn('name="director_area" list="lista-directores-area"', html)
        self.assertNotIn('<select class="form-select" name="quien_autoriza"', html)
        self.assertNotIn('<select class="form-select" name="director_area"', html)

    # ---------------- PUNTO 4: EDAD AUTOMÁTICA ----------------

    def test_07_formulario_incluye_script_de_calculo_de_edad(self):
        """El formulario debe incluir el script de cálculo automático de edad."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('calcularEdadDesdeFecha', html)
        self.assertIn('actualizarEdadAutomaticamente', html)

    def test_08_backend_calcula_edad_si_no_se_envia(self):
        """Si se registra una Solicitud con Fecha de Nacimiento pero sin Edad, el backend la calcula."""
        self._login('admin@atarjea.gob.mx', 'admin')
        anio_nacimiento = date.today().year - 30
        curp_prueba = 'EDAX%02d01HGTCCC03' % (anio_nacimiento % 100)
        resp = self.client.post('/solicitar_apoyo', data={
            'curp': curp_prueba, 'rfc': '', 'nombre': 'Edad', 'apellido_paterno': 'Automatica',
            'apellido_materno': 'Prueba', 'genero': 'M',
            'fecha_nacimiento': '15/06/%d' % anio_nacimiento, 'edad': '',
            'discapacidad': '0', 'comunidad': 'Atarjea', 'codigo_postal': '', 'telefono': '',
            'domicilio': '', 'referencia': '', 'programa': 'Programa Prueba Edad',
            'tipo_apoyo': 'Alimentario', 'tipo_beneficiario': 'Particular',
            'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0',
            'monto_beneficiario': '0', 'monto_estimado': '0',
            'dependencia': 'DIF Municipal', 'estatus': 'Pendiente',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            from app.models import Ciudadano
            ciudadano = Ciudadano.query.filter_by(CURP=curp_prueba).first()
            self.assertIsNotNone(ciudadano)
            self.assertIsNotNone(ciudadano.Edad)
            self.assertAlmostEqual(ciudadano.Edad, 30, delta=1)

    # ---------------- PUNTO 5: CATÁLOGO DINÁMICO POR DEPENDENCIA ----------------

    def test_09_catalogo_dinamico_tipo_apoyo_presente_en_formulario(self):
        """El JS del catálogo dinámico por dependencia debe incluir las opciones oficiales."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('Traslados', html)
        self.assertIn('Atención y seguimiento de víctimas especiales', html)
        self.assertIn('Prevención del delito', html)
        self.assertIn('Apoyo en favor del fomento del deporte', html)
        self.assertIn('Apoyo de entrega de equipo deportivo', html)
        self.assertIn('RESGUARDO CIVIL', html)
        self.assertIn('BÚSQUEDA Y RESCATE', html)
        self.assertIn('Apoyo a actividades culturales', html)
        self.assertIn('Apoyo para mejoramiento de vivienda', html)
        self.assertIn('Apoyo para instituciones', html)

    def test_10_editar_solicitud_respeta_catalogo_de_su_dependencia(self):
        """Editar Solicitud debe ofrecer el catálogo correspondiente a la Dependencia guardada."""
        self._login('admin@atarjea.gob.mx', 'admin')
        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(folio='TEST-BATCH-NOV2026-0002').first()
            if not solicitud:
                solicitud = Solicitud(
                    folio='TEST-BATCH-NOV2026-0002', CURP='BNVX000101HGTDDD04',
                    Comunidad='Atarjea', Programa='Prueba Protección Civil',
                    Tipo_Apoyo='RESGUARDO CIVIL', Monto=0.0,
                    Dependencia='Protección Civil', Estatus='Pendiente',
                )
                db.session.add(solicitud)
                db.session.commit()
            solicitud_id = solicitud.id
        resp = self.client.get(f'/solicitud/{solicitud_id}/editar')
        html = resp.data.decode('utf-8')
        self.assertIn('RESGUARDO CIVIL', html)
        self.assertIn('ACCESO A VIALIDADES', html)

    # ---------------- PUNTO 6: OBSERVACIONES ----------------

    def test_11_label_observaciones_sustituye_a_referencia(self):
        """El formulario de Solicitud debe mostrar la etiqueta 'Observaciones' en vez de 'Referencia'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('<label class="form-label">Observaciones</label>', html)
        # El campo de backend/DB se mantiene como "referencia" (compatibilidad).
        self.assertIn('name="referencia"', html)

    # ---------------- PUNTO 7: SIN GRÁFICAS DE PASTEL/DONA ----------------

    def test_12_dashboard_no_usa_graficas_de_pastel_ni_dona(self):
        """El Dashboard principal no debe contener ninguna gráfica 'pie' o 'doughnut'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/dashboard')
        html = resp.data.decode('utf-8')
        self.assertNotIn("type: 'pie'", html)
        self.assertNotIn("type: 'doughnut'", html)

    def test_13_servicios_publicos_no_usa_graficas_de_pastel_ni_dona(self):
        """El Panel de Servicios Públicos no debe contener ninguna gráfica 'pie' o 'doughnut'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertNotIn("type: 'pie'", html)
        self.assertNotIn("type: 'doughnut'", html)

    def test_14_centro_control_ejecutivo_no_usa_graficas_de_pastel_ni_dona(self):
        """El Centro de Control Ejecutivo no debe contener ninguna gráfica 'pie' o 'doughnut'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        html = resp.data.decode('utf-8')
        self.assertNotIn("type: 'pie'", html)
        self.assertNotIn("type: 'doughnut'", html)


if __name__ == '__main__':
    unittest.main()
