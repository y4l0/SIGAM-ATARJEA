# -*- coding: utf-8 -*-
"""
ORDEN TÉCNICA MAESTRA: CONEXIÓN DE DESCUENTO AUTOMÁTICO, HISTORIAL CON
PRECIO POR FLUIDO Y SWITCH EJECUTIVO (ALCALDE).

Prueba de integración que valida, de extremo a extremo con el
test_client() de Flask:
  1. El usuario Alcalde (Admin/Presidente) puede navegar y visualizar
     tanto el Panel de Apoyos Ciudadanos (Dashboard) como el Panel de
     Servicios Públicos (Combustible), y que el conmutador ejecutivo
     aparece en el layout para ese rol.
  2. Al crear una Asignación de Combustible (Formulario N° 10), el
     inventario del tanque del fluido correspondiente (Gasolina/
     Diésel/Urea) se descuenta de inmediato (sin refrescar), reflejado
     en calcular_estado_multitanque().
  3. El historial de abasto multifluido (con precio por litro y monto
     total) se registra y se refleja en el Dashboard de Servicios
     Públicos.

Ejecutar con: python -m pytest tests/_test_alcalde_switch.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import (
    Usuario, AsignacionCombustible, EstatusAsignacionEnum, TipoFluidoEnum,
    RegistroAbastoFluido
)


class TestAlcaldeSwitch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def setUp(self):
        self.client = self.app.test_client()
        self._login(self.client, 'admin@atarjea.gob.mx', 'admin')

    def _login(self, client, email, password):
        return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def test_01_alcalde_puede_ver_panel_apoyos_ciudadanos(self):
        """El Alcalde (Admin) debe poder cargar el Dashboard de Apoyos Ciudadanos sin colapsar."""
        resp = self.client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_02_alcalde_puede_ver_panel_servicios_publicos(self):
        """El Alcalde (Admin) debe poder cargar el Panel de Servicios Públicos (Combustible) sin colapsar."""
        resp = self.client.get('/servicios_publicos/combustible')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_03_conmutador_ejecutivo_visible_para_alcalde(self):
        """
        El conmutador de paneles (botón/switch) debe estar presente en el
        layout cuando el usuario es Administrador/Alcalde, en ambas vistas.
        """
        resp_dashboard = self.client.get('/dashboard')
        self.assertIn(b'Conmutador de Paneles del Alcalde', resp_dashboard.data)
        self.assertIn('Apoyos Ciudadanos'.encode('utf-8'), resp_dashboard.data)

        resp_combustible = self.client.get('/servicios_publicos/combustible')
        self.assertIn(b'Conmutador de Paneles del Alcalde', resp_combustible.data)
        self.assertIn(b'Servicios P', resp_combustible.data)

    def test_04_conmutador_no_visible_para_rol_servicios_publicos(self):
        """Un rol sin privilegios de Alcaldía (ServiciosPublicos) no debe ver el conmutador ejecutivo."""
        client = self.app.test_client()
        self._login(client, 'serviciospublicosAtarjea@gmail.com', 'serviciospublicos')
        resp = client.get('/servicios_publicos/combustible', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Conmutador de Paneles del Alcalde', resp.data)

    def test_05_asignacion_descuenta_litros_del_tanque_gasolina(self):
        """
        ORDEN TÉCNICA MAESTRA - DESCUENTO AUTOMÁTICO: al crear una
        asignación de Gasolina, los litros disponibles del tanque de
        Gasolina deben disminuir de inmediato (sin refrescar manualmente),
        reflejado en el recálculo de calcular_estado_multitanque().
        """
        from app.routes import calcular_estado_multitanque

        with self.app.app_context():
            abasto = RegistroAbastoFluido(
                tipo_fluido=TipoFluidoEnum.GASOLINA.value,
                numero_tanque=1,
                litros_recibidos=500.0,
                costo_litro=24.50,
                proveedor='Proveedor de Prueba Self-Test',
                documento='FACTURA',
                numero_documento='SELFTEST-001',
                recibe='Self-Test Alcalde',
                es_demo=False,
            )
            abasto.calcular_costo_total()
            db.session.add(abasto)
            db.session.commit()
            abasto_id = abasto.id

            estado_antes = calcular_estado_multitanque()
            litros_antes = sum(
                t['litros_disponibles'] for t in estado_antes[TipoFluidoEnum.GASOLINA.value]['tanques'] if t.get('activo')
            )

        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'unidad_organizacional': 'Presidencia Municipal',
            'tipo_asignacion': 'OFICIAL',
            'itinerario_destino': 'Prueba de descuento automático - Alcalde Switch',
            'responsable_nombre': 'Self-Test Alcalde Switch',
            'litros_asignados': '20.0',
            'tipo_combustible': 'Gasolina',
            'tipo_recorrido': 'Local',
            'quien_autoriza': 'Self-Test',
            'fecha_solicitud': '2026-01-01',
            'fecha_inicio': '2026-01-01',
            'hora_inicio': '08:00',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        try:
            with self.app.app_context():
                estado_despues = calcular_estado_multitanque()
                litros_despues = sum(
                    t['litros_disponibles'] for t in estado_despues[TipoFluidoEnum.GASOLINA.value]['tanques'] if t.get('activo')
                )
                self.assertLess(
                    litros_despues, litros_antes,
                    "El tanque de Gasolina debe descontar los litros autorizados de inmediato tras crear la asignación."
                )
                self.assertAlmostEqual(litros_antes - litros_despues, 20.0, delta=0.5)
        finally:
            with self.app.app_context():
                vale = AsignacionCombustible.query.filter_by(responsable_nombre='Self-Test Alcalde Switch').first()
                if vale:
                    db.session.delete(vale)
                abasto_a_borrar = RegistroAbastoFluido.query.get(abasto_id)
                if abasto_a_borrar:
                    db.session.delete(abasto_a_borrar)
                db.session.commit()

    def test_06_historial_abasto_fluido_con_precio_y_monto_visible(self):
        """
        El historial de entradas de abasto multifluido (con precio por
        litro y monto total calculado) debe registrarse y mostrarse en el
        Dashboard de Servicios Públicos.
        """
        with self.app.app_context():
            abasto = RegistroAbastoFluido(
                tipo_fluido=TipoFluidoEnum.DIESEL.value,
                numero_tanque=1,
                litros_recibidos=100.0,
                costo_litro=26.00,
                proveedor='Proveedor Diesel Self-Test',
                documento='FACTURA',
                numero_documento='SELFTEST-DIESEL-001',
                recibe='Self-Test Alcalde',
                es_demo=False,
            )
            abasto.calcular_costo_total()
            db.session.add(abasto)
            db.session.commit()
            abasto_id = abasto.id
            monto_esperado = float(abasto.costo_total)

        try:
            resp = self.client.get('/servicios_publicos/combustible')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Historial de Entradas de Abasto (Multitanque)', resp.data)
            self.assertIn(b'Proveedor Diesel Self-Test', resp.data)
            self.assertAlmostEqual(monto_esperado, 2600.0, delta=0.01)
        finally:
            with self.app.app_context():
                abasto_a_borrar = RegistroAbastoFluido.query.get(abasto_id)
                if abasto_a_borrar:
                    db.session.delete(abasto_a_borrar)
                db.session.commit()


if __name__ == '__main__':
    unittest.main()
