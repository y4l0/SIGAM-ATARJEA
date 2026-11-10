# -*- coding: utf-8 -*-
"""
ACTUALIZACIÓN SIGAM ATARJEA: TIPO DE BENEFICIARIO, MONTOS ESTIMADOS Y
NUEVAS COLUMNAS EN EL REPORTE DE EXCEL.

Este módulo valida, usando el test_client() de Flask:
  1. TIPO DE BENEFICIARIO: el selector (Particular/Grupo/Comunidad) se
     registra correctamente y es editable en cualquier momento posterior.
  2. SEPARACIÓN DE MONTOS GENERALES VS. ESTIMADOS: el Monto_Estimado se
     guarda y edita de forma INDEPENDIENTE del Monto General (Federal+
     Estatal+Municipal+Beneficiario), sin mezclarse automáticamente.
  3. LÓGICA DE SUMATORIA: Solicitud.monto_general(), monto_estimado() y
     monto_gran_total() calculan correctamente ambos montos combinados.
  4. NUEVAS COLUMNAS EN EL EXCEL: TIPO_BENEFICIARIO (a la izquierda de
     MONTO) con el valor real, y OBSERVACIONES (a la derecha de MONTO)
     con la leyenda de advertencia cuando existe un monto estimado.
  5. RETROCOMPATIBILIDAD: registros antiguos sin estos campos no causan
     errores (se tratan como 0 / 'Particular').

Ejecutar con:
    python -m pytest tests/test_tipo_beneficiario_monto_estimado_excel.py -v
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud, Ciudadano
from werkzeug.security import generate_password_hash


class TestTipoBeneficiarioMontoEstimadoExcel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            # Limpieza idempotente (la BD es un archivo real persistente).
            Solicitud.query.filter(Solicitud.CURP.like('BENF%')).delete(synchronize_session=False)
            Ciudadano.query.filter(Ciudadano.CURP.like('BENF%')).delete(synchronize_session=False)
            db.session.commit()

            dep = Dependencia.query.filter_by(nombre='TEST_DEP_BENEFICIARIO').first()
            if not dep:
                dep = Dependencia(nombre='TEST_DEP_BENEFICIARIO')
                db.session.add(dep)
                db.session.flush()

            director = Usuario.query.filter_by(email='director_beneficiario@test.atarjea.gob.mx').first()
            if not director:
                director = Usuario(
                    nombre='Director Prueba Beneficiario', email='director_beneficiario@test.atarjea.gob.mx',
                    password=generate_password_hash('Prueba12345'), rol='Director',
                    dependencia_id=dep.id, activo=True
                )
                db.session.add(director)
                db.session.flush()

            db.session.commit()
            cls.dep_id = dep.id
            cls.director_id = director.id

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            Solicitud.query.filter(Solicitud.CURP.like('BENF%')).delete(synchronize_session=False)
            Ciudadano.query.filter(Ciudadano.CURP.like('BENF%')).delete(synchronize_session=False)
            db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _datos_base_formulario(self, curp, tipo_beneficiario='Particular',
                                monto_federal=1000, monto_estatal=0, monto_municipal=0,
                                monto_beneficiario=0, monto_estimado=0):
        return {
            'curp': curp, 'rfc': '', 'nombre': 'Ana', 'apellido_paterno': 'García',
            'apellido_materno': 'Ruiz', 'genero': 'F', 'fecha_nacimiento': '', 'edad': '28',
            'discapacidad': '0', 'comunidad': 'Atarjea', 'codigo_postal': '', 'telefono': '',
            'domicilio': '', 'referencia': '', 'programa': 'Programa Prueba Beneficiario',
            'tipo_apoyo': 'Alimentario', 'tipo_beneficiario': tipo_beneficiario,
            'monto_federal': str(monto_federal), 'monto_estatal': str(monto_estatal),
            'monto_municipal': str(monto_municipal), 'monto_beneficiario': str(monto_beneficiario),
            'monto_estimado': str(monto_estimado),
            'dependencia': 'TEST_DEP_BENEFICIARIO', 'estatus': 'Pendiente',
        }

    # ---------------- REQUERIMIENTO 1: TIPO DE BENEFICIARIO ----------------

    def test_01_registro_guarda_tipo_beneficiario_correctamente(self):
        """El Tipo de Beneficiario seleccionado (Grupo) debe guardarse tal cual."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTAAA01'
        datos = self._datos_base_formulario(curp, tipo_beneficiario='Grupo')
        resp = self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            self.assertIsNotNone(solicitud)
            self.assertEqual(solicitud.Tipo_Beneficiario, 'Grupo')

    def test_02_registro_sin_especificar_usa_particular_por_defecto(self):
        """Si no se envía tipo_beneficiario, debe asumir 'Particular' (retrocompatibilidad)."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTBBB02'
        datos = self._datos_base_formulario(curp)
        del datos['tipo_beneficiario']
        resp = self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            self.assertEqual(solicitud.Tipo_Beneficiario, 'Particular')

    def test_03_tipo_beneficiario_editable_en_cualquier_momento(self):
        """El Tipo de Beneficiario debe poder cambiarse posteriormente vía /editar."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTCCC03'
        datos = self._datos_base_formulario(curp, tipo_beneficiario='Particular')
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id
            self.assertEqual(solicitud.Tipo_Beneficiario, 'Particular')

        resp = self.client.post(
            f'/solicitud/{solicitud_id}/editar',
            data={'programa': 'P', 'tipo_apoyo': 'Alimentario', 'estatus': 'Pendiente',
                  'tipo_beneficiario': 'Comunidad',
                  'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0',
                  'monto_beneficiario': '0', 'monto_estimado': '0'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Solicitud.query.get(solicitud_id).Tipo_Beneficiario, 'Comunidad')

    def test_04_formulario_de_registro_contiene_las_3_opciones_exactas(self):
        """El <select> de Tipo de Beneficiario debe ofrecer exactamente Particular/Grupo/Comunidad."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.get_data(as_text=True)
        self.assertIn('name="tipo_beneficiario"', html)
        self.assertIn('>Particular<', html)
        self.assertIn('>Grupo<', html)
        self.assertIn('>Comunidad<', html)

    # ---------------- REQUERIMIENTO 2 y 3: MONTOS GENERALES VS. ESTIMADOS Y SUMATORIA ----------------

    def test_05_monto_estimado_se_guarda_independiente_del_monto_general(self):
        """El Monto_Estimado NO debe sumarse automáticamente al Monto General (Monto)."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTDDD04'
        datos = self._datos_base_formulario(
            curp, monto_federal=1000, monto_estatal=500, monto_municipal=0,
            monto_beneficiario=0, monto_estimado=9999
        )
        resp = self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            self.assertEqual(float(solicitud.Monto), 1500.0, 'El Monto General no debe incluir el estimado.')
            self.assertEqual(float(solicitud.Monto_Estimado), 9999.0)

    def test_06_monto_estimado_editable_sin_restricciones(self):
        """El Monto Estimado debe poder modificarse en cualquier momento vía /editar."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTEEE05'
        datos = self._datos_base_formulario(curp, monto_estimado=100)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id

        resp = self.client.post(
            f'/solicitud/{solicitud_id}/editar',
            data={'programa': 'P', 'tipo_apoyo': 'Alimentario', 'estatus': 'Pendiente',
                  'tipo_beneficiario': 'Particular',
                  'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0',
                  'monto_beneficiario': '0', 'monto_estimado': '7500.50'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertEqual(float(Solicitud.query.get(solicitud_id).Monto_Estimado), 7500.50)

    def test_07_metodos_de_sumatoria_del_modelo(self):
        """monto_general(), monto_estimado() y monto_gran_total() deben calcular correctamente."""
        with self.app.app_context():
            s = Solicitud(
                CURP='BENF000101HGTFFF06', Comunidad='Atarjea', Programa='Test',
                Tipo_Apoyo='Alimentario', Monto_Federal=1000, Monto_Estatal=0,
                Monto_Municipal=0, Monto_Beneficiario=0, Monto_Estimado=250.50,
                Estatus='Pendiente'
            )
            s.calcular_monto_total()
            self.assertEqual(s.monto_general(), 1000.0)
            self.assertEqual(s.monto_estimado(), 250.50)
            self.assertEqual(s.monto_gran_total(), 1250.50)

    def test_08_retrocompatibilidad_registro_sin_monto_estimado_no_falla(self):
        """Un registro con Monto_Estimado=None no debe causar error al calcular totales."""
        with self.app.app_context():
            s = Solicitud(
                CURP='BENF000101HGTGGG07', Comunidad='Atarjea', Programa='Legacy',
                Tipo_Apoyo='Alimentario', Monto=500.0, Monto_Estimado=None,
                Tipo_Beneficiario=None, Estatus='Pendiente'
            )
            self.assertEqual(s.monto_estimado(), 0.0)
            self.assertEqual(s.monto_gran_total(), 500.0)

    def test_09_formulario_muestra_secciones_divididas_con_titulos_y_hr(self):
        """El formulario debe mostrar títulos 'Montos Generales' y 'Montos Estimados' con línea divisoria."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.get('/solicitar_apoyo')
        html = resp.get_data(as_text=True)
        self.assertIn('Montos Generales', html)
        self.assertIn('Montos Estimados', html)
        self.assertIn('<hr', html)
        self.assertIn('name="monto_estimado"', html)

    # ---------------- REQUERIMIENTO 4: NUEVAS COLUMNAS EN EL EXCEL ----------------

    def test_10_excel_incluye_columna_tipo_beneficiario_con_valor_real(self):
        """El Excel debe incluir TIPO_BENEFICIARIO con el valor real capturado."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTHHH08'
        datos = self._datos_base_formulario(curp, tipo_beneficiario='Grupo', monto_federal=100)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            fecha_iso = solicitud.Fecha_Solicitud.strftime('%Y-%m-%d')

        resp = self.client.get(f'/exportar_excel?fecha_inicio={fecha_iso}&fecha_fin={fecha_iso}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        encabezados = [c.value for c in ws[1]]
        self.assertIn('TIPO_BENEFICIARIO', encabezados)
        self.assertIn('OBSERVACIONES', encabezados)
        idx_monto = encabezados.index('MONTO')
        idx_tipo_beneficiario = encabezados.index('TIPO_BENEFICIARIO')
        idx_observaciones = encabezados.index('OBSERVACIONES')
        # TIPO_BENEFICIARIO inmediatamente a la IZQUIERDA de MONTO.
        self.assertEqual(idx_tipo_beneficiario, idx_monto - 1)
        # OBSERVACIONES inmediatamente a la DERECHA de MONTO.
        self.assertEqual(idx_observaciones, idx_monto + 1)

        fila_datos = [c.value for c in ws[2]]
        self.assertEqual(fila_datos[idx_tipo_beneficiario], 'Grupo')

    def test_11_excel_incluye_observacion_de_advertencia_si_hay_monto_estimado(self):
        """Debe aparecer la leyenda de advertencia en OBSERVACIONES cuando hay monto estimado."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTIII09'
        datos = self._datos_base_formulario(curp, monto_federal=100, monto_estimado=500)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            fecha_iso = solicitud.Fecha_Solicitud.strftime('%Y-%m-%d')

        resp = self.client.get(f'/exportar_excel?fecha_inicio={fecha_iso}&fecha_fin={fecha_iso}')
        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        encabezados = [c.value for c in ws[1]]
        idx_observaciones = encabezados.index('OBSERVACIONES')
        idx_curp = encabezados.index('CURP')

        fila_encontrada = None
        for fila in ws.iter_rows(min_row=2, values_only=True):
            if fila[idx_curp] == curp:
                fila_encontrada = fila
                break
        self.assertIsNotNone(fila_encontrada)
        self.assertIn('ADVERTENCIA', fila_encontrada[idx_observaciones])
        self.assertIn('Estimado', fila_encontrada[idx_observaciones])

    def test_12_excel_observaciones_vacio_si_no_hay_monto_estimado(self):
        """Si no hay monto estimado, OBSERVACIONES debe quedar vacío (sin advertencia falsa)."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTJJJ10'
        datos = self._datos_base_formulario(curp, monto_federal=100, monto_estimado=0)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            fecha_iso = solicitud.Fecha_Solicitud.strftime('%Y-%m-%d')

        resp = self.client.get(f'/exportar_excel?fecha_inicio={fecha_iso}&fecha_fin={fecha_iso}')
        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        encabezados = [c.value for c in ws[1]]
        idx_observaciones = encabezados.index('OBSERVACIONES')
        idx_curp = encabezados.index('CURP')

        for fila in ws.iter_rows(min_row=2, values_only=True):
            if fila[idx_curp] == curp:
                self.assertIn(fila[idx_observaciones], [None, ''])
                break
        else:
            self.fail('No se encontró la fila del CURP de prueba en el Excel.')

    def test_13_excel_formula_de_suma_del_monto_general_sigue_intacta(self):
        """La fórmula =SUM(...) de la columna MONTO debe seguir funcionando con las columnas nuevas."""
        self._login('director_beneficiario@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'BENF000101HGTKKK11'
        datos = self._datos_base_formulario(curp, monto_federal=250)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            fecha_iso = solicitud.Fecha_Solicitud.strftime('%Y-%m-%d')

        resp = self.client.get(f'/exportar_excel?fecha_inicio={fecha_iso}&fecha_fin={fecha_iso}')
        wb = load_workbook(io.BytesIO(resp.data))
        ws = wb['beneficiarios']
        encabezados = [c.value for c in ws[1]]
        idx_monto = encabezados.index('MONTO') + 1  # 1-based para openpyxl
        fila_total = ws.max_row
        celda_formula = ws.cell(row=fila_total, column=idx_monto)
        self.assertTrue(str(celda_formula.value).startswith('=SUM('))


if __name__ == '__main__':
    unittest.main()
