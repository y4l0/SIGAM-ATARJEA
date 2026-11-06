#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de construcción para PyInstaller - Sistema Integral de Gestión Municipal (SIGEM)
Municipio de Atarjea, Querétaro

Este script genera un ejecutable portable del sistema SIGEM que incluye:
- Aplicación Flask completa
- Base de datos SQLite
- Archivos estáticos (CSS, JS, imágenes)
- Plantillas HTML
- Dependencias necesarias
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

def crear_estructura_portable(directorio_base):
    """Crea la estructura de directorios para la aplicación portable"""
    print("Creando estructura de directorios portable...")
    
    # Directorios necesarios
    directorios = [
        'database',
        'logs',
        'static/uploads/identificaciones',
        'static/uploads/comprobantes',
        'static/uploads/evidencias',
        'static/css',
        'static/js',
        'static/img',
        'templates',
        'backups'
    ]
    
    for directorio in directorios:
        ruta_completa = os.path.join(directorio_base, directorio)
        os.makedirs(ruta_completa, exist_ok=True)
        print(f"  ✓ {directorio}")
    
    return directorio_base

def copiar_archivos_esenciales(origen, destino):
    """Copia los archivos esenciales del sistema al directorio portable"""
    print("\nCopiando archivos esenciales...")
    
    # Archivos principales
    archivos_principales = [
        'run.py',
        'config.py',
        'requirements.txt',
        'inicializar_sistema.py',
        'crear_db.py',
        'app/__init__.py',
        'app/models.py',
        'app/routes.py',
        'app/logger_config.py',
        'app/db_utils.py',
        'app/auth_utils.py',
        'app/pdf_utils.py',
        'app/decorators.py',
        'app/upload_utils.py',
        'app/services.py',
        'app/forms.py'
    ]
    
    for archivo in archivos_principales:
        origen_path = os.path.join(origen, archivo)
        destino_path = os.path.join(destino, archivo)
        
        if os.path.exists(origen_path):
            # Crear directorio de destino si no existe
            os.makedirs(os.path.dirname(destino_path), exist_ok=True)
            shutil.copy2(origen_path, destino_path)
            print(f"  ✓ {archivo}")
    
    # Copiar plantillas
    print("\nCopiando plantillas HTML...")
    templates_origen = os.path.join(origen, 'templates')
    templates_destino = os.path.join(destino, 'templates')
    
    if os.path.exists(templates_origen):
        shutil.copytree(templates_origen, templates_destino, dirs_exist_ok=True)
        print(f"  ✓ templates/ ({len(os.listdir(templates_origen))} archivos)")
    
    # Copiar archivos estáticos
    print("\nCopiando archivos estáticos...")
    static_origen = os.path.join(origen, 'static')
    static_destino = os.path.join(destino, 'static')
    
    if os.path.exists(static_origen):
        shutil.copytree(static_origen, static_destino, dirs_exist_ok=True)
        print(f"  ✓ static/ (CSS, JS, imágenes)")
    
    # Copiar base de datos inicial
    print("\nCopiando base de datos inicial...")
    db_origen = os.path.join(origen, 'database', 'apoyos.db')
    db_destino = os.path.join(destino, 'database', 'apoyos.db')
    
    if os.path.exists(db_origen):
        shutil.copy2(db_origen, db_destino)
        print(f"  ✓ database/apoyos.db")
    else:
        print(f"  ⚠ database/apoyos.db no encontrado, se creará al inicializar")

def generar_especificacion_pyinstaller(directorio_trabajo):
    """Genera el archivo .spec para PyInstaller"""
    print("\nGenerando archivo de especificación para PyInstaller...")
    
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Añadir el directorio de trabajo al path
sys.path.append(r'{directorio_trabajo}')

block_cipher = None

# Archivos de datos adicionales
datas = []

# Archivos estáticos
static_files = [
    ('static', 'static'),
    ('templates', 'templates'),
    ('database', 'database'),
    ('logs', 'logs'),
    ('backups', 'backups')
]

for src, dst in static_files:
    src_path = os.path.join(r'{directorio_trabajo}', src)
    if os.path.exists(src_path):
        if os.path.isdir(src_path):
            for root, dirs, files in os.walk(src_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, src_path)
                    datas.append((file_path, os.path.join(dst, rel_path)))
        else:
            datas.append((src_path, dst))

# Hooks para Flask y dependencias
hiddenimports = [
    'flask',
    'flask_sqlalchemy',
    'flask_login',
    'werkzeug.security',
    'sqlalchemy',
    'sqlalchemy.ext',
    'sqlalchemy.dialects.sqlite',
    'reportlab',
    'reportlab.pdfgen',
    'reportlab.lib',
    'reportlab.pdfbase',
    'reportlab.pdfbase.ttfonts',
    'PIL',
    'PIL.Image',
    'PIL.ImageFile',
    'PIL.ImageOps',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'jinja2',
    'jinja2.ext',
    'wtforms',
    'wtforms.fields',
    'wtforms.validators',
    'wtforms.widgets',
    'email_validator',
    'chardet',
    'cryptography',
    'cryptography.hazmat',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.primitives',
    'cryptography.x509',
    'markupsafe',
    'itsdangerous',
    'click',
    'blinker',
    'colorama'
]

# Configuración principal
a = Analysis(
    ['run.py'],
    pathex=[r'{directorio_trabajo}'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1
)

# Configuración del ejecutable
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SIGEM_Sistema_Apoyos_Municipales',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Cambiar a False para ocultar la consola en producción
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(r'{directorio_trabajo}', 'static', 'img', 'favicon.ico') if os.path.exists(os.path.join(r'{directorio_trabajo}', 'static', 'img', 'favicon.ico')) else None
)

# Configuración para empaquetado en un solo archivo
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SIGEM_Sistema_Apoyos_Municipales'
)
'''
    
    spec_path = os.path.join(directorio_trabajo, 'sigem.spec')
    with open(spec_path, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print(f"  ✓ Archivo spec generado: {spec_path}")
    return spec_path

def ejecutar_pyinstaller(directorio_trabajo, modo_onefile=True):
    """Ejecuta PyInstaller para generar el ejecutable"""
    print("\nEjecutando PyInstaller...")
    
    spec_path = os.path.join(directorio_trabajo, 'sigem.spec')
    
    if modo_onefile:
        comando = [
            'pyinstaller',
            '--onefile',
            '--name', 'SIGEM_Sistema_Apoyos_Municipales',
            '--add-data', f'{directorio_trabajo}/static;static',
            '--add-data', f'{directorio_trabajo}/templates;templates',
            '--add-data', f'{directorio_trabajo}/database;database',
            '--add-data', f'{directorio_trabajo}/logs;logs',
            '--add-data', f'{directorio_trabajo}/backups;backups',
            '--hidden-import', 'flask',
            '--hidden-import', 'flask_sqlalchemy',
            '--hidden-import', 'flask_login',
            '--hidden-import', 'werkzeug.security',
            '--hidden-import', 'sqlalchemy',
            '--hidden-import', 'reportlab',
            '--hidden-import', 'PIL',
            '--hidden-import', 'jinja2',
            '--hidden-import', 'wtforms',
            '--hidden-import', 'email_validator',
            '--hidden-import', 'chardet',
            '--hidden-import', 'cryptography',
            '--console',  # Cambiar a --windowed para ocultar consola
            '--icon', os.path.join(directorio_trabajo, 'static', 'img', 'favicon.ico') if os.path.exists(os.path.join(directorio_trabajo, 'static', 'img', 'favicon.ico')) else '',
            'run.py'
        ]
    else:
        comando = ['pyinstaller', spec_path]
    
    # Filtrar argumentos vacíos
    comando = [arg for arg in comando if arg]
    
    print(f"Comando: {' '.join(comando)}")
    
    try:
        resultado = subprocess.run(comando, cwd=directorio_trabajo, capture_output=True, text=True)
        
        if resultado.returncode == 0:
            print("✓ PyInstaller ejecutado exitosamente")
            print(f"Salida: {resultado.stdout[:500]}...")
            
            # Mostrar ubicación del ejecutable
            if modo_onefile:
                exe_path = os.path.join(directorio_trabajo, 'dist', 'SIGEM_Sistema_Apoyos_Municipales.exe')
            else:
                exe_path = os.path.join(directorio_trabajo, 'dist', 'SIGEM_Sistema_Apoyos_Municipales')
            
            if os.path.exists(exe_path):
                print(f"\n✓ Ejecutable generado: {exe_path}")
                print(f"  Tamaño: {os.path.getsize(exe_path) / (1024*1024):.2f} MB")
            else:
                print("⚠ Ejecutable no encontrado en la ubicación esperada")
                
        else:
            print(f"✗ Error en PyInstaller: {resultado.stderr}")
            
    except Exception as e:
        print(f"✗ Error ejecutando PyInstaller: {e}")

def crear_script_inicializacion(directorio_trabajo):
    """Crea un script de inicialización para el ejecutable"""
    print("\nCreando script de inicialización...")
    
    script_content = '''@echo off
echo ========================================
echo  SISTEMA INTEGRAL DE GESTIÓN MUNICIPAL
echo  Municipio de Atarjea, Querétaro
echo ========================================
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no está instalado o no está en el PATH.
    echo Por favor, instale Python 3.8 o superior.
    pause
    exit /b 1
)

REM Verificar si las dependencias están instaladas
echo Verificando dependencias...
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se pudieron instalar las dependencias.
    echo Asegúrese de tener pip instalado.
    pause
    exit /b 1
)

REM Inicializar base de datos si no existe
if not exist "database\\apoyos.db" (
    echo Inicializando base de datos...
    python inicializar_sistema.py
    if errorlevel 1 (
        echo ERROR: No se pudo inicializar la base de datos.
        pause
        exit /b 1
    )
)

REM Iniciar servidor
echo.
echo Iniciando servidor SIGEM...
echo.
echo Acceda al sistema en: http://127.0.0.1:5000
echo Usuario: admin@municipio.gob.mx
echo Contraseña: admin123
echo.
echo Presione Ctrl+C para detener el servidor.
echo.

python run.py

pause
'''
    
    script_path = os.path.join(directorio_trabajo, 'iniciar_sistema.bat')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"  ✓ Script de inicialización creado: {script_path}")
    
    # También crear versión para Linux/Mac
    script_sh_content = '''#!/bin/bash
echo "========================================"
echo " SISTEMA INTEGRAL DE GESTIÓN MUNICIPAL"
echo " Municipio de Atarjea, Querétaro"
echo "========================================"
echo ""

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no está instalado."
    echo "Por favor, instale Python 3.8 o superior."
    exit 1
fi

# Verificar si las dependencias están instaladas
echo "Verificando dependencias..."
pip3 install -r requirements.txt > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: No se pudieron instalar las dependencias."
    echo "Asegúrese de tener pip3 instalado."
    exit 1
fi

# Inicializar base de datos si no existe
if [ ! -f "database/apoyos.db" ]; then
    echo "Inicializando base de datos..."
    python3 inicializar_sistema.py
    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo inicializar la base de datos."
        exit 1
    fi
fi

# Iniciar servidor
echo ""
echo "Iniciando servidor SIGEM..."
echo ""
echo "Acceda al sistema en: http://127.0.0.1:5000"
echo "Usuario: admin@municipio.gob.mx"
echo "Contraseña: admin123"
echo ""
echo "Presione Ctrl+C para detener el servidor."
echo ""

python3 run.py
'''
    
    script_sh_path = os.path.join(directorio_trabajo, 'iniciar_sistema.sh')
    with open(script_sh_path, 'w', encoding='utf-8') as f:
        f.write(script_sh_content)
    
    # Hacer ejecutable el script de Linux/Mac
    try:
        import stat
        os.chmod(script_sh_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    except:
        pass
    
    print(f"  ✓ Script para Linux/Mac creado: {script_sh_path}")

def main():
    """Función principal"""
    print("=" * 60)
    print("  CONSTRUCTOR DE EJECUTABLE PORTABLE - SIGEM")
    print("  Sistema Integral de Gestión Municipal")
    print("  Municipio de Atarjea, Querétaro")
    print("=" * 60)
    
    # Directorio actual
    directorio_actual = os.path.dirname(os.path.abspath(__file__))
    
    # Crear directorio temporal para construcción
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"\nDirectorio temporal: {temp_dir}")
        
        # Crear estructura portable
        directorio_portable = crear_estructura_portable(temp_dir)
        
        # Copiar archivos esenciales
        copiar_archivos_esenciales(directorio_actual, directorio_portable)
        
        # Crear script de inicialización
        crear_script_inicializacion(directorio_portable)
        
        # Generar especificación de PyInstaller
        generar_especificacion_pyinstaller(directorio_portable)
        
        # Ejecutar PyInstaller
        ejecutar_pyinstaller(directorio_portable, modo_onefile=True)
        
        # Copiar el ejecutable al directorio actual
        exe_origen = os.path.join(directorio_portable, 'dist', 'SIGEM_Sistema_Apoyos_Municipales.exe')
        exe_destino = os.path.join(directorio_actual, 'SIGEM_Sistema_Apoyos_Municipales.exe')
        
        if os.path.exists(exe_origen):
            try:
                shutil.copy2(exe_origen, exe_destino)
                print(f"\n✓ Ejecutable copiado a: {exe_destino}")
            except Exception as e:
                print(f"⚠ No se pudo copiar el ejecutable: {e}")
        
        print("\n" + "=" * 60)
        print("  CONSTRUCCIÓN COMPLETADA")
        print("=" * 60)
        print("\nINSTRUCCIONES DE USO:")
        print("1. El ejecutable se encuentra en: SIGEM_Sistema_Apoyos_Municipales.exe")
        print("2. Para distribuir, copie todo el contenido de la carpeta 'dist'")
        print("3. Ejecute 'iniciar_sistema.bat' (Windows) o 'iniciar_sistema.sh' (Linux/Mac)")
        print("4. Acceda al sistema en: http://127.0.0.1:5000")
        print("5. Credenciales por defecto:")
        print("   - Usuario: admin@municipio.gob.mx")
        print("   - Contraseña: admin123")
        print("\nNOTA: Asegúrese de tener Python 3.8+ y las dependencias instaladas.")
        print("=" * 60)

if __name__ == '__main__':
    # Verificar que PyInstaller esté instalado
    try:
        import PyInstaller
        print("✓ PyInstaller está instalado")
    except ImportError:
        print("✗ PyInstaller no está instalado. Instalando...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
        print("✓ PyInstaller instalado correctamente")
    
    main()