# -*- coding: utf-8 -*-
"""
tests/test_sanidad_datos.py

AUDITORÍA PROACTIVA Y SELF-TEST INTEGRAL DE SANIDAD DE DATOS - SIGEM
Atarjea.

Este módulo valida, de forma preventiva y SIN modificar datos reales
del sistema (solo lectura + limpieza idempotente de sus propios
registros de prueba):

  1. INTEGRIDAD REFERENCIAL: las tablas críticas existen y responden a
     PRAGMA integrity_check sin reportar corrupción.
  2. EXISTENCIA DE TABLAS CRÍTICAS: todas las tablas que el sistema
     necesita para operar (usuarios, dependencias, solicitudes,
     ciudadanos, auditoria, asignaciones_combustible, adjuntos, etc.)
     existen en la base de datos activa.
  3. PREVENCIÓN DE PÉRDIDA DE DATOS ANTE FALLOS DE SESIÓN: una
     excepción deliberada a mitad de una transacción NUNCA debe dejar
     registros a medio escribir (rollback real verificado) ni afectar
     la siguiente operación sobre la misma sesión.
  4. MÓDULO DE SINCRONIZACIÓN/RECUPERACIÓN: las utilidades de
     diagnóstico, listado de respaldos y fusión de bases de datos
     (app/db_sync.py) están disponibles y no lanzan excepciones ante
     escenarios de entrada inválida.

Ejecutar con: python -m pytest tests/test_sanidad_datos.py -v
"""
import os
import sys
import sqlite3
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import (
    Usuario, Dependencia, Comunidad, Ciudadano, Solicitud, AdjuntoSolicitud,
    AuditoriaLog, AsignacionCombustible, AdjuntoAsignacionCombustible,
    BitacoraCombustible, RegistroAbasto,
)
from app.db_utils import transaccion_segura
from app.db_sync import (
    verificar_integridad_bd_local, listar_respaldos_disponibles,
    restaurar_desde_respaldo, fusionar_bases_de_datos,
)


TABLAS_CRITICAS = [
    'usuarios', 'dependencias', 'comunidades', 'ciudadanos', 'solicitudes',
    'adjuntos_solicitud', 'auditoria_logs', 'asignaciones_combustible',
    'adjuntos_asignacion_combustible', 'bitacoras_combustible',
    'registros_abasto',
]


class TestSanidadDatos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.rollback()
        self.app_context.pop()

    # ---------------- REQUERIMIENTO 1: INTEGRIDAD REFERENCIAL ----------------

    def test_01_base_de_datos_pasa_integrity_check(self):
        """La base de datos activa debe pasar PRAGMA integrity_check sin reportar corrupción."""
        diagnostico = verificar_integridad_bd_local()
        self.assertTrue(diagnostico['existe'], "La base de datos activa debe existir.")
        self.assertTrue(diagnostico['integra'], f"La base de datos reportó un problema de integridad: {diagnostico['detalle']}")

    def test_02_base_de_datos_no_esta_vacia_ni_en_cero(self):
        """BLINDAJE CONTRA BORRADOS: el archivo activo nunca debe quedar en 0 bytes
        o sospechosamente pequeño tras un arranque normal del sistema."""
        diagnostico = verificar_integridad_bd_local()
        self.assertGreaterEqual(
            diagnostico['tamano_bytes'], 1024,
            "La base de datos está sospechosamente vacía/pequeña (posible inicialización en 0 tras un despliegue limpio)."
        )

    # ---------------- REQUERIMIENTO 2: EXISTENCIA DE TABLAS CRÍTICAS ----------------

    def test_03_todas_las_tablas_criticas_existen(self):
        """Todas las tablas que el sistema necesita para operar deben existir en la base de datos activa."""
        uri = self.app.config['SQLALCHEMY_DATABASE_URI']
        ruta_db = uri.replace('sqlite:///', '', 1)
        self.assertTrue(os.path.exists(ruta_db), "El archivo de base de datos activo debe existir en disco.")

        conn = sqlite3.connect(ruta_db)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas_existentes = {fila[0] for fila in cursor.fetchall()}
        finally:
            conn.close()

        for tabla in TABLAS_CRITICAS:
            self.assertIn(
                tabla, tablas_existentes,
                f"La tabla crítica '{tabla}' no existe en la base de datos activa."
            )

    def test_04_modelos_criticos_son_consultables_sin_colapsar(self):
        """Cada modelo crítico debe poder consultarse sin lanzar una excepción, incluso si está vacío."""
        modelos = [
            Usuario, Dependencia, Comunidad, Ciudadano, Solicitud, AdjuntoSolicitud,
            AuditoriaLog, AsignacionCombustible, AdjuntoAsignacionCombustible,
            BitacoraCombustible, RegistroAbasto,
        ]
        for Modelo in modelos:
            total = Modelo.query.count()
            self.assertGreaterEqual(total, 0, f"El modelo {Modelo.__name__} debe ser consultable sin colapsar.")

    def test_05_columnas_nuevas_de_asignacion_combustible_existen(self):
        """Las columnas de unificación (Tipo de Beneficiario, desglose de
        montos, Monto Estimado) deben existir en 'asignaciones_combustible'
        tras la migración automática de app/__init__.py."""
        uri = self.app.config['SQLALCHEMY_DATABASE_URI']
        ruta_db = uri.replace('sqlite:///', '', 1)
        conn = sqlite3.connect(ruta_db)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(asignaciones_combustible)")
            columnas = {fila[1] for fila in cursor.fetchall()}
        finally:
            conn.close()

        columnas_esperadas = [
            'tipo_beneficiario', 'monto_federal', 'monto_estatal',
            'monto_municipal', 'monto_beneficiario', 'monto_general', 'monto_estimado',
        ]
        for columna in columnas_esperadas:
            self.assertIn(columna, columnas, f"La columna '{columna}' debe existir en 'asignaciones_combustible'.")

    # ---------------- REQUERIMIENTO 3: PREVENCIÓN DE PÉRDIDA DE DATOS ----------------

    def test_06_transaccion_segura_hace_rollback_ante_excepcion(self):
        """Una excepción deliberada a mitad de una transacción NUNCA debe
        dejar un registro parcialmente escrito en la base de datos."""
        dep_temporal = Dependencia.query.filter_by(nombre='TEST_SANIDAD_ROLLBACK').first()
        if dep_temporal:
            db.session.delete(dep_temporal)
            db.session.commit()

        with self.assertRaises(ValueError):
            with transaccion_segura("prueba de rollback de sanidad de datos"):
                db.session.add(Dependencia(nombre='TEST_SANIDAD_ROLLBACK'))
                db.session.flush()
                raise ValueError("Fallo deliberado para probar el rollback automático")

        existente = Dependencia.query.filter_by(nombre='TEST_SANIDAD_ROLLBACK').first()
        self.assertIsNone(existente, "La transacción fallida NO debe dejar el registro a medio escribir.")

    def test_07_sesion_se_mantiene_utilizable_tras_un_rollback(self):
        """Tras un rollback, la sesión de SQLAlchemy debe seguir siendo
        utilizable para una operación nueva (sin quedar 'contaminada')."""
        try:
            with transaccion_segura("prueba de sesión tras rollback"):
                db.session.add(Dependencia(nombre='TEST_SANIDAD_SESION_A'))
                raise RuntimeError("Fallo deliberado")
        except RuntimeError:
            pass

        dep_control = Dependencia.query.filter_by(nombre='TEST_SANIDAD_SESION_B').first()
        if not dep_control:
            dep_control = Dependencia(nombre='TEST_SANIDAD_SESION_B')
            db.session.add(dep_control)
            db.session.commit()

        self.assertIsNotNone(
            Dependencia.query.filter_by(nombre='TEST_SANIDAD_SESION_B').first(),
            "La sesión debe seguir siendo utilizable después de un rollback previo."
        )

        Dependencia.query.filter_by(nombre='TEST_SANIDAD_SESION_B').delete(synchronize_session=False)
        db.session.commit()

    # ---------------- REQUERIMIENTO 4: MÓDULO DE SINCRONIZACIÓN/RECUPERACIÓN ----------------

    def test_08_listar_respaldos_disponibles_nunca_colapsa(self):
        """listar_respaldos_disponibles() debe retornar siempre una lista,
        incluso si la carpeta de respaldos no existe."""
        respaldos = listar_respaldos_disponibles()
        self.assertIsInstance(respaldos, list)

    def test_09_restaurar_desde_respaldo_inexistente_no_colapsa(self):
        """Pedir restaurar un respaldo que no existe debe retornar un
        resultado controlado (exito=False), nunca lanzar una excepción."""
        resultado = restaurar_desde_respaldo('C:/ruta/que/no/existe/falso.db')
        self.assertFalse(resultado['exito'])
        self.assertTrue(len(resultado['mensaje']) > 0)

    def test_10_fusionar_bases_de_datos_archivo_inexistente_no_colapsa(self):
        """Fusionar un archivo .db que no existe debe retornar un resultado
        controlado con error descrito, nunca lanzar una excepción."""
        resumen = fusionar_bases_de_datos('C:/ruta/que/no/existe/externa.db')
        self.assertFalse(resumen['exito'])
        self.assertIsNotNone(resumen['error'])


if __name__ == '__main__':
    unittest.main()
