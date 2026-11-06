// -*- coding: utf-8 -*-
document.addEventListener('DOMContentLoaded', function() {
    // Cerrar alertas automáticamente después de 5 segundos
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Activar tooltips de Bootstrap
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Función para buscar beneficiario por CURP
    const curpInput = document.getElementById('curp');
    if (curpInput) {
        curpInput.addEventListener('blur', function() {
            const curp = this.value.trim().toUpperCase();
            if (curp.length === 18) {
                fetch('/buscar_beneficiario?curp=' + curp)
                    .then(response => response.json())
                    .then(data => {
                        if (data.encontrado) {
                            document.getElementById('nombre').value = data.nombre;
                            document.getElementById('apellidos').value = data.apellidos;
                            document.getElementById('genero').value = data.genero;
                            document.getElementById('fecha_nacimiento').value = data.fecha_nacimiento;
                            document.getElementById('rfc').value = data.rfc;
                            document.getElementById('comunidad').value = data.comunidad_id;
                            document.getElementById('codigo_postal').value = data.codigo_postal;
                            document.getElementById('telefono').value = data.telefono;
                            
                            // Mostrar alerta
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-info alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Beneficiario encontrado. Los datos han sido cargados automáticamente.
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            `;
                            document.querySelector('.container').insertBefore(alertDiv, document.querySelector('h2').nextSibling);
                        }
                    })
                    .catch(error => console.error('Error:', error));
            }
        });
    }
});