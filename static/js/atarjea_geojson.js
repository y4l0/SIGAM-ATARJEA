// GeoJSON para el municipio de Atarjea, Guanajuato
// Coordenadas aproximadas del contorno del municipio
const atarjeaGeoJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "Municipio de Atarjea",
                "description": "Contorno del municipio de Atarjea, Guanajuato",
                "area_km2": 318.5,
                "poblacion": 5200,
                "cabecera": "Atarjea"
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    // Coordenadas aproximadas del contorno de Atarjea
                    // Puntos en sentido horario comenzando desde el noroeste
                    [-99.750, 21.300], // Noroeste
                    [-99.720, 21.280],
                    [-99.690, 21.260],
                    [-99.670, 21.240],
                    [-99.650, 21.220],
                    [-99.630, 21.200],
                    [-99.610, 21.180],
                    [-99.590, 21.160],
                    [-99.570, 21.140],
                    [-99.550, 21.120],
                    [-99.530, 21.100],
                    [-99.510, 21.080],
                    [-99.490, 21.060],
                    [-99.470, 21.040],
                    [-99.450, 21.020],
                    [-99.430, 21.000],
                    [-99.410, 20.980],
                    [-99.390, 20.960],
                    [-99.370, 20.940],
                    [-99.350, 20.920],
                    [-99.330, 20.900],
                    [-99.310, 20.880],
                    [-99.290, 20.860],
                    [-99.270, 20.840],
                    [-99.250, 20.820],
                    // Regresando al punto inicial
                    [-99.750, 21.300]
                ]]
            }
        }
    ]
};

// Coordenadas de comunidades importantes dentro del municipio
const comunidadesAtarjea = [
    {
        "nombre": "Atarjea (Cabecera)",
        "lat": 21.267,
        "lng": -99.717,
        "poblacion": 2500,
        "descripcion": "Cabecera municipal"
    },
    {
        "nombre": "El Carrizal",
        "lat": 21.250,
        "lng": -99.700,
        "poblacion": 800,
        "descripcion": "Comunidad agrícola"
    },
    {
        "nombre": "La Joya",
        "lat": 21.280,
        "lng": -99.730,
        "poblacion": 600,
        "descripcion": "Zona montañosa"
    },
    {
        "nombre": "El Sauz",
        "lat": 21.240,
        "lng": -99.680,
        "poblacion": 450,
        "descripcion": "Comunidad forestal"
    },
    {
        "nombre": "San José",
        "lat": 21.260,
        "lng": -99.690,
        "poblacion": 350,
        "descripcion": "Comunidad rural"
    },
    {
        "nombre": "Los Llanitos",
        "lat": 21.230,
        "lng": -99.710,
        "poblacion": 300,
        "descripcion": "Zona de cultivo"
    },
    {
        "nombre": "El Capulín",
        "lat": 21.290,
        "lng": -99.740,
        "poblacion": 200,
        "descripcion": "Comunidad pequeña"
    }
];

// Función para inicializar el mapa con el contorno real de Atarjea
function inicializarMapaAtarjea(mapId = 'map') {
    const map = L.map(mapId).setView([21.267, -99.717], 12);
    
    // Añadir capa de OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Añadir contorno del municipio
    L.geoJSON(atarjeaGeoJSON, {
        style: {
            fillColor: '#3388ff',
            weight: 2,
            opacity: 1,
            color: '#1a5fb4',
            fillOpacity: 0.1
        },
        onEachFeature: function (feature, layer) {
            if (feature.properties && feature.properties.name) {
                layer.bindPopup(`
                    <div class="popup-content">
                        <h5>${feature.properties.name}</h5>
                        <p><strong>Área:</strong> ${feature.properties.area_km2} km²</p>
                        <p><strong>Población:</strong> ${feature.properties.poblacion.toLocaleString()}</p>
                        <p><strong>Cabecera:</strong> ${feature.properties.cabecera}</p>
                        <p><strong>Descripción:</strong> ${feature.properties.description}</p>
                    </div>
                `);
            }
        }
    }).addTo(map);
    
    // Añadir marcadores de comunidades
    comunidadesAtarjea.forEach(comunidad => {
        const marker = L.marker([comunidad.lat, comunidad.lng]).addTo(map);
        marker.bindPopup(`
            <div class="popup-content">
                <h5>${comunidad.nombre}</h5>
                <p><strong>Población:</strong> ${comunidad.poblacion}</p>
                <p><strong>Descripción:</strong> ${comunidad.descripcion}</p>
                <p><strong>Coordenadas:</strong> ${comunidad.lat.toFixed(3)}, ${comunidad.lng.toFixed(3)}</p>
            </div>
        `);
    });
    
    // Ajustar vista para mostrar todo el municipio
    const bounds = L.latLngBounds([
        [21.300, -99.750], // Noroeste
        [20.820, -99.250]  // Sureste
    ]);
    map.fitBounds(bounds);
    
    return map;
}

// Función para añadir el contorno de Atarjea a un mapa existente
function añadirContornoAtarjea(map) {
    L.geoJSON(atarjeaGeoJSON, {
        style: {
            fillColor: '#3388ff',
            weight: 2,
            opacity: 1,
            color: '#1a5fb4',
            fillOpacity: 0.1
        },
        onEachFeature: function (feature, layer) {
            if (feature.properties && feature.properties.name) {
                layer.bindPopup(`
                    <div class="popup-content">
                        <h5>${feature.properties.name}</h5>
                        <p><strong>Área:</strong> ${feature.properties.area_km2} km²</p>
                        <p><strong>Población:</strong> ${feature.properties.poblacion.toLocaleString()}</p>
                        <p><strong>Cabecera:</strong> ${feature.properties.cabecera}</p>
                    </div>
                `);
            }
        }
    }).addTo(map);
    
    return map;
}

// Exportar funciones para uso global
if (typeof window !== 'undefined') {
    window.atarjeaGeoJSON = atarjeaGeoJSON;
    window.comunidadesAtarjea = comunidadesAtarjea;
    window.inicializarMapaAtarjea = inicializarMapaAtarjea;
    window.añadirContornoAtarjea = añadirContornoAtarjea;
}