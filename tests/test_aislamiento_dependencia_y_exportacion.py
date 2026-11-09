# -*- coding: utf-8 -*-
"""
CORRECCIÓN CRÍTICA DE PRODUCCIÓN: AISLAMIENTO ESTRICTO POR DEPENDENCIA Y
SINCRONIZACIÓN DE EXPORTACIÓN/MÉTRICAS CON LA BASE DE DATOS REAL.

Este módulo valida, usando el test_client() de Flask, las dos fallas
críticas detectadas en producción:

  1. AISLAMIENTO ESTRICTO POR DEPENDENCIA: un Director (rol distinto de
     Admin/Presidente) jamás debe poder ver, consultar o exportar
     registros de otra dependencia a través de /ciudadano/<curp>,
     /buscar_curp/<curp> o /exportar_excel.

  2. SINCRONIZACIÓN DE EXCEL/MÉTRICAS: el Presidente Municipal (rol
     "Presidente", dependencia_id=None) debe ver y exportar EXACTAMENTE
     los mismos registros que existen en la base de datos real, sin que
     el filtro por dependencia_id=None (NULL) descarte accidentalmente
     todos los resultados (hueco causado por usar es_admin() en vez de
     tiene_vision_total() como criterio de visión ejecutiva total).

Ejecutar con:
    python -m pytest tests/test_aislamiento_dependencia_y_exportacion.py -v
"""
import io
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud, Ciudadano
from werkzeug.security import generate_password_hash


class TestAislamientoDependenciaYExportacion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            dep_x = Dependencia.query.filter_by(nombre='TEST_DEP_EXPORT_X').first()
            if not dep_x:
                dep_x = Dependencia(nombre='TEST_DEP_EXPORT_X')
                db.session.add(dep_x)
                db.session.flush()

            dep_y = Dependencia.query.filter_by(nombre='TEST_DEP_EXPORT_Y').first()
            if not dep_y:
                dep_y = Dependencia(nombre='TEST_DEP_EXPORT_Y')
                db.session.add(dep_y)
                db.session.flush()

            director_x = Usuario.query.filter_by(email='director_x@test.atarjea.gob.mx').first()
            if not director_x:
                director_x = Usuario(
                    nombre='Director Prueba X', email='director_x@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep_x.id, activo=True
                )
                db.session.add(director_x)
                db.session.flush()

            director_y = Usuario.query.filter_by(email='director_y@test.atarjea.gob.mx').first()
            if not director_y:
                director_y = Usuario(
                    nombre='Director Prueba Y', email='director_y@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep_y.id, activo=True
                )
                db.session.add(director_y)
                db.session.flush()

            if not Ciudadano.query.get('EXPX000101HGTXXX01'):
                db.session.add(Ciudadano(
                    CURP='EXPX000101HGTXXX01', Nombre='Export', Apellido_Paterno='Prueba',
                    Apellido_Materno='X', Fecha_Nacimiento=date(2000, 1, 1)
                ))

            if not Solicitud.query.filter_by(folio='TEST-EXPORT-X-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-EXPORT-X-0001', CURP='EXPX000101HGTXXX01',
                    Comunidad='Atarjea', Programa='Programa X', Tipo_Apoyo='Alimentario',
                    Monto=1234.56, Dependencia=dep_x.nombre, dependencia_id=dep_x.id,
                    Estatus='Aprobado', usuario_id=director_x.id
                ))
            if not Solicitud.query.filter_by(folio='TEST-EXPORT-Y-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-EXPORT-Y-0001', CURP='EXPY000101HGTYYY02',
                    Comunidad='Atarjea', Programa='Programa Y', Tipo_Apoyo='Educativo',
                    Monto=777.00, Dependencia=dep_y.nombre, dependencia_id=dep_y.id,
                    Estatus='Aprobado', usuario_id=director_y.id
                ))
            db.session.commit()

            cls.dep_x_id = dep_x.id
            cls.dep_y_id = dep_y.id

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    # ---------------- FALLA 1: AISLAMIENTO ESTRICTO POR DEPENDENCIA ----------------

    def test_01_director_no_ve_detalle_de_otra_dependencia_en_ver_ciudadano(self):
        """/ciudadano/<curp> no debe exponer el folio/programa de otra dependencia a un Director."""
        self._login('director_y@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/ciudadano/EXPX000101HGTXXX01')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'TEST-EXPORT-X-0001', resp.data)
        self.assertNotIn(b'Programa X', resp.data)

    def test_02_director_no_ve_detalle_de_otra_dependencia_en_buscar_curp(self):
        """/buscar_curp/<curp> (AJAX) no debe exponer folio/monto/programa de otra dependencia."""
        self._login('director_y@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/buscar_curp/EXPX000101HGTXXX01')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['existe'])
        self.assertEqual(data['historial'], [])
        self.assertEqual(data.get('total_otras_dependencias'), 1)
        self.assertNotIn('TEST-EXPORT-X-0001', str(data))
        self.assertNotIn('Programa X', str(data))

    def test_03_director_exporta_excel_y_solo_obtiene_sus_propios_registros(self):
        """/exportar_excel debe limitarse estrictamente a la dependencia del Director."""
        self._login('director_x@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/exportar_excel?fecha_inicio=2020-01-01&fecha_fin=2030-01-01')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        contenido = []
        for row in ws.iter_rows(values_only=True):
            contenido.extend([str(c) for c in row if c is not None])
        texto_completo = ' '.join(contenido)

        self.assertIn('EXPX000101HGTXXX01', texto_completo)
        self.assertNotIn('EXPY000101HGTYYY02', texto_completo)

    # ---------------- FALLA 2: SINCRONIZACIÓN EXCEL/MÉTRICAS CON BD REAL ----------------

    def test_04_presidente_tiene_vision_total_pese_a_dependencia_id_nulo(self):
        """El modelo Usuario debe exponer tiene_vision_total() para Admin y Presidente."""
        with self.app.app_context():
            presidente = Usuario.query.filter_by(email='presidente@atarjea.gob.mx').first()
            self.assertIsNotNone(presidente)
            self.assertIsNone(presidente.dependencia_id)
            self.assertTrue(presidente.tiene_vision_total())

            director_x = Usuario.query.filter_by(email='director_x@test.atarjea.gob.mx').first()
            self.assertFalse(director_x.tiene_vision_total())

    def test_05_presidente_exportacion_coincide_exactamente_con_bd_real(self):
        """
        CORRECCIÓN CRÍTICA: el Presidente debe exportar EXACTAMENTE el
        mismo número de solicitudes que existen en la base de datos para
        el rango de fechas solicitado (antes devolvía 0 por el filtro
        erróneo dependencia_id=None, que nunca coincide con ningún dato real).
        """
        with self.app.app_context():
            total_real = Solicitud.query.filter(
                Solicitud.Fecha_Solicitud.between('2020-01-01', '2030-01-01')
            ).count()
        self.assertGreater(total_real, 0, 'El escenario de prueba debe tener datos reales en la BD.')

        self._login('presidente@atarjea.gob.mx', 'Presidente2026')
        resp = self.client.get('/exportar_excel?fecha_inicio=2020-01-01&fecha_fin=2030-01-01')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        filas_de_datos = ws.max_row - 2  # se descuenta encabezado y fila de TOTAL
        self.assertEqual(filas_de_datos, total_real)

    def test_06_presidente_ve_detalle_completo_en_buscar_curp_y_ver_ciudadano(self):
        """El Presidente (visión total) sí debe ver el detalle de cualquier dependencia."""
        self._login('presidente@atarjea.gob.mx', 'Presidente2026')

        resp = self.client.get('/buscar_curp/EXPX000101HGTXXX01')
        data = resp.get_json()
        self.assertTrue(data['existe'])
        self.assertEqual(len(data['historial']), 1)
        self.assertEqual(data['historial'][0]['folio'], 'TEST-EXPORT-X-0001')

        resp2 = self.client.get('/ciudadano/EXPX000101HGTXXX01')
        self.assertEqual(resp2.status_code, 200)
        # ciudadano.html no renderiza el folio, pero sí el nombre del
        # Programa de la solicitud; se usa como evidencia de que el
        # Presidente SÍ ve el detalle completo (a diferencia del Director).
        self.assertIn(b'Programa X', resp2.data)

    def test_07_historial_auditoria_presidente_no_queda_vacio(self):
        """/historial_auditoria debe reflejar solicitudes reales para el Presidente."""
        self._login('presidente@atarjea.gob.mx', 'Presidente2026')
        resp = self.client.get('/historial_auditoria')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Programa X', resp.data)


if __name__ == '__main__':
    unittest.main()
