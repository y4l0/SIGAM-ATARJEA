/**
 * Script para gráficas Chart.js optimizadas para comunidades.html
 * Visualización intuitiva con etiquetas legibles y tipografía clara
 */

// Función para inicializar gráficas optimizadas de demanda de apoyos por comunidad
function inicializarGraficasComunidades(datosComunidades) {
    // Transformar datos para gráfica de comunidades
    const comunidades = Object.keys(datosComunidades);
    const demanda = Object.values(datosComunidades);
    
    // Configuración optimizada para gráfica de comunidades
    const ctxComunidades = document.getElementById('graficaComunidades').getContext('2d');
    const graficaComunidades = new Chart(ctxComunidades, {
        type: 'bar',
        data: {
            labels: comunidades,
            datasets: [{
                label: 'Demanda de Apoyos',
                data: demanda,
                backgroundColor: '#1a237e', // Azul institucional
                borderColor: '#0d1538',
                borderWidth: 1,
                barPercentage: 0.8,
                categoryPercentage: 0.9
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y', // Barras horizontales
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#1a237e',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 12,
                            weight: 'bold'
                        }
                    }
                },
                title: {
                    display: true,
                    text: 'Demanda de Apoyos por Comunidad',
                    color: '#1a237e',
                    font: {
                        family: 'Arial, sans-serif',
                        size: 16,
                        weight: 'bold'
                    }
                },
                tooltip: {
                    backgroundColor: '#ffffff',
                    borderColor: '#1a237e',
                    borderWidth: 1,
                    cornerRadius: 4,
                    titleColor: '#1a237e',
                    bodyColor: '#333333',
                    footerColor: '#666666',
                    font: {
                        family: 'Arial, sans-serif',
                        size: 12
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: {
                        color: '#e0e0e0',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#333333',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 11
                        }
                    },
                    title: {
                        display: true,
                        text: 'Número de Solicitudes',
                        color: '#333333',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 12,
                            weight: 'bold'
                        }
                    }
                },
                y: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#333333',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 11
                        },
                        maxRotation: 0,
                        autoSkip: false
                    },
                    title: {
                        display: true,
                        text: 'Comunidades',
                        color: '#333333',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 12,
                            weight: 'bold'
                        }
                    }
                }
            }
        }
    });
    
    // Crear gráfica de distribución de tipos de apoyo
    if (document.getElementById('graficaTiposApoyo')) {
        const ctxTiposApoyo = document.getElementById('graficaTiposApoyo').getContext('2d');
        const tiposApoyo = ['Alimentario', 'Educativo', 'A la Salud', 'A la Vivienda', 'Apoyo a la Movilidad', 'Fortalecimiento Comunitario y Cohesión Social'];
        const distribucionTipos = [25, 20, 18, 15, 12, 10]; // Datos ejemplo
        
        const coloresTiposApoyo = [
            '#FF6B6B', // Alimentario (Rojo)
            '#4ECDC4', // Educativo (Turquesa)
            '#FFD166', // Salud (Amarillo)
            '#06D6A0', // Vivienda (Verde)
            '#118AB2', // Movilidad (Azul)
            '#073B4C'  // Fortalecimiento (Gris oscuro)
        ];
        
        const graficaTiposApoyo = new Chart(ctxTiposApoyo, {
            type: 'doughnut',
            data: {
                labels: tiposApoyo,
                datasets: [{
                    label: 'Distribución por Tipo',
                    data: distribucionTipos,
                    backgroundColor: coloresTiposApoyo,
                    borderColor: coloresTiposApoyo.map(color => color.replace('#', '#') + '80'),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#333333',
                            font: {
                                family: 'Arial, sans-serif',
                                size: 11
                            },
                            boxWidth: 15,
                            padding: 10
                        }
                    },
                    title: {
                        display: true,
                        text: 'Distribución por Tipo de Apoyo',
                        color: '#1a237e',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 16,
                            weight: 'bold'
                        }
                    }
                },
                cutout: '60%'
            }
        });
    }
    
    // Crear gráfica de distribución de presupuesto por dependencia
    if (document.getElementById('graficaPresupuestoDependencia')) {
        const ctxPresupuestoDependencia = document.getElementById('graficaPresupuestoDependencia').getContext('2d');
        const dependencias = ['DIF Municipal', 'Dirección de Deportes', 'Dirección de Servicios Públicos Municipales', 'Presidencia Municipal', 'Dirección de Desarrollo Social', 'Dirección de Desarrollo Rural y Económico'];
        const presupuestoDependencia = [150000, 80000, 120000, 90000, 110000, 50000]; // Datos ejemplo
        
        const coloresDependencias = [
            '#1a237e', '#303f9f', '#3f51b5', '#5c6bc0', '#7986cb', '#9fa8da'
        ];
        
        const graficaPresupuestoDependencia = new Chart(ctxPresupuestoDependencia, {
            type: 'pie',
            data: {
                labels: dependencias,
                datasets: [{
                    label: 'Presupuesto Ejercido',
                    data: presupuestoDependencia,
                    backgroundColor: coloresDependencias,
                    borderColor: coloresDependencias.map(color => color.replace('#', '#') + '80'),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#333333',
                            font: {
                                family: 'Arial, sans-serif',
                                size: 11
                            },
                            boxWidth: 15,
                            padding: 10
                        }
                    },
                    title: {
                        display: true,
                        text: 'Presupuesto Ejercido por Dependencia',
                        color: '#1a237e',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 16,
                            weight: 'bold'
                        }
                    }
                }
            }
        });
    }
}

// Función para actualizar gráfica al filtrar por comunidad
function actualizarGraficaComunidad(nombreComunidad, datosComunidad) {
    const ctx = document.getElementById('graficaComunidadDetalle').getContext('2d');
    if (ctx) {
        // Datos para gráfica de detalle por comunidad
        const meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
        const solicitudesPorMes = datosComunidad.solicitudesPorMes || [12, 15, 18, 22, 25, 30, 28, 32, 35, 30, 27, 24];
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: meses,
                datasets: [{
                    label: `Solicitudes en ${nombreComunidad}`,
                    data: solicitudesPorMes,
                    backgroundColor: '#1a237e20',
                    borderColor: '#1a237e',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#333333',
                            font: {
                                family: 'Arial, sans-serif',
                                size: 12
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: `Tendencia de Solicitudes - ${nombreComunidad}`,
                        color: '#1a237e',
                        font: {
                            family: 'Arial, sans-serif',
                            size: 16,
                            weight: 'bold'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Número de Solicitudes',
                            color: '#333333',
                            font: {
                                family: 'Arial, sans-serif',
                                size: 12
                            }
                        },
                        grid: {
                            color: '#e0e0e0'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Mes',
                            color: '#333333',
                            font: {
                                family: 'Arial, sans-serif',
                                size: 12
                            }
                        },
                        grid: {
                            color: '#e0e0e0'
                        }
                    }
                }
            }
        });
    }
}

// Exportar funciones para uso global
window.inicializarGraficasComunidades = inicializarGraficasComunidades;
window.actualizarGraficaComunidad = actualizarGraficaComunidad;