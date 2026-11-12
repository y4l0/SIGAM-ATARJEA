# -*- coding: utf-8 -*-
"""
tests/test_servicios_publicos_unificado.py

UNIFICACIÓN DEL FORMULARIO DE SERVICIOS PÚBLICOS (COMBUSTIBLE / TRASLADOS
/ AGUA) CON EL REGISTRO GENERAL DE APOYOS - SIGAM Atarjea.

Valida, usando el test_client() de Flask, que la Asignación de
Combustible (Formulario N° 10, incluyendo las modalidades de Apoyo
Ciudadano: Traslado/Vale de Gasolina/Viajes de Agua) incorpore los
mismos apartados estandarizados que el registro general de apoyos:
  1. Tipo de Beneficiario (Particular, Grupo, Comunidad).
  2. Desglose de Montos por Fuente de Financiamiento (Federal, Estatal,
     Municipal, Beneficiario), con el Monto General calculado
     automáticamente como la suma de los 4.
  3. Separación de Montos Generales vs. Estimados (independientes).
  4. Estatus editable, incluyendo el nuevo estatus "Otorgado".
  5. Documentos adjuntos opcionales (el registro se guarda exitosamente
     sin ningún archivo adjunto).
  6. Eliminación con confirmación (borra por completo el registro).

Ejecutar con:
    python -m pytest tests/test_servicios_publicos_unificado.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import AsignacionCombustible, AdjuntoAsignacionCombustible


class TestServiciosPublicosUnificado(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            AsignacionCombustible.query.filter(
                AsignacionCombustible.folio_asignacion.like('SELFTEST-SP-UNIF%')
            ).delete(synchronize_session=False)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            AsignacionCombustible.query.filter(
                AsignacionCombustible.folio_asignacion.like('SELFTEST-SP-UNIF%')
            ).delete(synchronize_session=False)
            db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()
        self._login('serviciospublicosAtarjea@gmail.com', 'serviciospublicos')

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _datos_base(self, tipo_asignacion='CIUDADANO', subtipo_asignacion='TRASLADO', **overrides):
        datos = {
            'unidad_organizacional': 'Dirección de Servicios Públicos',
            'tipo_asignacion': tipo_asignacion,
            'subtipo_asignacion': subtipo_asignacion,
            'itinerario_destino': 'Prueba unificada de Servicios Públicos',
            'responsable_nombre': 'Self-Test Unificado SP',
            'litros_asignados': '5.0',
            'tipo_beneficiario': 'Comunidad',
            'monto_federal': '100',
            'monto_estatal': '50',
            'monto_municipal': '25',
            'monto_beneficiario': '0',
            'monto_estimado': '300',
        }
        datos.update(overrides)
        return datos

    # ---------------- REQUERIMIENTO 1: TIPO DE BENEFICIARIO ----------------

    def test_01_registro_guarda_tipo_beneficiario(self):
        """El Tipo de Beneficiario (Particular/Grupo/Comunidad) debe guardarse correctamente."""
        datos = self._datos_base(tipo_beneficiario='Grupo')
        resp = self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            self.assertIsNotNone(asignacion)
            self.assertEqual(asignacion.tipo_beneficiario, 'Grupo')

    # ---------------- REQUERIMIENTO 2: DESGLOSE DE MONTOS POR FUENTE ----------------

    def test_02_monto_general_se_calcula_automaticamente_como_suma_de_4_fuentes(self):
        """El Monto General debe calcularse automáticamente como Federal+Estatal+Municipal+Beneficiario."""
        datos = self._datos_base(
            monto_federal='1000', monto_estatal='500', monto_municipal='250', monto_beneficiario='50'
        )
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            self.assertEqual(float(asignacion.monto_general), 1800.0)

    # ---------------- REQUERIMIENTO 3: MONTO ESTIMADO INDEPENDIENTE ----------------

    def test_03_monto_estimado_es_independiente_del_monto_general(self):
        """El Monto Estimado NUNCA debe mezclarse automáticamente con el Monto General."""
        datos = self._datos_base(monto_federal='100', monto_estimado='9999')
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            self.assertEqual(float(asignacion.monto_estimado), 9999.0)
            self.assertNotEqual(float(asignacion.monto_general), 9999.0)

    # ---------------- REQUERIMIENTO 4: ESTATUS "OTORGADO" EDITABLE ----------------

    def test_04_estatus_otorgado_aceptado_por_editar_asignacion(self):
        """El estatus 'Otorgado' debe ser aceptado por /servicios_publicos/asignacion/editar/<id>."""
        datos = self._datos_base()
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            asignacion_id = asignacion.id

        resp = self.client.post(
            f'/servicios_publicos/asignacion/editar/{asignacion_id}',
            data={'estatus': 'Otorgado', 'tipo_beneficiario': 'Comunidad',
                  'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0',
                  'monto_beneficiario': '0', 'monto_estimado': '0'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertEqual(AsignacionCombustible.query.get(asignacion_id).estatus, 'Otorgado')

    def test_05_estatus_otorgado_aceptado_por_cambiar_estatus(self):
        """El estatus 'Otorgado' debe ser aceptado por /servicios_publicos/asignacion/cambiar_estatus/<id>."""
        datos = self._datos_base()
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            asignacion_id = asignacion.id

        resp = self.client.post(
            f'/servicios_publicos/asignacion/cambiar_estatus/{asignacion_id}',
            data={'nuevo_estatus': 'Otorgado'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertEqual(AsignacionCombustible.query.get(asignacion_id).estatus, 'Otorgado')

    # ---------------- REQUERIMIENTO 5: DOCUMENTOS ADJUNTOS OPCIONALES ----------------

    def test_06_registro_exitoso_sin_ningun_documento_adjunto(self):
        """La asignación debe registrarse exitosamente sin adjuntar ningún archivo."""
        datos = self._datos_base()
        resp = self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            self.assertIsNotNone(asignacion)
            adjuntos = AdjuntoAsignacionCombustible.query.filter_by(asignacion_id=asignacion.id).count()
            self.assertEqual(adjuntos, 0)


    # ---------------- REQUERIMIENTO 6: ELIMINACIÓN CON CONFIRMACIÓN ----------------

    def test_07_eliminar_asignacion_borra_definitivamente_de_la_base_de_datos(self):
        """/servicios_publicos/asignacion/eliminar/<id> debe borrar POR COMPLETO el registro."""
        datos = self._datos_base()
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        with self.app.app_context():
            asignacion = AsignacionCombustible.query.filter_by(
                responsable_nombre='Self-Test Unificado SP'
            ).order_by(AsignacionCombustible.id.desc()).first()
            asignacion_id = asignacion.id
            self.assertIsNotNone(AsignacionCombustible.query.get(asignacion_id))

        resp = self.client.post(
            f'/servicios_publicos/asignacion/eliminar/{asignacion_id}', follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertIsNone(
                AsignacionCombustible.query.get(asignacion_id),
                'La asignación debe desaparecer POR COMPLETO de la base de datos tras eliminar.'
            )

    # ---------------- VERIFICACIÓN GENERAL: FORMULARIO Y REPORTE EXCEL ----------------

    def test_08_panel_servicios_publicos_contiene_los_campos_unificados(self):
        """El panel debe renderizar los nuevos campos unificados (Tipo de
        Beneficiario, Montos Generales, Monto Estimado, Documento Adjunto)."""
        resp = self.client.get('/servicios_publicos')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('tipo_beneficiario', html)
        self.assertIn('monto_federal', html)
        self.assertIn('monto_estimado', html)
        self.assertIn('documento_adjunto', html)

    def test_09_excel_apoyos_ciudadanos_incluye_columnas_nuevas_al_final(self):
        """El Excel oficial de Apoyos Ciudadanos debe incluir, AL FINAL de
        la plantilla, las columnas TIPO_BENEFICIARIO/MONTO_GENERAL/
        MONTO_ESTIMADO/OBSERVACIONES, sin romper las columnas originales."""
        datos = self._datos_base(tipo_beneficiario='Grupo', monto_federal='500')
        self.client.post('/servicios_publicos/asignacion/crear', data=datos, follow_redirects=True)

        resp = self.client.get('/exportar_excel_combustible?tipo_bitacora=CIUDADANO')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp.content_type)

        from io import BytesIO
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(resp.data))
        ws = wb.active
        fila_encabezados = [c.value for c in ws[8]]
        self.assertIn('TIPO_BENEFICIARIO', fila_encabezados)
        self.assertIn('MONTO_GENERAL', fila_encabezados)
        self.assertIn('MONTO_ESTIMADO', fila_encabezados)
        self.assertIn('OBSERVACIONES', fila_encabezados)
        self.assertEqual(fila_encabezados[0], 'FECHA')
        self.assertEqual(fila_encabezados[6], 'NO. DE\nLITROS')


if __name__ == '__main__':
    unittest.main()
