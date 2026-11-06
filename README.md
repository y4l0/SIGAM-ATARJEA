# Sistema de Apoyos Municipales

Sistema de gestión y control de apoyos sociales para el Municipio de Atarjea, Guanajuato.

## Descripción

El Sistema de Apoyos Municipales es una plataforma robusta para la gestión, validación y auditoría de apoyos sociales otorgados por el municipio. Permite el registro de ciudadanos, solicitudes de apoyo, validación de duplicados y generación de reportes estadísticos.

## Características Principales

- **Gestión de Ciudadanos**: Registro único por CURP con validación estricta.
- **Control de Solicitudes**: Flujo completo desde captura hasta aprobación.
- **Validación Antifraude**: Detección automática de posibles duplicados.
- **Roles de Usuario**: Administrador, Director y Capturista con permisos diferenciados.
- **Auditoría Completa**: Registro detallado de todas las acciones realizadas.
- **Reportes y Estadísticas**: Dashboard con KPIs y gráficas para análisis de datos.
- **Catálogos Normalizados**: Comunidades, programas y dependencias estandarizados.

## Requisitos Técnicos

- Python 3.10 o superior (probado con 3.14)
- Windows 10/11 (también funciona en Linux/macOS con ajustes mínimos)
- Todas las dependencias exactas están fijadas en `requirements.txt`

## Instalación (Windows)

1. Copiar la carpeta completa del proyecto a la computadora destino
   (por USB, red compartida o repositorio Git).

2. Crear y activar un entorno virtual (muy recomendado, evita conflictos
   con otras instalaciones de Python en la misma máquina):
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```

3. Instalar las dependencias exactas:
   ```powershell
   pip install -r requirements.txt
   ```

4. Ejecutar la aplicación (la base de datos y los 5 usuarios oficiales
   se crean/verifican AUTOMÁTICAMENTE en el primer arranque, no requiere
   ningún script adicional de inicialización):
   ```powershell
   python run.py
   ```

5. Acceder a la aplicación en el navegador:
   ```
   http://127.0.0.1:5000
   ```

## Credenciales de Acceso

Ver el detalle completo en **`CREDENCIALES_SISTEMA.md`**. Resumen rápido:

- **Admin / Alcalde**: `admin@atarjea.gob.mx` / `admin`
- **Servicios Públicos**: `serviciospublicosAtarjea@gmail.com` / `serviciospublicos`

**IMPORTANTE**: Por seguridad, cambie estas contraseñas desde
`/admin/usuarios` después de la primera instalación en producción.

## Estructura del Proyecto

```
Sistema_Apoyos_Municipales/
├── app/                    # Código principal de la aplicación (ÚNICA fuente de verdad)
│   ├── __init__.py         # Fábrica de la app Flask (create_app)
│   ├── models.py           # Modelos de datos (SQLAlchemy)
│   ├── routes.py           # Todas las rutas y controladores (Blueprint 'main')
│   ├── forms.py            # Formularios (WTForms)
│   ├── backup_utils.py      # Respaldo automático en Escritorio + Paquete Diario
│   ├── pdf_utils.py         # Generación de PDFs (fichas técnicas, expedientes)
│   ├── combustible_logic.py # Reglas de negocio del semáforo de alertas de combustible
│   ├── decorators.py       # @admin_required, @servicios_publicos_required, etc.
│   └── logger_config.py    # Configuración de logging
├── static/                 # CSS, JS, imágenes y librerías vendorizadas (sin internet)
├── templates/              # TODAS las plantillas HTML activas (Jinja2)
├── database/               # Base de datos SQLite (apoyos.db) — se crea sola
├── logs/                   # Archivos de registro del sistema
├── tests/                  # Suite de pruebas automatizadas (pytest)
├── config.py / config_paths.py  # Configuración y rutas 100% portables
├── requirements.txt        # Dependencias exactas verificadas
├── run.py                  # PUNTO DE ENTRADA ÚNICO del sistema
├── build_exe.py            # Genera el ejecutable portable (.exe) con PyInstaller
└── README.md               # Este archivo
```

⚠️ **Nota de arquitectura**: todo el código vive dentro de la carpeta
`app/`. Los únicos archivos de Python fuera de `app/` que forman parte
del sistema real son `run.py` (arranque), `config.py`/`config_paths.py`
(configuración), `build_exe.py` (empaquetado) y
`purgar_pruebas_servicios_publicos.py` (utilidad de mantenimiento). No
existen `routes.py`, `models.py` ni `forms.py` sueltos en la raíz: esos
nombres solo existen dentro de `app/`.

## Flujo de Trabajo

1. **Captura de Solicitud**:
   - El Capturista registra al ciudadano por CURP
   - Selecciona programa y monto
   - El sistema verifica duplicados automáticamente

2. **Validación**:
   - El Director revisa las solicitudes pendientes
   - Aprueba o rechaza según criterios establecidos
   - Las alertas de duplicidad se destacan para revisión especial

3. **Seguimiento**:
   - El Administrador monitorea KPIs en el dashboard
   - Genera reportes por comunidad, programa o periodo
   - Audita el historial completo de operaciones

## Características de Seguridad

- Validación estricta de CURP y RFC
- Auditoría completa de todas las acciones
- Control de acceso basado en roles
- Protección contra duplicados
- Cifrado de contraseñas
- Manejo seguro de sesiones

## Soporte UTF-8

El sistema está configurado para manejar correctamente caracteres UTF-8 en todos los niveles:

- Base de datos con codificación UTF-8
- Encabezados HTTP con charset=utf-8
- Formularios HTML con accept-charset="UTF-8"
- Scripts Python con encoding utf-8

## Mantenimiento

- **Respaldos**: La base de datos debe respaldarse diariamente
- **Logs**: Revisar periódicamente los archivos de registro
- **Actualizaciones**: Mantener las dependencias actualizadas

## Licencia

Este software es propiedad del Municipio de Atarjea, Guanajuato.
Todos los derechos reservados © 2026.

## Contacto

Para soporte técnico:
- Email: sistemas@atarjea.gob.mx
- Teléfono: (419) 293-5278