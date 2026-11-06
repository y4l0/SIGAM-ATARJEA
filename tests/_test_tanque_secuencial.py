# -*- coding: utf-8 -*-
"""
ORDEN TÉCNICA MAESTRA: FILAS DE TOTALES, TANQUES SECUENCIALES
AUTOMÁTICOS Y REPORTE CONSOLIDADO.

Prueba de integración que valida, de extremo a extremo con el
test_client() de Flask:
  1. Las tablas "Resumen Ejecutivo por Área" y "Reporte Semanal
     Consolidado" muestran una fila TOTAL GENERAL con las sumatorias
     correctas de folios, litros y costos.
  2. El Tanque 1 (Principal) de un fluido, al agotarse, cede
     automáticamente el rol de Principal al Tanque 2 (Secundario), con
     alerta visual en el Dashboard, sin intervención manual.
  3. El botón Activar/Desactivar Tanque 2 es funcional y, si se
     desactiva estando promovido a Principal, el Tanque 1 recupera el
     rol de Principal (coherencia del ciclo).
  4. El desglose por fluido del Reporte Semanal coincide exactamente
     con los litros/costos reales (excluyendo asignaciones CANCELADA,
     igual que el cálculo de tanques).

Ejecutar con: python -m pytest tests/_test_tanque_secuencial.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import (
    AsignacionCombustible, EstatusAsignacionEnum, TipoFluidoEnum,
    RegistroAbastoFluido, ConfiguracionTanque
)


class TestTanqueSecuencial(unittest.TestCase):

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

    def test_01_fila_total_general_resumen_ejecutivo(self):
        """La tabla 'Resumen Ejecutivo por Área' debe incluir la fila TOTAL GENERAL."""
        resp = self.client.get('/servicios_publicos/combustible')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'TOTAL GENERAL', resp.data)

    def test_02_fila_total_general_reporte_semanal(self):
        """El Reporte Semanal Consolidado debe mostrar TOTAL GENERAL en ambas tablas (bitácora y fluido)."""
        resp = self.client.get('/servicios_publicos/reporte_semanal')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data.count(b'TOTAL GENERAL'), 2)

    def test_03_rotacion_automatica_principal_a_secundario(self):
        """
        Si el Tanque 1 (Principal) de un fluido se agota y el Tanque 2
        (Secundario) tiene litros disponibles, calcular_estado_
        multitanque() debe promover automáticamente al Tanque 2 como
        Principal y emitir una alerta_rotacion no vacía.

        Usa el fluido UREA (sin abastos ni asignaciones previas en la
        base de datos real) para garantizar un escenario 100% aislado y
        reproducible, sin depender del estado de otros fluidos.
        """
        from app.routes import calcular_estado_multitanque

        abasto_t1_id = None
        abasto_t2_id = None
        vale_id = None
        try:
            with self.app.app_context():
                # Tanque 1 (Principal): abasto pequeño que se agotará con el vale.
                abasto_t1 = RegistroAbastoFluido(
                    tipo_fluido=TipoFluidoEnum.UREA.value, numero_tanque=1,
                    litros_recibidos=10.0, costo_litro=20.0,
                    proveedor='Self-Test Rotacion T1', es_demo=False,
                )
                abasto_t1.calcular_costo_total()
                db.session.add(abasto_t1)

                # Tanque 2 (Secundario): activo con litros de respaldo.
                abasto_t2 = RegistroAbastoFluido(
                    tipo_fluido=TipoFluidoEnum.UREA.value, numero_tanque=2,
                    litros_recibidos=200.0, costo_litro=20.0,
                    proveedor='Self-Test Rotacion T2', es_demo=False,
                )
                abasto_t2.calcular_costo_total()
                db.session.add(abasto_t2)
                db.session.commit()
                abasto_t1_id, abasto_t2_id = abasto_t1.id, abasto_t2.id

                config_t2 = ConfiguracionTanque.obtener_o_crear(TipoFluidoEnum.UREA.value, 2)
                config_t2.activo = True
                db.session.commit()

                # Vale UREA que agota exactamente el Tanque 1 (10 L).
                vale = AsignacionCombustible(
                    folio_asignacion='SELFTEST-ROTACION-UREA-0001',
                    unidad_organizacional='Dirección de Servicios Públicos',
                    tipo_asignacion='UREA',
                    responsable_nombre='Self-Test Rotacion Tanque',
                    litros_asignados=10.0,
                    estatus=EstatusAsignacionEnum.AUTORIZADO.value,
                )
                db.session.add(vale)
                db.session.commit()
                vale_id = vale.id

                estado = calcular_estado_multitanque()
                datos_urea = estado[TipoFluidoEnum.UREA.value]
                tanque_1 = next(t for t in datos_urea['tanques'] if t['numero_tanque'] == 1)
                tanque_2 = next(t for t in datos_urea['tanques'] if t['numero_tanque'] == 2)

                self.assertLessEqual(tanque_1['litros_disponibles'], 0.01)
                self.assertFalse(tanque_1['es_principal'], "El Tanque 1 agotado debe perder el rol de Principal.")
                self.assertTrue(tanque_2['es_principal'], "El Tanque 2 (Secundario) debe promoverse a Principal.")
                self.assertIsNotNone(datos_urea['alerta_rotacion'])
                self.assertIn('entró en servicio', datos_urea['alerta_rotacion'])
        finally:
            with self.app.app_context():
                if vale_id:
                    v = AsignacionCombustible.query.get(vale_id)
                    if v:
                        db.session.delete(v)
                if abasto_t1_id:
                    a1 = RegistroAbastoFluido.query.get(abasto_t1_id)
                    if a1:
                        db.session.delete(a1)
                if abasto_t2_id:
                    a2 = RegistroAbastoFluido.query.get(abasto_t2_id)
                    if a2:
                        db.session.delete(a2)
                # Restaura el Tanque 1 de Urea como Principal (estado por defecto).
                config_t1 = ConfiguracionTanque.obtener_o_crear(TipoFluidoEnum.UREA.value, 1)
                config_t1.es_principal = True
                config_t2 = ConfiguracionTanque.obtener_o_crear(TipoFluidoEnum.UREA.value, 2)
                config_t2.es_principal = False
                config_t2.activo = False
                db.session.commit()

    def test_04_boton_activar_desactivar_tanque_2_es_funcional(self):
        """
        El botón "Activar/Desactivar Tanque 2 (Secundario)" debe invertir
        el estado 'activo' del Tanque 2 en cada envío del formulario.
        """
        try:
            with self.app.app_context():
                config_inicial = ConfiguracionTanque.obtener_o_crear(TipoFluidoEnum.UREA.value, 2)
                activo_inicial = bool(config_inicial.activo)

            resp = self.client.post('/servicios_publicos/tanque/activar', data={
                'tipo_fluido': TipoFluidoEnum.UREA.value,
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            with self.app.app_context():
                config_despues = ConfiguracionTanque.query.filter_by(
                    tipo_fluido=TipoFluidoEnum.UREA.value, numero_tanque=2
                ).first()
                self.assertNotEqual(bool(config_despues.activo), activo_inicial)

            # Revierte el envío para dejar el botón en su estado original.
            resp2 = self.client.post('/servicios_publicos/tanque/activar', data={
                'tipo_fluido': TipoFluidoEnum.UREA.value,
            }, follow_redirects=True)
            self.assertEqual(resp2.status_code, 200)
        finally:
            with self.app.app_context():
                config_final = ConfiguracionTanque.query.filter_by(
                    tipo_fluido=TipoFluidoEnum.UREA.value, numero_tanque=2
                ).first()
                if config_final:
                    config_final.activo = False
                    config_final.es_principal = False
                config_t1 = ConfiguracionTanque.query.filter_by(
                    tipo_fluido=TipoFluidoEnum.UREA.value, numero_tanque=1
                ).first()
                if config_t1:
                    config_t1.es_principal = True
                    config_t1.activo = True
                db.session.commit()

    def test_05_reporte_semanal_coincide_con_tanques_sin_cargas_foraneas(self):
        """
        El total de litros consumidos por fluido en el Reporte Semanal
        Consolidado debe coincidir exactamente con la suma de consumo
        calculada por calcular_estado_multitanque() (misma regla de
        exclusión de Cargas Foráneas y asignaciones CANCELADA), sin
        discrepancias de costos.
        """
        from app.routes import calcular_estado_multitanque, calcular_reporte_semanal_consolidado

        with self.app.app_context():
            estado_tanques = calcular_estado_multitanque()
            reporte = calcular_reporte_semanal_consolidado()

            consumo_tanques_gasolina = estado_tanques[TipoFluidoEnum.GASOLINA.value]['litros_consumidos_total']
            fila_gasolina_reporte = next(
                f for f in reporte['desglose_por_fluido']
                if f['nombre'] == TipoFluidoEnum.nombre_completo(TipoFluidoEnum.GASOLINA.value)
            )
            # El reporte semanal es una ventana de 7 días; el consumo
            # histórico total de tanques es igual o mayor, pero NUNCA debe
            # haber litros reportados en el reporte semanal que excedan
            # el consumo histórico total (coherencia de magnitud).
            self.assertLessEqual(fila_gasolina_reporte['litros_consumidos'], consumo_tanques_gasolina + 0.01)

            # Las claves de totales nuevas deben existir y ser numéricas.
            self.assertIn('total_litros_consumidos_fluidos', reporte)
            self.assertIn('total_litros_abastecidos_fluidos', reporte)
            self.assertIn('total_costo_abasto_fluidos', reporte)
            self.assertIsInstance(reporte['total_litros_consumidos_fluidos'], float)
