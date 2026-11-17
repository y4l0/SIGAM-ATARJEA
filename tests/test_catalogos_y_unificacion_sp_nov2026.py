# -*- coding: utf-8 -*-
"""
tests/test_catalogos_y_unificacion_sp_nov2026.py

CORRECCIÓN DEFINITIVA DE CATÁLOGOS DE TIPO DE APOYO Y UNIFICACIÓN DE
SERVICIOS PÚBLICOS (SIGAM Atarjea, noviembre 2026). Valida:

  1. Regla EXACTA de agregar vs. sustitución total por dependencia:
     - DIF: AGREGA "Traslados" y "Aparatos funcionales", ELIMINA
       "Apoyo a la Movilidad" del catálogo base.
     - Prevención: SUSTITUCIÓN TOTAL (solo sus 2 apartados).
     - Deportes: SUSTITUCIÓN TOTAL (solo sus 2 apartados).
     - Protección Civil: SUSTITUCIÓN TOTAL (6 apartados exactos).
     - Casa de la Cultura: SUSTITUCIÓN TOTAL (1 apartado único).
     - Presidencia Municipal: el catálogo base SE QUEDA y se AGREGAN
       las 11 opciones nuevas (nunca se reemplaza).
  2. Todas las cuentas oficiales (11 dependencias + 2 de Servicios
     Públicos + Admin) existen y funcionan.
  3. Unificación de Servicios Públicos con Datos del Ciudadano,
     Ubicación/Contacto, Tipo de Beneficiario (Escuela/Clínica) y
     Parque Vehicular.
  4. Resumen Semanal incluye el desglose por Área/Dependencia.

Ejecutar con:
    python -m pytest tests/test_catalogos_y_unificacion_sp_nov2026.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, AsignacionCombustible


class TestCatalogosYUnificacionSPNov2026(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    # ---------------- PUNTO 1: REGLA EXACTA AGREGAR VS. SUSTITUIR ----------------

    def test_01_dif_agrega_traslados_y_aparatos_funcionales_elimina_movilidad(self):
        """DIF: agrega 'Traslados' y 'Aparatos funcionales'; elimina 'Apoyo a la Movilidad'."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('Aparatos funcionales', html)
        self.assertIn("'DIF Municipal': CATALOGO_DIF_TIPO_APOYO", html)
        self.assertIn("filter(function (opcion) { return opcion !== 'Apoyo a la Movilidad'; })", html)

    def test_02_prevencion_sustitucion_total_sin_catalogo_base(self):
        """Prevención: SUSTITUCIÓN TOTAL, ya no debe concatenar el catálogo base."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn("'Prevención': [\n            'Atención y seguimiento de víctimas especiales',\n            'Prevención del delito'\n        ],", html)

    def test_03_deportes_sustitucion_total_sin_catalogo_base(self):
        """Deportes: SUSTITUCIÓN TOTAL, ya no debe concatenar el catálogo base."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn("'Dirección de Deportes': [\n            'Apoyo en favor del fomento del deporte',\n            'Apoyo de entrega de equipo deportivo'\n        ],", html)

    def test_04_proteccion_civil_sustitucion_total_sin_cambios(self):
        """Protección Civil: catálogo reemplazado en su totalidad por los 6 apartados exactos."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        for opcion in ['RESGUARDO CIVIL', 'CORTE DE ÁRBOLES', 'ACCESO A VIALIDADES',
                        'ATENCIÓN A INCENDIOS', 'BÚSQUEDA Y RESCATE', 'RESGUARDO A LA POBLACIÓN']:
            self.assertIn(opcion, html)

    def test_05_casa_de_la_cultura_sustitucion_total_apartado_unico(self):
        """Casa de la Cultura: catálogo reemplazado por una única opción."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn('Apoyo a actividades culturales', html)

    def test_06_presidencia_municipal_agrega_11_opciones_sin_reemplazar_base(self):
        """Presidencia Municipal: el catálogo base SE QUEDA y se AGREGAN las 11 opciones nuevas."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.data.decode('utf-8')
        self.assertIn("'Presidencia Municipal': CATALOGO_BASE_TIPO_APOYO.concat([", html)
        self.assertIn('Apoyo para instituciones', html)

    def test_07_editar_solicitud_replica_la_misma_regla_exacta(self):
        """El Jinja de editar_solicitud.html debe replicar la misma regla exacta del JS."""
        self._login('admin@atarjea.gob.mx', 'admin')
        from app.models import Solicitud
        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(folio='TEST-CAT-NOV2026-0001').first()
            if not solicitud:
                solicitud = Solicitud(
                    folio='TEST-CAT-NOV2026-0001', CURP='CATX000101HGTAAA01',
                    Comunidad='Atarjea', Programa='Prueba Catálogo DIF',
                    Tipo_Apoyo='Traslados', Monto=0.0,
                    Dependencia='DIF Municipal', Estatus='Pendiente',
                )
                db.session.add(solicitud)
                db.session.commit()
            solicitud_id = solicitud.id
        resp = self.client.get(f'/solicitud/{solicitud_id}/editar')
        html = resp.data.decode('utf-8')
        self.assertIn('Aparatos funcionales', html)
        self.assertNotIn("'DIF Municipal': ['Alimentario', 'Educativo', 'A la Salud', 'A la Vivienda', 'Apoyo a la Movilidad'", html)

    # ---------------- PUNTO 2: TODAS LAS CUENTAS DEL SISTEMA ----------------

    def test_08_las_11_dependencias_mas_servicios_publicos_y_admin_existen(self):
        """Las 11 dependencias oficiales + 2 cuentas de Servicios Públicos + Admin deben existir."""
        with self.app.app_context():
            correos_oficiales = [
                'atarjea2016@gmail.com', 'procatarjea@gmail.com', 'ruralatarjea@gmail.com',
                'casadelaculturaatarjea@gmail.com', 'desarrollo-social@atarjea.gob.mx',
                'atarjeaprevencionmo6@gmail.com', 'Kimbybueno84@gmail.com',
                'presidenciamunicipala@gmail.com', 'sayuntamiento@gmail.com',
                'proteccionatarjea2021@gmail.com',
                'serviciospublicosAtarjea@gmail.com', 'Serviciospublicos@gmail.com',
                'admin@atarjea.gob.mx',
            ]
            for correo in correos_oficiales:
                usuario = Usuario.query.filter(db.func.lower(Usuario.email) == correo.lower()).first()
                self.assertIsNotNone(usuario, f"La cuenta '{correo}' debe existir siempre.")
                self.assertTrue(usuario.activo, f"La cuenta '{correo}' debe estar activa.")

    # ---------------- PUNTO 3: UNIFICACIÓN DE SERVICIOS PÚBLICOS ----------------

    def test_09_servicios_publicos_muestra_datos_del_ciudadano_y_ubicacion(self):
        """El panel de Servicios Públicos debe mostrar la sección de Datos del Ciudadano y Ubicación."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/combustible')
        html = resp.data.decode('utf-8')
        self.assertIn('id="fila-datos-ciudadano"', html)
        self.assertIn('name="ciudadano_curp"', html)
        self.assertIn('name="ciudadano_comunidad"', html)
        self.assertIn('name="ciudadano_domicilio"', html)
        self.assertIn('name="ciudadano_codigo_postal"', html)
        self.assertIn('Escuela', html)
        self.assertIn('Clínica', html)
        self.assertIn('Parque Vehicular Municipal', html)
        self.assertIn('name="quien_autoriza" list="lista-quien-autoriza"', html)
        self.assertIn('name="responsable_nombre"', html)

    def test_10_crear_asignacion_ciudadana_guarda_datos_del_ciudadano(self):
        """Crear una Asignación de Combustible tipo CIUDADANO debe guardar CURP/comunidad/domicilio/CP."""
        self._login('serviciospublicosAtarjea@gmail.com', 'serviciospublicos')
        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'tipo_asignacion': 'CIUDADANO',
            'subtipo_asignacion': 'TRASLADO',
            'unidad_organizacional': 'Dirección de Servicios Públicos',
            'responsable_nombre': 'Ciudadano de Prueba Nov2026',
            'quien_autoriza': 'Autorizador de Prueba',
            'litros_asignados': '10',
            'tipo_combustible': 'Gasolina',
            'fecha_inicio': '2026-11-17',
            'ciudadano_curp': 'cunx000101hgtaaa01',
            'ciudadano_comunidad': 'Atarjea (Cabecera)',
            'ciudadano_domicilio': 'Calle Prueba #123',
            'ciudadano_codigo_postal': '37940',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Ciudadano de Prueba Nov2026'
            ).order_by(AsignacionCombustible.id.desc()).first()
            self.assertIsNotNone(asignacion)
            self.assertEqual(asignacion.ciudadano_curp, 'CUNX000101HGTAAA01')
            self.assertEqual(asignacion.ciudadano_comunidad, 'Atarjea (Cabecera)')
            self.assertEqual(asignacion.ciudadano_domicilio, 'Calle Prueba #123')
            self.assertEqual(asignacion.ciudadano_codigo_postal, '37940')

    # ---------------- PUNTO 4: RESUMEN SEMANAL POR ÁREA ----------------

    def test_11_reporte_semanal_incluye_desglose_por_area(self):
        """El Reporte Semanal Consolidado debe incluir el desglose por Área/Dependencia."""
        self._login('admin@atarjea.gob.mx', 'admin')
        resp = self.client.get('/servicios_publicos/reporte_semanal')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('Desglose por Área / Dependencia', html)

    def test_12_calculo_resumen_semanal_retorna_clave_desglose_por_area(self):
        """La función de cálculo del Reporte Semanal debe incluir 'desglose_por_area' sin colapsar."""
        with self.app.app_context():
            from app.routes import calcular_reporte_semanal_consolidado
            reporte = calcular_reporte_semanal_consolidado()
            self.assertIn('desglose_por_area', reporte)
            self.assertIsInstance(reporte['desglose_por_area'], list)


if __name__ == '__main__':
    unittest.main()
