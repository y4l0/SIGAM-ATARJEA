# GUÍA DE INSTALACIÓN EN UNA NUEVA LAPTOP — SIGEM Atarjea

Este documento está escrito para que puedas copiarlo y pegarlo como
instrucciones a otro asistente de IA (Gemini, ChatGPT, Claude, etc.) o
seguirlo tú mismo paso a paso, sin que se "invente" rutas ni asuma
nada que no esté aquí confirmado contra el código real del sistema.

## 0. QUÉ ES ESTE SISTEMA (contexto para el asistente)

SIGEM es una aplicación web **Flask + SQLite**, 100% portable (sin
dependencias de servidor externo, sin Docker, sin nube). Corre con
`python run.py` y se accede desde el navegador en
`http://127.0.0.1:5000`. Toda la lógica vive en la carpeta `app/`;
`run.py` es el único punto de entrada.

## 1. REQUISITOS PREVIOS EN LA LAPTOP DESTINO

- **Python 3.10 o superior** instalado (verificar con `python --version`
  en una terminal). Si no está instalado, descargarlo de
  https://www.python.org/downloads/ y marcar la casilla "Add Python to
  PATH" durante la instalación en Windows.
- **NO requiere** internet para funcionar (Bootstrap, FontAwesome,
  Chart.js y Flatpickr están vendorizados localmente en
  `static/vendor/`), excepto para la fuente Google Roboto (tiene
  fallback) y el login opcional con Google OAuth.
- **NO requiere** PostgreSQL, MySQL, Redis ni ningún otro servicio
  externo: la base de datos es un único archivo SQLite
  (`database/apoyos.db`) que se crea solo.

## 2. COPIAR EL PROYECTO

Copiar la carpeta completa `Sistema_Apoyos_Municipales` a la nueva
laptop (USB, red compartida, o `git clone` si está en un repositorio).

⚠️ **NO copiar** (si existieran) las carpetas `venv/`, `build/`,
`dist/`, `__pycache__/` ni `.pytest_cache/`: son específicas de cada
máquina/instalación y se regeneran automáticamente. Si ya las copiaste
sin querer, bórralas antes de empezar:
```powershell
Remove-Item -Recurse -Force venv, build, dist, __pycache__, .pytest_cache -ErrorAction SilentlyContinue
```

## 3. CREAR EL ENTORNO VIRTUAL E INSTALAR DEPENDENCIAS

Abrir PowerShell **dentro de la carpeta del proyecto** y ejecutar:

```powershell
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### ⚠️ FALLA ANTICIPADA #1: `xlsxwriter` o `pillow` faltantes
`requirements.txt` YA incluye `xlsxwriter==3.3.0` y `pillow==12.2.0`
(dependencias reales usadas por `app/routes.py` y `app/pdf_utils.py`
que en versiones anteriores del proyecto faltaban en este archivo y
causaban un error 500 silencioso al generar reportes Excel/PDF). Si
por alguna razón el `pip install` falla específicamente en uno de
estos dos paquetes, instálalos manualmente:
```powershell
pip install xlsxwriter pillow
```

### ⚠️ FALLA ANTICIPADA #2: `python-magic-bin` en Windows
`python-magic-bin` (detección de tipo MIME de archivos subidos) solo
aplica a Windows (`platform_system == "Windows"` en requirements.txt).
En Linux/macOS, pip instalará automáticamente `python-magic` en su
lugar — esto es correcto y no requiere intervención.

## 4. VERIFICAR LA INSTALACIÓN ANTES DE ARRANCAR (opcional pero recomendado)

```powershell
python -c "import flask, flask_login, flask_sqlalchemy, flask_wtf, authlib, pandas, openpyxl, xlsxwriter, reportlab, fpdf, PIL, requests; print('TODOS LOS IMPORTS OK')"
```
Si esto imprime `TODOS LOS IMPORTS OK` sin errores, la instalación de
dependencias es correcta.

## 5. PRIMER ARRANQUE

```powershell
python run.py
```

### Qué debe aparecer en consola (salida esperada y normal):
```
SQLite configurado en modo WAL para concurrencia optimizada
========================================================
  SISTEMA INTEGRAL DE GESTIÓN MUNICIPAL - ATARJEA
  Dirección de Desarrollo Social y Económico
========================================================
[INFO] Usuarios y dependencias verificados/creados automáticamente
[INFO] Catálogo de vehículos/operadores y costo de combustible verificados/creados
[INFO] Vehículos genéricos/inventados de pruebas anteriores depurados (si existían)
[INFO] Padrón real del parque vehicular municipal verificado/importado
[INFO] Catálogos FASE 2 ... verificados/creados
[INFO] Tanque Principal (Gasolina/Diésel/Urea) en 0.0 L: auto-relleno deshabilitado, operación municipal limpia

[INFO] MODO: PRODUCCIÓN
[INFO] ACCESO: http://127.0.0.1:5000
[INFO] DATOS: <ruta>\database\apoyos.db
[INFO] ARCHIVOS: <ruta>\static\uploads

[INFO] Iniciando servidor... (Ctrl+C para detener)
 * Serving Flask app 'app'
 * Running on http://127.0.0.1:5000
```

Esto significa que: (a) la base de datos se creó/verificó sola, (b)
los 5 usuarios oficiales ya existen, (c) el catálogo de vehículos y
combustible se pobló desde `data_flota_municipal.json`, y (d) el
inventario de combustible queda en 0.0 L REAL (no se rellena solo:
debe capturarse el primer abasto real desde el panel de Servicios
Públicos).

### ⚠️ FALLA ANTICIPADA #3: "unable to open database file"
Puede aparecer brevemente al primer arranque en Windows si SQLite
compite por el archivo con otro proceso. **No es un error real**: el
sistema sigue funcionando. Si persiste, verificar permisos de
escritura en la carpeta `database/` (clic derecho → Propiedades →
Seguridad → permitir escritura al usuario actual).

### ⚠️ FALLA ANTICIPADA #4: el puerto 5000 ya está en uso
Si aparece `OSError: [WinError 10048]` o similar, otro proceso (u otra
instancia de `run.py`) ya está usando el puerto 5000. Ciérralo:
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```
y vuelve a ejecutar `python run.py`.

## 6. ACCEDER AL SISTEMA

Abrir el navegador en: **http://127.0.0.1:5000**

Credenciales de acceso (ver detalle completo en
`CREDENCIALES_SISTEMA.md`):
- **Admin / Alcalde**: `admin@atarjea.gob.mx` / `admin`
- **Servicios Públicos**: `serviciospublicosAtarjea@gmail.com` / `serviciospublicos`

## 7. PRUEBA DE HUMO (confirmar que todo funciona de verdad)

Con el entorno virtual activado y el servidor **detenido**, ejecutar la
suite de pruebas automatizadas:
```powershell
python -m pytest tests/ -v
```
Debe mostrar algo como `XX passed` sin ningún `FAILED`. Esta suite
simula login, creación de vales de combustible, generación de PDF y
Excel, y accesos por rol — es la forma más rápida de confirmar que la
instalación quedó 100% funcional antes de usarla con datos reales.

## 8. LIMPIEZA PARA OPERACIÓN REAL (si se va a usar en producción desde cero)

Si la laptop destino es para operación real municipal (no para
pruebas), ejecutar una sola vez, con el servidor detenido:
```powershell
python purgar_pruebas_servicios_publicos.py
```
Esto garantiza que el inventario de combustible, vales y bitácoras
queden en cero absoluto, listos para que el primer registro sea 100%
real (no hay ningún dato de ejemplo oculto).

## 9. DEJAR EL SISTEMA CORRIENDO PERMANENTEMENTE (opcional)

Para producción real de forma continua (no solo pruebas), lo más
simple en Windows es crear un acceso directo que ejecute:
```
<ruta_al_venv>\Scripts\python.exe <ruta_del_proyecto>\run.py
```
y colocarlo en la carpeta de inicio de Windows
(`shell:startup` en el Explorador de archivos) si se desea que arranque
solo. Para que otras computadoras de la red local puedan acceder por
la IP de esta laptop (en vez de solo `127.0.0.1`), definir la variable
de entorno `FLASK_HOST=0.0.0.0` antes de ejecutar `run.py` (ver
`configurar_entorno_produccion()` en `run.py`, que lee `FLASK_HOST` y
`FLASK_PORT` del entorno con `127.0.0.1:5000` como valores por defecto):
```powershell
$env:FLASK_HOST = "0.0.0.0"
python run.py
```

## 10. GENERAR EL EJECUTABLE PORTABLE (.exe) — OPCIONAL

Si se requiere un `.exe` autocontenido (sin necesidad de Python
instalado en la computadora final):
```powershell
pip install pyinstaller
python build_exe.py
```
El ejecutable y todos sus archivos de soporte se generan en `dist/`.
Copiar esa carpeta completa a la computadora destino.

---

## RESUMEN PARA COPIAR Y PEGAR A UN ASISTENTE DE IA

> Tengo el proyecto SIGEM (Flask + SQLite) copiado en esta laptop
> Windows. Necesito: 1) crear un entorno virtual con
> `python -m venv venv` y activarlo, 2) instalar
> `pip install -r requirements.txt` (ya incluye xlsxwriter y pillow,
> no asumas que faltan), 3) ejecutar `python run.py` desde la raíz del
> proyecto, 4) confirmar que la consola muestra "Iniciando servidor..."
> sin ningún traceback de Python, 5) abrir
> http://127.0.0.1:5000 y entrar con admin@atarjea.gob.mx / admin,
> 6) correr `python -m pytest tests/ -v` con el servidor detenido para
> confirmar que todo pasa. Si algo falla, dime el traceback EXACTO
> antes de proponer una solución; no inventes rutas ni nombres de
> archivos que no veas en el error real.
