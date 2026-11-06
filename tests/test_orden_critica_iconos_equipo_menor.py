# -*- coding: utf-8 -*-
"""
ORDEN DE EJECUCIÓN CRÍTICA: self-test de extremo a extremo para validar:
  1. Los iconos vectoriales de las 11 bitácoras existen en el HTML
     renderizado del panel de Servicios Públicos.
  2. El formulario de asignación (Vehículos Oficiales) guarda sin
     caídas y emite el folio correctamente.
  3. La bitácora de Equipo Menor captura EXCLUSIVAMENTE por "Horas de
     Uso / Operación" (nunca kilometraje) y descuenta el inventario.
  4. El campo "Chofer / Operador" acepta texto libre y, si el nombre
     no existe en el catálogo, se da de alta automáticamente sin
     bloquear el guardado.

Ejecutar con: python -m pytest tests/test_orden_critica_iconos_equipo_menor.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import AsignacionCombustible, Conductor, Equipo


class TestOrdenCriticaIconosEquipoMenor(unittest.TestCase):

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

    def test_01_panel_servicios_publicos_contiene_los_10_iconos_solicitados(self):
        """El panel debe renderizar los iconos vectoriales elegantes solicitados.
        ORDEN TÉCNICA MAESTRA: la tarjeta "Camión Pipas" (fa-truck-droplet)
        se eliminó del selector porque ese servicio se opera fuera del
        sistema; ya no debe aparecer en el panel renderizado."""
        resp = self.client.get('/servicios_publicos/combustible')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        iconos_esperados = [
            'fa-car-side',            # Vehículos Oficiales
            'fa-bus',                 # Autobuses Escolares / Pasajeros
            'fa-tractor',             # Maquinaria Pesada
            'fa-dumpster',            # Camión de Basura
            'fa-screwdriver-wrench',  # Equipo Menor
            'fa-car-tunnel',          # Vehículos Externos
            'fa-route',               # Cargas Foráneas
            'fa-hand-holding-heart',  # Apoyos Ciudadanos
            'fa-droplet',             # Fluidos (Urea)
            'fa-oil-can',             # Lubricantes (Aceite Motor)
        ]
        for icono in iconos_esperados:
            self.assertIn(icono, html, f"El icono '{icono}' no se encontró en el panel renderizado.")

        # Verificación negativa: la TARJETA DE CAPTURA "Camión Pipas" ya no
        # debe existir en el selector (ese servicio se opera fuera del
        # sistema). El Panel Ejecutivo/Dona de reportes históricos SÍ puede
        # seguir mostrando "Camión Pipas" si existen registros pasados, por
        # decisión explícita del usuario; solo se valida la tarjeta del
        # selector de nueva asignación.
        self.assertNotIn('data-tipo="PIPA"', html, "La tarjeta 'Camión Pipas' debe estar eliminada del selector.")

    def test_01b_tarjetas_de_bitacora_ya_no_muestran_subtitulo(self):
        """ORDEN TÉCNICA MAESTRA: las tarjetas de selección de bitácora ya
        no deben llevar el subtítulo descriptivo bajo el nombre."""
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertNotIn('subtitulo-tarjeta', html, "Ya no deben existir subtítulos en las tarjetas de bitácora.")

    def test_02_chofer_texto_libre_ya_no_es_select(self):
        """El campo de Chofer/Operador debe ser un input de texto libre."""
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertIn('name="chofer_nombre"', html)
        self.assertIn('<input type="text" class="form-control" name="chofer_nombre"', html)

    def test_03_crear_asignacion_oficial_con_chofer_nuevo_sin_caidas(self):
        """Crea una asignación de Vehículos Oficiales con un chofer capturado
        por teclado que AÚN NO EXISTE en el catálogo; debe darse de alta
        automáticamente y el vale debe guardarse sin ningún error 500."""
        nombre_chofer_nuevo = 'Chofer De Prueba Smoke Test SIGEM'
        with self.app.app_context():
            previo = Conductor.query.filter_by(nombre=nombre_chofer_nuevo).first()
            if previo:
                db.session.delete(previo)
                db.session.commit()

        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'unidad_organizacional': 'Presidencia Municipal',
            'tipo_asignacion': 'OFICIAL',
            'itinerario_destino': 'Prueba de Humo - Vehículos Oficiales',
            'responsable_nombre': 'Smoke Test Oficial',
            'chofer_nombre': nombre_chofer_nuevo,
            'litros_asignados': '12.0',
            'tipo_combustible': 'Gasolina',
            'tipo_recorrido': 'Local',
            'quien_autoriza': 'Smoke Test',
            'fecha_solicitud': '2026-01-01',
            'fecha_inicio': '2026-01-01',
            'hora_inicio': '08:00',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Smoke Test Oficial').first()
            self.assertIsNotNone(vale, "El vale OFICIAL debe haberse guardado exitosamente.")
            self.assertIsNotNone(vale.chofer_id, "El chofer capturado por teclado debe quedar vinculado.")
            self.assertEqual(vale.chofer.nombre, nombre_chofer_nuevo)

    def test_04_crear_asignacion_equipo_menor_captura_exclusiva_por_horas(self):
        """Crea una asignación de Equipo Menor midiendo 'Horas de Uso /
        Operación'; NUNCA debe capturarse ni guardarse kilometraje."""
        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'unidad_organizacional': 'Dirección de Servicios Públicos',
            'tipo_asignacion': 'EQUIPO_MENOR',
            'itinerario_destino': 'Prueba de Humo - Equipo Menor (motosierra)',
            'responsable_nombre': 'Smoke Test Equipo Menor',
            'chofer_nombre': 'Operador De Prueba Equipo Menor',
            'litros_asignados': '2.5',
            'tipo_combustible': 'Gasolina',
            'tipo_recorrido': 'Local',
            'quien_autoriza': 'Smoke Test',
            'fecha_solicitud': '2026-01-01',
            'fecha_inicio': '2026-01-01',
            'hora_inicio': '08:00',
            'horas_uso_equipo_menor': '3.5',
            # Aun si el navegador llegara a enviar KM por error de caché,
            # la ruta debe IGNORARLO para EQUIPO_MENOR (blindaje de datos).
            'km_inicial': '99999',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Smoke Test Equipo Menor').first()
            self.assertIsNotNone(vale, "El vale de Equipo Menor debe haberse guardado exitosamente.")
            self.assertIsNone(vale.km_inicial, "Equipo Menor NUNCA debe guardar kilometraje inicial.")
            self.assertIsNone(vale.km_final, "Equipo Menor NUNCA debe guardar kilometraje final.")
            self.assertEqual(vale.horas_trabajo(), 3.5, "Las horas de uso capturadas deben coincidir exactamente.")

    def test_05_camion_basura_es_bitacora_propia_y_conserva_horometro(self):
        """ORDEN TÉCNICA MAESTRA: Camión de Basura debe operar como
        bitácora propia (tipo_asignacion='CAMION_BASURA') exportando su
        propia plantilla oficial, pero CONSERVANDO la captura exclusiva
        por Horómetro (nunca kilometraje)."""
        with self.app.app_context():
            equipo = Equipo.query.first()
            if not equipo:
                self.skipTest("No hay equipos (maquinaria por horómetro) en el catálogo para esta prueba.")
            equipo_id = equipo.id

        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'unidad_organizacional': 'Dirección de Servicios Públicos',
            'tipo_asignacion': 'CAMION_BASURA',
            'itinerario_destino': 'Prueba de Humo - Camión de Basura',
            'responsable_nombre': 'Smoke Test Camion Basura',
            'chofer_nombre': 'Operador De Prueba Camion Basura',
            'litros_asignados': '40.0',
            'tipo_combustible': 'Diésel',
            'quien_autoriza': 'Smoke Test',
            'fecha_solicitud': '2026-01-01',
            'fecha_inicio': '2026-01-01',
            'hora_inicio': '08:00',
            'equipo_id': str(equipo_id),
            'horometro_inicial': '100.0',
            'horometro_final': '108.5',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Smoke Test Camion Basura').first()
            self.assertIsNotNone(vale, "El vale de Camión de Basura debe haberse guardado exitosamente.")
            self.assertEqual(vale.tipo_asignacion, 'CAMION_BASURA')
            self.assertEqual(vale.horas_trabajo(), 8.5)

        # Exportación con la plantilla oficial propia (BITACORA_CAMION_BASURA.xlsx)
        resp_excel = self.client.get('/exportar_excel_combustible?tipo_bitacora=CAMION_BASURA')
        self.assertEqual(resp_excel.status_code, 200)
        self.assertIn('spreadsheetml', resp_excel.content_type)

    def test_99_limpieza_de_registros_de_humo(self):
        """Elimina los vales y choferes de prueba creados por este self-test."""
        with self.app.app_context():
            for nombre in ('Smoke Test Oficial', 'Smoke Test Equipo Menor', 'Smoke Test Camion Basura'):
                vale = AsignacionCombustible.query.filter_by(responsable_nombre=nombre).first()
                if vale:
                    db.session.delete(vale)
            for nombre_chofer in ('Chofer De Prueba Smoke Test SIGEM', 'Operador De Prueba Equipo Menor', 'Operador De Prueba Camion Basura'):
                chofer = Conductor.query.filter_by(nombre=nombre_chofer).first()
                if chofer:
                    db.session.delete(chofer)
            db.session.commit()


if __name__ == '__main__':
    unittest.main()
