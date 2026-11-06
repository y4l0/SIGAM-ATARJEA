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
    // REINICIO DE GRÁFICOS DE PRESUPUESTO (ORDEN TÉCNICA MAESTRA): esta
    // función acepta opcionalmente datos REALES de distribución por tipo
    // de apoyo (segundo parámetro); si no se proporcionan, se muestra
    // estrictamente un estado en 0%, nunca presupuesto visual fantasma
    // con cifras de ejemplo ficticias.
    if (document.getElementById('graficaTiposApoyo')) {
        const ctxTiposApoyo = document.getElementById('graficaTiposApoyo').getContext('2d');
        const datosRealesTipos = (typeof datosDistribucionTipos !== 'undefined' && datosDistribucionTipos) ? datosDistribucionTipos : {};
        const sinDatosTipos = Object.keys(datosRealesTipos).length === 0;
        const tiposApoyo = sinDatosTipos ? ['Sin apoyos registrados (0%)'] : Object.keys(datosRealesTipos);
        const distribucionTipos = sinDatosTipos ? [1] : Object.values(datosRealesTipos);
        
        const coloresTiposApoyo = sinDatosTipos ? ['#e0e0e0'] : [
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
    // REINICIO DE GRÁFICOS DE PRESUPUESTO (ORDEN TÉCNICA MAESTRA): acepta
    // opcionalmente datos REALES de presupuesto por dependencia (variable
    // global datosPresupuestoDependencia); si no existen apoyos aprobados
    // con monto real, se refleja ESTRICTAMENTE 0%, eliminando cualquier
    // presupuesto visual fantasma (antes cifras de ejemplo ficticias).
    if (document.getElementById('graficaPresupuestoDependencia')) {
        const ctxPresupuestoDependencia = document.getElementById('graficaPresupuestoDependencia').getContext('2d');
        const datosRealesDependencia = (typeof datosPresupuestoDependencia !== 'undefined' && datosPresupuestoDependencia) ? datosPresupuestoDependencia : {};
        const sinDatosDependencia = Object.keys(datosRealesDependencia).length === 0;
        const dependencias = sinDatosDependencia ? ['Sin presupuesto ejercido (0%)'] : Object.keys(datosRealesDependencia);
        const presupuestoDependencia = sinDatosDependencia ? [1] : Object.values(datosRealesDependencia);
        
        const coloresDependencias = sinDatosDependencia ? ['#e0e0e0'] : [
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