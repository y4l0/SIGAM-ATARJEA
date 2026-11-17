# -*- coding: utf-8 -*-
"""
tests/test_centro_control_ejecutivo.py

REDISEÑO DEL CENTRO DE CONTROL EJECUTIVO (PANEL ADMIN/ALCALDE) -
SIGAM Atarjea.

Valida, usando el test_client() de Flask, el nuevo formato de
supervisión ejecutiva tipo tarjetas/cuadrícula en /auditoria_en_vivo:

  1. KPIs ejecutivos de un vistazo: solicitudes totales, Aprobadas,
     Pendientes, Rechazadas y Otorgadas, con montos Generales y
     Estimados desglosados, para TODAS las dependencias.
  2. Filtro dinámico por rango de fechas personalizado (Desde/Hasta) y
     accesos rápidos (Hoy, Esta Semana, Este Mes, Histórico).
  3. Extensión del formato de resumen estructurado (estilo Servicios
     Públicos) a todas las áreas: cada dependencia con actividad real
     se muestra como tarjeta con botón de "Ver Resumen Detallado".
  4. Detección visual de errores/desviaciones (alertas) sin bloquear
     ni ocultar información, y limpieza de "datos fantasma" (áreas sin
     actividad en el período no se listan).

Ejecutar con:
    python -m pytest tests/test_centro_control_ejecutivo.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud
from app.routes import _evaluar_alertas_area
from werkzeug.security import generate_password_hash


class TestCentroControlEjecutivo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            dep = Dependencia.query.filter_by(nombre='TEST_DEP_CCE').first()
            if not dep:
                dep = Dependencia(nombre='TEST_DEP_CCE')
                db.session.add(dep)
                db.session.flush()

            director = Usuario.query.filter_by(email='director_cce@test.atarjea.gob.mx').first()
            if not director:
                director = Usuario(
                    nombre='Director Prueba CCE', email='director_cce@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep.id, activo=True
                )
                db.session.add(director)
                db.session.flush()

            if not Solicitud.query.filter_by(folio='TEST-CCE-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-CCE-0001', CURP='CCEX000101HGTAAA01',
                    Comunidad='Atarjea', Programa='Prueba CCE', Tipo_Apoyo='Alimentario',
                    Monto=500.0, Monto_Federal=500.0, Monto_Estimado=100.0,
                    Dependencia=dep.nombre, dependencia_id=dep.id,
                    Estatus='Aprobado', usuario_id=director.id
                ))
            if not Solicitud.query.filter_by(folio='TEST-CCE-0002').first():
                db.session.add(Solicitud(
                    folio='TEST-CCE-0002', CURP='CCEX000101HGTBBB02',
                    Comunidad='Atarjea', Programa='Prueba CCE', Tipo_Apoyo='Educativo',
                    Monto=300.0, Monto_Federal=300.0,
                    Dependencia=dep.nombre, dependencia_id=dep.id,
                    Estatus='Otorgado', usuario_id=director.id
                ))
            db.session.commit()
            cls.dep_id = dep.id

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    # ---------------- REQUERIMIENTO 1: KPIs EJECUTIVOS DE UN VISTAZO ----------------

    def test_01_panel_muestra_titulo_centro_de_control_ejecutivo(self):
        """El panel debe mostrar el nuevo título 'Centro de Control Ejecutivo'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Centro de Control Ejecutivo'.encode('utf-8'), resp.data)

    def test_02_kpis_ejecutivos_incluyen_los_5_estatus(self):
        """El panel debe mostrar los 5 KPIs: Totales, Aprobadas, Pendientes, Rechazadas, Otorgadas."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        for etiqueta in ['Solicitudes Totales', 'Aprobadas', 'Pendientes', 'Rechazadas', 'Otorgadas']:
            self.assertIn(etiqueta, html)

    def test_03_kpis_muestran_montos_generales_y_estimados(self):
        """El resumen ejecutivo debe desglosar Monto General y Monto Estimado por separado."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        html = resp.data.decode('utf-8')
        self.assertIn('Monto General', html)
        self.assertIn('Monto Estimado', html)

    # ---------------- REQUERIMIENTO 2: FILTRO DINÁMICO DE FECHAS ----------------

    def test_04_accesos_rapidos_de_fecha_presentes(self):
        """Deben existir los accesos directos Hoy/Esta Semana/Este Mes/Histórico."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo')
        html = resp.data.decode('utf-8')
        for etiqueta in ['Hoy', 'Esta Semana', 'Este Mes', 'Histórico', 'Rango Personalizado']:
            self.assertIn(etiqueta, html)

    def test_05_filtro_rango_personalizado_hasta_hoy_no_colapsa(self):
        """El rango personalizado debe aceptar evaluar cualquier fecha hasta la fecha actual."""
        from datetime import datetime
        hoy_iso = datetime.utcnow().strftime('%Y-%m-%d')
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get(f'/auditoria_en_vivo?periodo=personalizado&fecha_inicio=2026-01-01&fecha_fin={hoy_iso}')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_06_filtros_hoy_semana_mes_no_colapsan(self):
        """Los accesos rápidos Hoy/Esta Semana/Este Mes deben responder 200 sin colapsar."""
        self._login('admin@atarjea.gob.mx', 'admin')
        for periodo in ['hoy', 'semana', 'mes', 'todo']:
            resp = self.client.get(f'/auditoria_en_vivo?periodo={periodo}')
            self.assertEqual(resp.status_code, 200, f"El filtro '{periodo}' debe responder 200.")
            self.assertNotIn(b'Internal Server Error', resp.data)

    # ---------------- REQUERIMIENTO 3: EXTENSIÓN DEL FORMATO A TODAS LAS ÁREAS ----------------

    def test_07_tarjeta_de_area_muestra_desglose_estructurado(self):
        """La dependencia de prueba con actividad real debe aparecer como tarjeta con su desglose completo."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        html = resp.data.decode('utf-8')
        self.assertIn('TEST_DEP_CCE', html)
        self.assertIn('Ver Resumen Detallado', html)

    def test_08_boton_ver_resumen_detallado_accesible_para_admin(self):
        """El botón 'Ver Resumen Detallado' debe estar visible para el Admin/Alcalde."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        self.assertIn(b'modalResumenArea', resp.data)

    def test_09_areas_sin_actividad_no_aparecen_datos_fantasma(self):
        """Una dependencia recién creada SIN solicitudes no debe aparecer en la cuadrícula de tarjetas."""
        with self.app.app_context():
            dep_fantasma = Dependencia.query.filter_by(nombre='TEST_DEP_FANTASMA_CCE').first()
            if not dep_fantasma:
                dep_fantasma = Dependencia(nombre='TEST_DEP_FANTASMA_CCE')
                db.session.add(dep_fantasma)
                db.session.commit()

        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/auditoria_en_vivo?periodo=todo')
        self.assertNotIn(b'TEST_DEP_FANTASMA_CCE', resp.data)

    # ---------------- REQUERIMIENTO 4: DETECCIÓN VISUAL DE ERRORES/DESVIACIONES ----------------

    def test_10_alerta_monto_estimado_mayor_al_general(self):
        """La función pura de alertas debe detectar cuando el Monto Estimado supera al Monto General."""
        datos = {'total': 5, 'pendientes': 0, 'rechazadas': 0, 'monto_general': 100.0, 'monto_estimado': 500.0}
        alertas = _evaluar_alertas_area(datos)
        self.assertTrue(any('Monto Estimado supera' in a['mensaje'] for a in alertas))

    def test_11_alerta_alta_tasa_de_rechazo(self):
        """La función pura de alertas debe detectar una alta tasa de rechazo (>=30%)."""
        datos = {'total': 10, 'pendientes': 0, 'rechazadas': 5, 'monto_general': 1000.0, 'monto_estimado': 0.0}
        alertas = _evaluar_alertas_area(datos)
        self.assertTrue(any(a['color'] == 'danger' for a in alertas))

    def test_12_alerta_rezago_operativo_por_pendientes(self):
        """La función pura de alertas debe detectar rezago operativo cuando >=50% está pendiente."""
        datos = {'total': 6, 'pendientes': 4, 'rechazadas': 0, 'monto_general': 100.0, 'monto_estimado': 0.0}
        alertas = _evaluar_alertas_area(datos)
        self.assertTrue(any('Rezago operativo' in a['mensaje'] for a in alertas))

    def test_13_sin_alertas_cuando_todo_esta_en_orden(self):
        """Un área sin anomalías no debe generar ninguna alerta."""
        datos = {'total': 10, 'pendientes': 1, 'rechazadas': 1, 'monto_general': 1000.0, 'monto_estimado': 50.0}
        alertas = _evaluar_alertas_area(datos)
        self.assertEqual(alertas, [])

    def test_14_area_sin_actividad_nunca_lanza_excepcion(self):
        """Un área con total=0 (sin actividad) nunca debe generar alertas ni fallar."""
        alertas = _evaluar_alertas_area({'total': 0, 'pendientes': 0, 'rechazadas': 0, 'monto_general': 0, 'monto_estimado': 0})
        self.assertEqual(alertas, [])

    # ---------------- INTEGRIDAD GENERAL Y PRESERVACIÓN DE DATOS ----------------

    def test_15_director_no_puede_acceder_al_centro_de_control_ejecutivo(self):
        """Un Director no debe tener acceso al Centro de Control Ejecutivo."""
        self._login('director_cce@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/auditoria_en_vivo', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Avance de Apoyos por Área'.encode('utf-8'), resp.data)

    def test_16_renderizado_no_altera_el_total_de_solicitudes_reales(self):
        """Consultar el panel repetidamente NUNCA debe alterar el número real de solicitudes en la BD."""
        with self.app.app_context():
            total_antes = Solicitud.query.count()

        self._login('admin@atarjea.gob.mx', 'admin')
        self.client.get('/auditoria_en_vivo?periodo=todo')
        self.client.get('/auditoria_en_vivo?periodo=mes')

        with self.app.app_context():
            total_despues = Solicitud.query.count()
        self.assertEqual(total_antes, total_despues)


if __name__ == '__main__':
    unittest.main()
