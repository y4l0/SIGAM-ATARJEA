#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
purgar_pruebas_servicios_publicos.py

ORDEN DE EJECUCIÓN CRÍTICA (punto 3): PURGA LIMPIA DE REGISTROS DE PRUEBA.

Elimina PERMANENTEMENTE todos los registros de prueba generados en el
Módulo de Servicios Públicos (Control de Combustible) antes de iniciar
las pruebas de campo reales con el personal:
  - Asignaciones de Combustible (Formulario N° 10): TODAS.
  - Bitácoras físicas de combustible (legado): TODAS.
  - Entradas de abasto al tanque municipal (RegistroAbasto y
    RegistroAbastoFluido - Gasolina/Diésel/Urea): TODAS.
  - Bitácora de sistema (hash encadenado) asociada al módulo de
    combustible: se reinicia para evitar referencias a folios ya
    eliminados.

NO TOCA: usuarios, catálogos reales (Unidad/Equipo/Conductor/
Autorizador/Despachador/Area/Gasolinera), ni ningún dato del módulo de
Apoyos Ciudadanos (Solicitud/Ciudadano), que es un módulo independiente.

Tras ejecutar este script, el inventario de los tanques queda en
0.0 L (sin registros de abasto de prueba). ORDEN TÉCNICA MAESTRA
(VACIADO A CEROS): a diferencia de versiones anteriores, `run.py` ya
NO repone automáticamente ningún abasto inicial al arrancar; el
Tanque Principal (Gasolina, Diésel y Urea) permanecerá en 0.0 L hasta
que el personal de Servicios Públicos registre el primer abasto REAL
desde el panel, dejando la operación municipal completamente limpia
para las pruebas de campo.

Uso:
    python purgar_pruebas_servicios_publicos.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import (
    AsignacionCombustible, BitacoraCombustible, RegistroAbasto,
    RegistroAbastoFluido, BitacoraSistemaLog, ConfiguracionTanque,
)


def purgar_registros_prueba():
    """Ejecuta la purga completa del módulo de combustible dentro del
    contexto de la aplicación Flask (obligatorio para SQLAlchemy)."""
    app = create_app()
    with app.app_context():
        try:
            total_asignaciones = AsignacionCombustible.query.delete()
            total_bitacoras = BitacoraCombustible.query.delete()
            total_abasto = RegistroAbasto.query.delete()
            total_abasto_fluido = RegistroAbastoFluido.query.delete()
            total_bitacora_sistema = BitacoraSistemaLog.query.delete()

            # Deja los tanques configurados (capacidad) pero sin litros de
            # prueba: al borrarse las entradas de abasto,
            # calcular_estado_multitanque() ya reporta 0 L disponibles
            # automáticamente para cada fluido. ORDEN TÉCNICA MAESTRA
            # (VACIADO A CEROS): además, restaura el Tanque 1 como
            # Principal y el Tanque 2 como Secundario en los 3 fluidos,
            # deshaciendo cualquier rotación automática heredada de
            # pruebas anteriores, para iniciar la operación municipal
            # 100% limpia.
            total_tanques_reset = 0
            for tanque in ConfiguracionTanque.query.all():
                tanque.fecha_actualizacion = None
                tanque.es_principal = (tanque.numero_tanque == 1)
                total_tanques_reset += 1

            db.session.commit()

            print("=" * 70)
            print("  PURGA DE DATOS DE PRUEBA - MÓDULO DE SERVICIOS PÚBLICOS")
            print("=" * 70)
            print(f"  Asignaciones de Combustible eliminadas:     {total_asignaciones}")
            print(f"  Bitácoras físicas (legado) eliminadas:      {total_bitacoras}")
            print(f"  Entradas de abasto (legado) eliminadas:     {total_abasto}")
            print(f"  Entradas de abasto multifluido eliminadas:  {total_abasto_fluido}")
            print(f"  Eventos de bitácora de sistema eliminados:  {total_bitacora_sistema}")
            print(f"  Configuraciones de tanque reiniciadas:      {total_tanques_reset}")
            print("=" * 70)
            print("  Los tanques quedaron en 0.0 L REAL y PERMANENTE. El sistema")
            print("  ya NO repone litros automáticamente al reiniciar run.py: el")
            print("  inventario queda listo para que el primer abasto de campo")
            print("  sea 100% real.")
            print("=" * 70)
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] No se pudo completar la purga: {str(e)}")
            raise


if __name__ == "__main__":
    purgar_registros_prueba()
