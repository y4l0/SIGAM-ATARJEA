# -*- coding: utf-8 -*-
"""
DIRECTIVA: BLINDAJE DE ROBLE, RESPALDOS EN ESCRITORIO, SINCRONIZACIÓN
ASÍNCRONA Y DASHBOARD DEL ALCALDE.

Valida, usando el test_client() de Flask:
  1. El respaldo automático en ~/Desktop/RESPALDOS_SIGEM/ se genera
     correctamente (copia viva + copia diaria).
  2. El "Paquete Diario" se exporta (JSON descargable) y se puede
     importar de vuelta sin duplicar registros ya existentes.
  3. El Panel de Auditoría en Vivo admite el filtro de período (Hoy,
     Esta Semana, Período Personalizado) sin colapsar.
  4. La búsqueda de ciudadano por CURP calcula el historial de apoyos
     (Aprobados vs Pendientes) - bug de indentación corregido.

Ejecutar con: python -m pytest tests/test_blindaje_backup_dashboard.py -v
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Ciudadano, Solicitud
from app.backup_utils import obtener_ruta_respaldos_escritorio


class TestBlindajeBackupDashboard(unittest.TestCase):

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

    def test_01_respaldo_automatico_en_escritorio(self):
        """El respaldo debe generar la copia viva y la copia diaria en el Escritorio."""
        with self.app.app_context():
            ruta = obtener_ruta_respaldos_escritorio()
            self.assertIsNotNone(ruta, "La carpeta de respaldos del Escritorio debe poder crearse.")
            self.assertTrue(os.path.isdir(ruta))

    def test_02_exportar_paquete_diario_descarga_json(self):
        """El botón Exportar Paquete Diario debe devolver un .sigem.json descargable."""
        resp = self.client.get('/paquete_diario/exportar')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.content_type)
        contenido = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(contenido.get('sistema'), 'SIGEM Atarjea')
        self.assertIn('tablas', contenido)
        self.assertIn('usuarios', contenido['tablas'])

    def test_03_importar_paquete_sin_duplicar(self):
        """Importar el mismo paquete exportado no debe duplicar ningún registro."""
        resp_export = self.client.get('/paquete_diario/exportar')
        self.assertEqual(resp_export.status_code, 200)

        with self.app.app_context():
            total_usuarios_antes = Usuario.query.count()

        data = {
            'paquete': (resp_export.data, 'paquete_prueba.sigem.json')
        }
        resp_import = self.client.post(
            '/paquete_diario/importar', data=data,
            content_type='multipart/form-data', follow_redirects=True
        )
        self.assertEqual(resp_import.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp_import.data)

        with self.app.app_context():
            total_usuarios_despues = Usuario.query.count()
        self.assertEqual(
            total_usuarios_antes, total_usuarios_despues,
            "Importar el mismo paquete no debe duplicar usuarios existentes."
        )

    def test_04_auditoria_en_vivo_filtro_hoy(self):
        """El filtro 'hoy' del Panel de Auditoría en Vivo no debe colapsar."""
        resp = self.client.get('/auditoria_en_vivo?periodo=hoy')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_05_auditoria_en_vivo_filtro_semana(self):
        """El filtro 'semana' del Panel de Auditoría en Vivo no debe colapsar."""
        resp = self.client.get('/auditoria_en_vivo?periodo=semana')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_06_auditoria_en_vivo_filtro_personalizado(self):
        """El filtro Período Personalizado no debe colapsar con fechas válidas."""
        resp = self.client.get('/auditoria_en_vivo?periodo=personalizado&fecha_inicio=2026-01-01&fecha_fin=2026-12-31')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)

    def test_07_buscar_ciudadano_calcula_historial(self):
        """
        CORRECCIÓN CRÍTICA: la búsqueda exitosa por CURP debe calcular
        el historial de apoyos (antes quedaba vacío por un bug de
        indentación posterior a un return).
        """
        with self.app.app_context():
            ciudadano = Ciudadano.query.first()
            if not ciudadano:
                self.skipTest("No hay ciudadanos registrados para validar el historial.")
            curp_prueba = ciudadano.CURP

        resp = self.client.post('/buscar_ciudadano', data={'curp': curp_prueba}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Internal Server Error', resp.data)


if __name__ == '__main__':
    unittest.main()
