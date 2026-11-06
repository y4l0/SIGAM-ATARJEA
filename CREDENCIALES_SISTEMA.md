# CREDENCIALES DEL SISTEMA SIGEM - ATARJEA

## 📋 INICIALIZACIÓN AUTOMÁTICA

Cada vez que se ejecuta `python run.py`, la función
`inicializar_usuarios_y_dependencias()` (en `run.py`) **garantiza** (crea o
restablece la contraseña de) las siguientes 5 cuentas oficiales, por lo
que SIEMPRE funcionan sin importar el estado previo de la base de datos:

## 👥 CUENTAS DEL SISTEMA (verificadas contra el código real)

| Rol | Email | Contraseña | Alcance |
|---|---|---|---|
| **Admin / Alcalde** | `admin@atarjea.gob.mx` | `admin` | Control total: Panel Ejecutivo, usuarios, cierre de ejercicio |
| **Presidente Municipal** | `presidente@atarjea.gob.mx` | `Presidente2026` | Único rol (junto con Admin) que puede cerrar el ejercicio anual |
| **Director (prueba)** | `director@atarjea.gob.mx` | `Director2026` | Solo ve solicitudes de su propia dependencia |
| **Operador** | `operador@atarjea.gob.mx` | `Operador2026` | Solo captura nuevas solicitudes |
| **Servicios Públicos** | `serviciospublicosAtarjea@gmail.com` | `serviciospublicos` | Acceso exclusivo al Dashboard de Combustible |
| **Presidencia Municipal** | `presidenciamunicipala@gmail.com` | `pmunicipal2427` | Rol Admin: control total (administrador global) |
| **Secretaría del Ayuntamiento** | `sayuntamiento@gmail.com` | `sayuntamiento2427` | Rol Director: solo ve/gestiona su propia dependencia |

⚠️ **IMPORTANTE DE SEGURIDAD**: estas son credenciales de arranque/demo.
En un entorno de producción real, cambie la contraseña del Admin y del
Presidente inmediatamente después de la primera instalación desde
`/admin/usuarios` (solo el Admin puede editar usuarios).

## 🏛️ DEPENDENCIAS OFICIALES (7 OPCIONES)

1. **DIF Municipal**
2. **Dirección de Deportes**
3. **Dirección de Servicios Públicos Municipales**
4. **Presidencia Municipal**
5. **Dirección de Desarrollo Social**
6. **Dirección de Desarrollo Rural y Económico**
7. **Secretaría del Ayuntamiento**

## 🌍 COMUNIDADES DE ATARJEA (25 COMUNIDADES)

El sistema incluye las 25 comunidades oficiales del municipio de Atarjea, incluyendo la cabecera municipal y las localidades rurales.

## 🚀 ACCESO AL SISTEMA

```bash
python run.py
```

Luego abrir en el navegador: **http://127.0.0.1:5000**

## 🔒 SEGURIDAD

- Contraseñas cifradas con `Werkzeug.security` (`generate_password_hash`),
  nunca se guarda texto plano.
- Autenticación por roles (Admin, Presidente, Director, Operador,
  ServiciosPublicos) mediante decoradores en `app/decorators.py`.
- Auditoría completa de cambios de estado en la tabla `AuditoriaLog` y
  en la bitácora de sistema con hash encadenado (`BitacoraSistemaLog`).
- Protección CSRF activa en todos los formularios (Flask-WTF).

---
**Última actualización:** 23 de octubre de 2026 — credenciales verificadas
contra el código real de `run.py::inicializar_usuarios_y_dependencias()`.