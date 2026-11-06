# -*- coding: utf-8 -*-
"""
Pruebas unitarias de la función PURA evaluar_registro() del Módulo de
Servicios Públicos (Control de Combustible). No requieren base de datos
ni Flask: evalúan directamente la lógica de negocio.

Ejecutar con: python -m unittest tests.test_combustible_logic -v
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.combustible_logic import evaluar_registro, obtener_umbrales_default, ROJO, AMARILLO


def _colores(alertas):
    return [a['color'] for a in alertas]


class TestEvaluarRegistro(unittest.TestCase):

    def test_registro_perfecto_sin_alertas(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 1100,
            'litros': 10, 'capacidad_tanque': 60,
            'tanque_lleno': True, 'foto_vale': 'vale.jpg',
            'folio_vale': 'ABC-001'
        }
        alertas = evaluar_registro(reg, {})
        self.assertEqual(alertas, [])

    def test_km_actual_menor_al_anterior_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 900,
            'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'ABC-002'
        }
        alertas = evaluar_registro(reg, {})
        self.assertIn(ROJO, _colores(alertas))
        self.assertTrue(any('kilómetro actual' in a['mensaje'] for a in alertas))

    def test_horometro_actual_menor_al_anterior_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'MAQUINARIA',
            'horometro_anterior': 500, 'horometro_actual': 480,
            'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'MAQ-001'
        }
        alertas = evaluar_registro(reg, {})
        self.assertIn(ROJO, _colores(alertas))
        self.assertTrue(any('horómetro actual' in a['mensaje'] for a in alertas))

    def test_km_igual_con_carga_nueva_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 1000,
            'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'ABC-003'
        }
        alertas = evaluar_registro(reg, {})
        self.assertIn(ROJO, _colores(alertas))

    def test_litros_mayores_a_capacidad_tanque_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'litros': 80, 'capacidad_tanque': 60,
            'foto_vale': 'vale.jpg', 'folio_vale': 'ABC-004'
        }
        alertas = evaluar_registro(reg, {})
        self.assertIn(ROJO, _colores(alertas))
        self.assertTrue(any('capacidad del tanque' in a['mensaje'] for a in alertas))

    def test_sin_foto_vale_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'OFICIAL', 'litros': 10,
            'foto_vale': None, 'folio_vale': 'ABC-005'
        }
        alertas = evaluar_registro(reg, {})
        self.assertIn(ROJO, _colores(alertas))
        self.assertTrue(any('foto' in a['mensaje'].lower() for a in alertas))

    def test_foranea_sin_ticket_ni_factura_genera_alerta_roja(self):
        reg = {
            'tipo_bitacora': 'FORANEA', 'litros': 10,
            'foto_vale': 'vale.jpg', 'folio_vale': 'FOR-001',
            'tiene_factura': 'NINGUNO'
        }
        alertas = evaluar_registro(reg, {})
        mensajes = [a['mensaje'] for a in alertas]
        self.assertTrue(any('ticket o la factura' in m for m in mensajes))

    def test_foranea_con_ticket_no_genera_esa_alerta(self):
        reg = {
            'tipo_bitacora': 'FORANEA', 'litros': 10,
            'foto_vale': 'vale.jpg', 'folio_vale': 'FOR-002',
            'tiene_factura': 'TICKET'
        }
        alertas = evaluar_registro(reg, {})
        mensajes = [a['mensaje'] for a in alertas]
        self.assertFalse(any('ticket o la factura' in m for m in mensajes))

    def test_folio_faltante_genera_alerta_roja(self):
        reg = {'tipo_bitacora': 'OFICIAL', 'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': ''}
        alertas = evaluar_registro(reg, {})
        self.assertTrue(any('folio' in a['mensaje'].lower() for a in alertas))

    def test_folio_repetido_genera_alerta_roja(self):
        reg = {'tipo_bitacora': 'OFICIAL', 'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'DUP-001'}
        alertas = evaluar_registro(reg, {'folio_repetido': True})
        self.assertTrue(any('ya fue utilizado' in a['mensaje'] for a in alertas))

    def test_rendimiento_bajo_mediana_con_tanque_lleno_y_aprendizaje_genera_amarillo(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 1040,  # 40 km
            'litros': 10,  # 4 km/L (muy bajo)
            'tanque_lleno': True,
            'foto_vale': 'vale.jpg', 'folio_vale': 'RND-001'
        }
        contexto = {'mediana_rendimiento_unidad': 10.0, 'cargas_previas_unidad': 6}
        alertas = evaluar_registro(reg, contexto)
        self.assertIn(AMARILLO, _colores(alertas))
        self.assertTrue(any('rendimiento' in a['mensaje'].lower() for a in alertas))

    def test_rendimiento_bajo_sin_suficientes_cargas_aprendizaje_no_genera_alerta(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 1040,
            'litros': 10, 'tanque_lleno': True,
            'foto_vale': 'vale.jpg', 'folio_vale': 'RND-002'
        }
        contexto = {'mediana_rendimiento_unidad': 10.0, 'cargas_previas_unidad': 2}
        alertas = evaluar_registro(reg, contexto)
        self.assertFalse(any('rendimiento' in a['mensaje'].lower() for a in alertas))

    def test_rendimiento_bajo_sin_tanque_lleno_no_genera_alerta(self):
        reg = {
            'tipo_bitacora': 'OFICIAL',
            'km_anterior': 1000, 'km_actual': 1040,
            'litros': 10, 'tanque_lleno': False,
            'foto_vale': 'vale.jpg', 'folio_vale': 'RND-003'
        }
        contexto = {'mediana_rendimiento_unidad': 10.0, 'cargas_previas_unidad': 6}
        alertas = evaluar_registro(reg, contexto)
        self.assertFalse(any('rendimiento' in a['mensaje'].lower() for a in alertas))

    def test_dos_cargas_en_menos_de_dos_dias_genera_amarillo(self):
        reg = {'tipo_bitacora': 'OFICIAL', 'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'DIA-001'}
        alertas = evaluar_registro(reg, {'dias_desde_ultima_carga_unidad': 1})
        self.assertIn(AMARILLO, _colores(alertas))

    def test_precio_litro_40_porciento_fuera_de_promedio_genera_amarillo(self):
        reg = {
            'tipo_bitacora': 'FORANEA', 'litros': 10, 'foto_vale': 'vale.jpg',
            'folio_vale': 'PRE-001', 'tiene_factura': 'TICKET',
            'precio_por_litro': 35.0
        }
        alertas = evaluar_registro(reg, {'promedio_precio_litro': 24.5})
        self.assertIn(AMARILLO, _colores(alertas))

    def test_ciudadano_con_apoyo_reciente_genera_amarillo(self):
        reg = {
            'tipo_bitacora': 'CIUDADANO', 'litros': 10,
            'foto_vale': 'vale.jpg', 'folio_vale': 'CIU-001'
        }
        alertas = evaluar_registro(reg, {'dias_desde_ultimo_apoyo_ciudadano': 10})
        self.assertIn(AMARILLO, _colores(alertas))

    def test_sin_foto_tablero_por_mas_de_30_dias_genera_amarillo(self):
        reg = {'tipo_bitacora': 'OFICIAL', 'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'TAB-001'}
        alertas = evaluar_registro(reg, {'dias_desde_ultima_foto_tablero': 45})
        self.assertIn(AMARILLO, _colores(alertas))

    def test_umbrales_personalizados_se_respetan(self):
        umbrales = obtener_umbrales_default()
        umbrales['dias_min_entre_cargas'] = 5
        reg = {'tipo_bitacora': 'OFICIAL', 'litros': 10, 'foto_vale': 'vale.jpg', 'folio_vale': 'UMB-001'}
        # 3 días es menor al umbral personalizado de 5 -> debe alertar
        alertas = evaluar_registro(reg, {'dias_desde_ultima_carga_unidad': 3, 'umbrales': umbrales})
        self.assertIn(AMARILLO, _colores(alertas))

    def test_nunca_lanza_excepcion_con_datos_vacios(self):
        try:
            alertas = evaluar_registro({}, {})
        except Exception as e:
            self.fail(f'evaluar_registro no debe lanzar excepciones nunca: {e}')
        self.assertIsInstance(alertas, list)

    def test_nunca_lanza_excepcion_con_datos_corruptos(self):
        reg = {'litros': 'no-es-numero', 'km_anterior': 'abc', 'km_actual': None}
        try:
            alertas = evaluar_registro(reg, {})
        except Exception as e:
            self.fail(f'evaluar_registro no debe lanzar excepciones con datos corruptos: {e}')
        self.assertIsInstance(alertas, list)


if __name__ == '__main__':
    unittest.main()
