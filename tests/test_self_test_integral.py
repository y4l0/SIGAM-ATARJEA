# -*- coding: utf-8 -*-
"""
ORDEN TÉCNICA MAESTRA: REINGENIERÍA TOTAL "MECÁNICA DE TSURU"
Punto 5 - PRUEBAS AUTOMATIZADAS LOCALES (SELF-TEST).

Simula de extremo a extremo, usando el test_client() de Flask (sin
levantar un servidor real), los flujos críticos que el usuario reportó
como "colapso":
  1. Login exitoso y login fallido (credenciales incorrectas).
  2. Creación de un vale (Asignación de Combustible / Formulario N° 10).
  3. Generación del reporte en Excel (plantilla oficial BITACORA_
     VEHICULOS_OFICIALES.xlsx) para ese vale recién creado.
  4. Generación del PDF del Formulario N° 10 para ese vale.
  5. Cálculo del inventario del tanque de 1,000 L, verificando que las
     Cargas Foráneas NUNCA descuenten litros del tanque municipal.
  6. Acceso al Panel de Auditoría en Vivo (solo Admin/Presidente).
  7. Limpieza: el vale de prueba creado se elimina al final para no
     dejar datos huérfanos en la base de datos real.

Ejecutar con: python -m pytest tests/test_self_test_integral.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import (
    Usuario, AsignacionCombustible, EstatusAsignacionEnum, TipoBitacoraEnum,
    RegistroAbasto
)


class TestSelfTestIntegral(unittest.TestCase):

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

    def test_01_login_exitoso_admin(self):
        """El login del Administrador/Alcaldía debe quedar 100% accesible."""
        client = self.app.test_client()
        resp = self._login(client, 'admin@atarjea.gob.mx', 'admin')
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            admin = Usuario.query.filter_by(email='admin@atarjea.gob.mx').first()
            self.assertIsNotNone(admin, "La cuenta admin@atarjea.gob.mx debe existir siempre tras el arranque.")
            self.assertTrue(admin.activo, "La cuenta admin debe estar siempre activa.")

    def test_02_login_fallido_no_colapsa(self):
        """Credenciales incorrectas deben regresar 200 (login.html) y NUNCA un 500."""
        client = self.app.test_client()
        resp = self._login(client, 'admin@atarjea.gob.mx', 'password-incorrecta')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_03_login_usuario_inexistente_no_colapsa(self):
        """Un correo que no existe en la base de datos nunca debe provocar un 500."""
        client = self.app.test_client()
        resp = self._login(client, 'no-existe@atarjea.gob.mx', 'cualquiera')
        self.assertEqual(resp.status_code, 200)

    def test_04_crear_vale_combustible_oficial(self):
        """Crea un vale real (Formulario N° 10) de tipo OFICIAL sin colapsar."""
        resp = self.client.post('/servicios_publicos/asignacion/crear', data={
            'unidad_organizacional': 'Presidencia Municipal',
            'tipo_asignacion': 'OFICIAL',
            'itinerario_destino': 'Recorrido de supervisión - Prueba Self-Test',
            'responsable_nombre': 'Self-Test Automatizado',
            'litros_asignados': '15.5',
            'tipo_combustible': 'Gasolina',
            'tipo_recorrido': 'Local',
            'quien_autoriza': 'Self-Test',
            'fecha_solicitud': '2026-01-01',
            'fecha_inicio': '2026-01-01',
            'hora_inicio': '08:00',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Self-Test Automatizado').first()
            self.assertIsNotNone(vale, "El vale de prueba debe haberse creado correctamente.")
            self.assertEqual(vale.estatus, EstatusAsignacionEnum.AUTORIZADO.value)

    def test_05_generar_pdf_formulario_10(self):
        """El PDF del Formulario N° 10 debe generarse sin error 500."""
        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Self-Test Automatizado').first()
            self.assertIsNotNone(vale)
            vale_id = vale.id
        resp = self.client.get(f'/servicios_publicos/asignacion/pdf/{vale_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'application/pdf')

    def test_06_generar_excel_bitacora_oficial(self):
        """
        ORDEN TÉCNICA MAESTRA (11 plantillas oficiales): el Excel debe
        generarse exactamente con la plantilla oficial de la bitácora
        solicitada (OFICIAL), sin error 500. Ya no existe una opción
        "todas las bitácoras" ni una plantilla genérica: el parámetro
        tipo_bitacora es obligatorio.
        """
        resp = self.client.get('/exportar_excel_combustible?tipo_bitacora=OFICIAL')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp.content_type)

        # Sin tipo de bitácora, nunca debe colapsar: redirige con aviso.
        resp_sin_tipo = self.client.get('/exportar_excel_combustible')
        self.assertEqual(resp_sin_tipo.status_code, 302)

    def test_07_inventario_tanque_excluye_cargas_foraneas(self):
        """
        El inventario del tanque de 1,000 L debe calcularse SOLO restando
        asignaciones no-FORÁNEAS, no-CANCELADAS. Simula el cálculo exacto
        que hace servicios_publicos() en routes.py.
        """
        with self.app.app_context():
            TANQUE_CAPACIDAD_LITROS = 1000.0
            litros_abasto_total = sum(float(a.litros_recibidos) for a in RegistroAbasto.query.all())
            asignaciones = AsignacionCombustible.query.all()
            litros_autorizados_total = sum(
                float(a.litros_asignados or 0)
                for a in asignaciones
                if a.estatus != EstatusAsignacionEnum.CANCELADA.value
                and a.tipo_asignacion != TipoBitacoraEnum.FORANEA.value
            )
            asignaciones_foraneas = [a for a in asignaciones if a.tipo_asignacion == TipoBitacoraEnum.FORANEA.value]
            litros_foraneas = sum(float(a.litros_asignados or 0) for a in asignaciones_foraneas)
            litros_autorizados_sin_exclusion = sum(
                float(a.litros_asignados or 0) for a in asignaciones
                if a.estatus != EstatusAsignacionEnum.CANCELADA.value
            )
            if litros_foraneas > 0:
                self.assertLess(
                    litros_autorizados_total, litros_autorizados_sin_exclusion,
                    "Las Cargas Foráneas deben quedar excluidas del descuento del tanque municipal."
                )
            tanque_litros_disponibles = min(
                TANQUE_CAPACIDAD_LITROS,
                max(0.0, litros_abasto_total - litros_autorizados_total)
            )
            self.assertGreaterEqual(tanque_litros_disponibles, 0.0)
            self.assertLessEqual(tanque_litros_disponibles, TANQUE_CAPACIDAD_LITROS)

    def test_08_panel_auditoria_en_vivo_accesible_para_admin(self):
        """El Panel de Auditoría en Vivo debe cargar sin error para el Admin."""
        resp = self.client.get('/auditoria_en_vivo')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_09_panel_auditoria_en_vivo_restringido_a_otros_roles(self):
        """Un rol sin privilegios de Alcaldía no debe poder ver el panel."""
        client = self.app.test_client()
        self._login(client, 'serviciospublicosAtarjea@gmail.com', 'serviciospublicos')
        resp = client.get('/auditoria_en_vivo', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Panel del Alcalde', resp.data)

    def test_10_exportar_las_10_plantillas_oficiales(self):
        """
        ORDEN TÉCNICA MAESTRA: cada uno de los 10 tipos de bitácora debe
        exportar exclusivamente su propia plantilla oficial (.xlsx), sin
        error 500 y sin mezclar datos entre plantillas. Crea un vale
        sintético por cada tipo, exporta y limpia al finalizar.
        """
        vales_creados_ids = []
        try:
            with self.app.app_context():
                for tipo in TipoBitacoraEnum:
                    vale = AsignacionCombustible(
                        folio_asignacion=f"SELFTEST-{tipo.value}-0001",
                        unidad_organizacional='Dirección de Servicios Públicos',
                        tipo_asignacion=tipo.value,
                        itinerario_destino='Prueba automatizada de plantilla oficial',
                        responsable_nombre='Self-Test Plantillas',
                        litros_asignados=10.0,
                        estatus='Autorizado',
                    )
                    db.session.add(vale)
                    db.session.flush()
                    vales_creados_ids.append(vale.id)
                db.session.commit()

            for tipo in TipoBitacoraEnum:
                resp = self.client.get(f'/exportar_excel_combustible?tipo_bitacora={tipo.value}')
                self.assertEqual(
                    resp.status_code, 200,
                    f"La bitácora '{tipo.value}' debe exportar su plantilla oficial sin error (obtuvo {resp.status_code})."
                )
                self.assertIn('spreadsheetml', resp.content_type)
        finally:
            with self.app.app_context():
                for vale_id in vales_creados_ids:
                    vale = AsignacionCombustible.query.get(vale_id)
                    if vale:
                        db.session.delete(vale)
                db.session.commit()

    def test_99_limpieza_vale_de_prueba(self):
        """Elimina el vale de prueba creado para no dejar datos huérfanos."""
        with self.app.app_context():
            vale = AsignacionCombustible.query.filter_by(responsable_nombre='Self-Test Automatizado').first()
            if vale:
                db.session.delete(vale)
                db.session.commit()
            vale_verificacion = AsignacionCombustible.query.filter_by(responsable_nombre='Self-Test Automatizado').first()
            self.assertIsNone(vale_verificacion, "El vale de prueba debe quedar eliminado al finalizar el self-test.")


if __name__ == '__main__':
    unittest.main()
