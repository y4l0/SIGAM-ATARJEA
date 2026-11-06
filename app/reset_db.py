from app import db
from app.models import Comunidad, Dependencia

# Crear tablas si no existen
db.create_all()

# Insertar datos de ejemplo si las tablas están vacías
if Comunidad.query.count() == 0:
    comunidades = [
        Comunidad(nombre='Mangas Cuatas'),
        Comunidad(nombre='El Carricillo'),
        Comunidad(nombre='La Loma'),
        Comunidad(nombre='El Rincón'),
        Comunidad(nombre='Cerro Prieto')
    ]
    db.session.add_all(comunidades)

if Dependencia.query.count() == 0:
    dependencias = [
        Dependencia(nombre='Presidencia'),
        Dependencia(nombre='Obras Públicas'),
        Dependencia(nombre='Desarrollo Social')
    ]
    db.session.add_all(dependencias)

db.session.commit()
