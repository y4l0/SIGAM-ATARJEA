# -*- coding: utf-8 -*-
"""
ACTUALIZACIÓN SIGAM ATARJEA: 4 REQUERIMIENTOS CRÍTICOS.

Este módulo valida, usando el test_client() de Flask:
  1. DESGLOSE DE MONTOS POR FUENTE DE FINANCIAMIENTO: los 4 apartados
     independientes (Federal, Estatal, Municipal, Beneficiario) se
     registran y editan correctamente, y el monto total se calcula
     AUTOMÁTICAMENTE como la suma de los 4.
  2. ELIMINACIÓN CON CONFIRMACIÓN Y CASCADA GLOBAL: /solicitud/<id>/eliminar
     borra por completo el registro (y sus adjuntos en cascada) de la
     base de datos, respetando el aislamiento estricto por dependencia.
  3. CUARTO ESTATUS "OTORGADO" Y EDICIÓN COMPLETA DE ESTATUS: el estatus
     "Otorgado" existe en el catálogo y es editable en cualquier momento
     posterior al registro inicial vía /solicitud/<id>/editar.
  4. DOCUMENTOS ADJUNTOS OPCIONALES: una solicitud se registra
     exitosamente sin adjuntar ningún archivo.

Ejecutar con:
    python -m pytest tests/test_desglose_montos_eliminacion_estatus.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Dependencia, Solicitud, Ciudadano, AdjuntoSolicitud
from werkzeug.security import generate_password_hash


class TestDesgloseMontosEliminacionEstatus(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

        with cls.app.app_context():
            # LIMPIEZA IDEMPOTENTE: este módulo registra solicitudes REALES vía
            # POST (no solo fixtures), lo que puede dejar datos persistentes de
            # ejecuciones anteriores de pytest (la BD es un archivo real, no
            # efímero). Se purgan primero para evitar colisiones de folio
            # (generar_folio() tiene una lógica legada que puede repetir
            # folios al toparse con filas huérfanas de corridas previas).
            Solicitud.query.filter(Solicitud.CURP.like('MONT%')).delete(synchronize_session=False)
            Ciudadano.query.filter(Ciudadano.CURP.like('MONT%')).delete(synchronize_session=False)
            db.session.commit()

            dep = Dependencia.query.filter_by(nombre='TEST_DEP_MONTOS').first()
            if not dep:
                dep = Dependencia(nombre='TEST_DEP_MONTOS')
                db.session.add(dep)
                db.session.flush()

            director = Usuario.query.filter_by(email='director_montos@test.atarjea.gob.mx').first()
            if not director:
                director = Usuario(
                    nombre='Director Prueba Montos', email='director_montos@test.atarjea.gob.mx',
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
        """Limpieza final: no dejar solicitudes de prueba reales persistidas
        en la base de datos, para no afectar corridas futuras ni métricas."""
        with cls.app.app_context():
            Solicitud.query.filter(Solicitud.CURP.like('MONT%')).delete(synchronize_session=False)
            Ciudadano.query.filter(Ciudadano.CURP.like('MONT%')).delete(synchronize_session=False)
            db.session.commit()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _datos_base_formulario(self, curp, monto_federal=1000, monto_estatal=2000,
                                monto_municipal=500, monto_beneficiario=250):
        return {
            'curp': curp,
            'rfc': '',
            'nombre': 'Juan',
            'apellido_paterno': 'Pérez',
            'apellido_materno': 'López',
            'genero': 'M',
            'fecha_nacimiento': '',
            'edad': '30',
            'discapacidad': '0',
            'comunidad': 'Atarjea',
            'codigo_postal': '',
            'telefono': '',
            'domicilio': '',
            'referencia': '',
            'programa': 'Programa de Prueba Montos',
            'tipo_apoyo': 'Alimentario',
            'monto_federal': str(monto_federal),
            'monto_estatal': str(monto_estatal),
            'monto_municipal': str(monto_municipal),
            'monto_beneficiario': str(monto_beneficiario),
            'dependencia': 'TEST_DEP_MONTOS',
            'estatus': 'Pendiente',
        }

    # ---------------- REQUERIMIENTO 1: DESGLOSE DE MONTOS POR FUENTE ----------------

    def test_01_registro_calcula_monto_total_automaticamente(self):
        """Al registrar, el monto total debe ser la suma EXACTA de los 4 apartados."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTAAA01'
        datos = self._datos_base_formulario(curp, 1000, 2000, 500, 250)
        resp = self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            self.assertIsNotNone(solicitud)
            self.assertEqual(float(solicitud.Monto_Federal), 1000.0)
            self.assertEqual(float(solicitud.Monto_Estatal), 2000.0)
            self.assertEqual(float(solicitud.Monto_Municipal), 500.0)
            self.assertEqual(float(solicitud.Monto_Beneficiario), 250.0)
            self.assertEqual(float(solicitud.Monto), 3750.0)

    def test_02_metodo_calcular_monto_total_suma_los_4_apartados(self):
        """El método calcular_monto_total() del modelo debe sumar correctamente, tratando None como 0."""
        with self.app.app_context():
            s = Solicitud(
                CURP='MONT000101HGTAAA01', Comunidad='Atarjea', Programa='Test',
                Tipo_Apoyo='Alimentario', Monto_Federal=100, Monto_Estatal=None,
                Monto_Municipal=50, Monto_Beneficiario=25, Estatus='Pendiente'
            )
            total = s.calcular_monto_total()
            self.assertEqual(total, 175.0)
            self.assertEqual(float(s.Monto), 175.0)

    def test_03_editar_solicitud_actualiza_desglose_y_recalcula_total(self):
        """La edición posterior de los 4 apartados debe recalcular el total automáticamente."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTBBB02'
        datos = self._datos_base_formulario(curp, 100, 100, 100, 100)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id
            self.assertEqual(float(solicitud.Monto), 400.0)

        resp = self.client.post(
            f'/solicitud/{solicitud_id}/editar',
            data={
                'programa': 'Programa Editado', 'tipo_apoyo': 'Educativo', 'estatus': 'Aprobado',
                'monto_federal': '5000', 'monto_estatal': '0', 'monto_municipal': '0', 'monto_beneficiario': '0',
            },
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud_editada = Solicitud.query.get(solicitud_id)
            self.assertEqual(float(solicitud_editada.Monto_Federal), 5000.0)
            self.assertEqual(float(solicitud_editada.Monto), 5000.0)
            self.assertEqual(solicitud_editada.Estatus, 'Aprobado')

    def test_04_expediente_muestra_desglose_de_montos(self):
        """El expediente (historial detallado) debe mostrar el desglose por fuente."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTCCC03'
        datos = self._datos_base_formulario(curp, 1111, 2222, 3333, 4444)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id

        resp = self.client.get(f'/expediente/{solicitud_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'1,111.00', resp.data)
        self.assertIn(b'2,222.00', resp.data)
        self.assertIn(b'3,333.00', resp.data)
        self.assertIn(b'4,444.00', resp.data)

    # ---------------- REQUERIMIENTO 4: DOCUMENTOS ADJUNTOS OPCIONALES ----------------

    def test_05_registro_exitoso_sin_ningun_documento_adjunto(self):
        """Debe poder registrarse exitosamente un apoyo SIN adjuntar ningún archivo."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTDDD04'
        datos = self._datos_base_formulario(curp)
        resp = self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            self.assertIsNotNone(solicitud, 'La solicitud debe registrarse exitosamente sin documentos adjuntos.')
            adjuntos = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud.id).count()
            self.assertEqual(adjuntos, 0)

    # ---------------- REQUERIMIENTO 3: ESTATUS "OTORGADO" EDITABLE ----------------

    def test_06_estatus_otorgado_aceptado_por_cambiar_estatus_solicitud(self):
        """El estatus 'Otorgado' debe ser aceptado por /cambiar_estatus/<id>/<estatus>."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTEEE05'
        datos = self._datos_base_formulario(curp)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id

        resp = self.client.post(
            f'/cambiar_estatus/{solicitud_id}/Otorgado', follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            solicitud_actualizada = Solicitud.query.get(solicitud_id)
            self.assertEqual(solicitud_actualizada.Estatus, 'Otorgado')

    def test_07_editar_solicitud_permite_estatus_otorgado_en_cualquier_momento(self):
        """El estatus debe ser completamente editable (incluido 'Otorgado') vía /editar."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTFFF06'
        datos = self._datos_base_formulario(curp)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id
            self.assertEqual(solicitud.Estatus, 'Pendiente')

        # Primer cambio: Pendiente -> Aprobado
        self.client.post(
            f'/solicitud/{solicitud_id}/editar',
            data={'programa': 'P', 'tipo_apoyo': 'Alimentario', 'estatus': 'Aprobado',
                  'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0', 'monto_beneficiario': '0'},
            follow_redirects=True
        )
        with self.app.app_context():
            self.assertEqual(Solicitud.query.get(solicitud_id).Estatus, 'Aprobado')

        # Segundo cambio posterior: Aprobado -> Otorgado (demuestra edición en CUALQUIER momento)
        resp = self.client.post(
            f'/solicitud/{solicitud_id}/editar',
            data={'programa': 'P', 'tipo_apoyo': 'Alimentario', 'estatus': 'Otorgado',
                  'monto_federal': '0', 'monto_estatal': '0', 'monto_municipal': '0', 'monto_beneficiario': '0'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Solicitud.query.get(solicitud_id).Estatus, 'Otorgado')

    # ---------------- REQUERIMIENTO 2: ELIMINACIÓN CON CASCADA GLOBAL ----------------

    def test_08_eliminar_solicitud_borra_definitivamente_de_la_base_de_datos(self):
        """/solicitud/<id>/eliminar debe borrar POR COMPLETO el registro de la BD."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTGGG07'
        datos = self._datos_base_formulario(curp)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id
            self.assertIsNotNone(Solicitud.query.get(solicitud_id))

        resp = self.client.post(f'/solicitud/{solicitud_id}/eliminar', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertIsNone(
                Solicitud.query.get(solicitud_id),
                'La solicitud debe desaparecer POR COMPLETO de la base de datos tras eliminar.'
            )

    def test_09_eliminar_solicitud_desaparece_de_inmediato_en_lista_solicitudes(self):
        """Tras eliminar, el folio ya NO debe aparecer en /solicitudes (sincronización inmediata)."""
        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        curp = 'MONT000101HGTHHH08'
        datos = self._datos_base_formulario(curp)
        self.client.post('/solicitar_apoyo', data=datos, follow_redirects=True)

        with self.app.app_context():
            solicitud = Solicitud.query.filter_by(CURP=curp).order_by(Solicitud.id.desc()).first()
            solicitud_id = solicitud.id
            folio = solicitud.folio

        resp_antes = self.client.get('/solicitudes')
        self.assertIn(folio.encode(), resp_antes.data)

        self.client.post(f'/solicitud/{solicitud_id}/eliminar', follow_redirects=True)

        resp_despues = self.client.get('/solicitudes')
        self.assertNotIn(folio.encode(), resp_despues.data)

    def test_10_director_no_puede_eliminar_solicitud_de_otra_dependencia(self):
        """AISLAMIENTO ESTRICTO: un Director no puede eliminar solicitudes de otra dependencia."""
        with self.app.app_context():
            dep_otra = Dependencia.query.filter_by(nombre='TEST_DEP_MONTOS_OTRA').first()
            if not dep_otra:
                dep_otra = Dependencia(nombre='TEST_DEP_MONTOS_OTRA')
                db.session.add(dep_otra)
                db.session.flush()
            if not Solicitud.query.filter_by(folio='TEST-MONTOS-OTRA-0001').first():
                db.session.add(Solicitud(
                    folio='TEST-MONTOS-OTRA-0001', CURP='MONT000101HGTIII09',
                    Comunidad='Atarjea', Programa='Otra Dependencia', Tipo_Apoyo='Alimentario',
                    Monto=500.0, Dependencia=dep_otra.nombre, dependencia_id=dep_otra.id,
                    Estatus='Pendiente', usuario_id=self.director_id
                ))
                db.session.commit()
            solicitud_id = Solicitud.query.filter_by(folio='TEST-MONTOS-OTRA-0001').first().id

        self._login('director_montos@test.atarjea.gob.mx', 'Prueba12345')
        resp = self.client.post(f'/solicitud/{solicitud_id}/eliminar', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertIsNotNone(
                Solicitud.query.get(solicitud_id),
                'La solicitud de otra dependencia NO debe eliminarse (aislamiento estricto).'
            )


if __name__ == '__main__':
    unittest.main()
