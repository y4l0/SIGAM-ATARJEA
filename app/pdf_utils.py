from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from flask import current_app
from .models import Solicitud, Ciudadano, Dependencia, AdjuntoSolicitud
import os
from datetime import datetime
import tempfile
from PIL import Image as PILImage
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_paths import obtener_ruta_expedientes


def generar_ficha_tecnica_pdf(solicitud_id, usuario_id):
    """
    Genera una ficha técnica en PDF para una solicitud específica.
    Contiene: Folio, Datos Ciudadano, Detalle del Apoyo, Nombre/Puesto del autorizante y miniaturas de fotos adjuntas.
    """
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        ciudadano = Ciudadano.query.get(solicitud.CURP)
        dependencia = Dependencia.query.get(solicitud.dependencia_id) if solicitud.dependencia_id else None
        
        # Obtener usuario autorizante
        usuario = Solicitud.query.get(solicitud_id).usuario
        
        # Obtener adjuntos de la solicitud
        adjuntos = AdjuntoSolicitud.query.filter_by(solicitud_id=solicitud_id, activo=True).all()
        
        # Crear directorio para expedientes de auditoría (ruta portable, funciona en cualquier PC y como .exe)
        expediente_path = obtener_ruta_expedientes()
        
        # Generar nombre de archivo único
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Ficha_Tecnica_{solicitud.folio}_{timestamp}.pdf"

        pdf_path = os.path.join(expediente_path, filename)
        
        # Crear PDF
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        elements = []
        
        styles = getSampleStyleSheet()
        
        # Título principal
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1a237e'),  # Azul institucional
            alignment=TA_CENTER,
            spaceAfter=12
        )
        
        # Subtítulos
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_LEFT,
            spaceAfter=6
        )
        
        # Texto normal
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.black,
            alignment=TA_LEFT,
            spaceAfter=3
        )
        
        # Encabezado institucional
        elements.append(Paragraph("Sistema Integral de Gestión Municipal (SIGEM)", title_style))
        elements.append(Paragraph("Municipio de Atarjea, Guanajuato", subtitle_style))
        elements.append(Paragraph("Dirección de Desarrollo Social y Económico", styles['Heading3']))
        elements.append(Paragraph(f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", normal_style))
        
        # Folio de la solicitud
        elements.append(Paragraph("Folio de Auditoría:", subtitle_style))
        elements.append(Paragraph(f"{solicitud.folio}", ParagraphStyle(
            'FolioStyle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.red,
            alignment=TA_CENTER,
            borderWidth=1,
            borderColor=colors.red,
            borderRadius=2,
            padding=6
        )))
        
        # Información del Ciudadano
        elements.append(Paragraph("1. Datos del Ciudadano:", subtitle_style))
        datos_ciudadano = [
            ["Campo", "Valor"],
            ["CURP", solicitud.CURP],
            ["Nombre Completo", f"{ciudadano.Nombre} {ciudadano.Apellido_Paterno} {ciudadano.Apellido_Materno or ''}"],
            ["Fecha de Nacimiento", ciudadano.Fecha_Nacimiento.strftime('%d/%m/%Y') if ciudadano.Fecha_Nacimiento else "No disponible"],
            ["Edad", ciudadano.Edad or "No disponible"],
            ["Género", ciudadano.Genero or "No disponible"],
            ["Discapacidad", "Si" if ciudadano.Discapacidad else "No"],
            ["RFC", ciudadano.RFC or "No disponible"],
            ["Domicilio", ciudadano.Direccion or "No disponible"],
            ["Teléfono", ciudadano.Telefono or "No disponible"],
            ["Colonia", ciudadano.Colonia or "No disponible"],
            ["Código Postal", ciudadano.Codigo_Postal or "No disponible"]
        ]
        
        ciudadano_table = Table(datos_ciudadano, colWidths=[2.5*inch, 4*inch])
        ciudadano_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(ciudadano_table)
        
        # Información del Apoyo
        elements.append(Paragraph("2. Detalle del Apoyo:", subtitle_style))
        datos_apoyo = [
            ["Campo", "Valor"],
            ["Folio", solicitud.folio],
            ["Comunidad", solicitud.Comunidad],
            ["Programa", solicitud.Programa],
            ["Tipo de Apoyo", solicitud.Tipo_Apoyo],
            ["Monto", f"${solicitud.Monto:.2f}" if solicitud.Monto else "$0.00"],
            ["Fecha Solicitud", solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M:%S')],
            ["Estatus", solicitud.Estatus],
            ["Dependencia", dependencia.nombre if dependencia else solicitud.Dependencia or "No disponible"]
        ]
        
        apoyo_table = Table(datos_apoyo, colWidths=[2.5*inch, 4*inch])
        apoyo_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(apoyo_table)
        
        # Información del Autorizante
        elements.append(Paragraph("3. Autorizante:", subtitle_style))
        datos_autorizante = [
            ["Campo", "Valor"],
            ["Nombre", usuario.nombre if usuario else "No disponible"],
            ["Email", usuario.email if usuario else "No disponible"],
            ["Rol", usuario.rol if usuario else "No disponible"],
            ["Dependencia", usuario.dependencia.nombre if usuario and usuario.dependencia else "No disponible"],
            ["Fecha Autorización", solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M:%S')]
        ]
        
        autorizante_table = Table(datos_autorizante, colWidths=[2.5*inch, 4*inch])
        autorizante_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(autorizante_table)
        
        # Miniaturas de fotos adjuntas
        if adjuntos:
            elementos_evidencia = []
            elementos_evidencia.append(Paragraph("4. Documentos Adjuntos:", subtitle_style))
            
            # Crear tabla de adjuntos
            adjuntos_data = [["Tipo Documento", "Nombre Archivo", "Fecha Carga", "Tamaño"]]
            
            for adjunto in adjuntos:
                adjuntos_data.append([
                    adjunto.tipo_documento,
                    adjunto.nombre_original,
                    adjunto.fecha_carga.strftime('%d/%m/%Y %H:%M:%S'),
                    f"{adjunto.tamano_bytes} bytes"
                ])
            
            adjuntos_table = Table(adjuntos_data, colWidths=[2*inch, 3*inch, 1.5*inch, 1.5*inch])
            adjuntos_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D4037')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elementos_evidencia.append(adjuntos_table)
            
            # Agregar miniaturas de imágenes si existen
            # NOTA: tipo_documento se guarda como 'evidencia_fotografica' (snake_case) al crear
            # el adjunto en routes.py, por lo que la comparación debe usar ese mismo valor.
            # También se aceptan variantes con el texto descriptivo por compatibilidad.
            tipos_evidencia_validos = {'evidencia_fotografica', 'Evidencia Fotográfica del Apoyo'}
            imagenes = []
            for adjunto in adjuntos:
                if adjunto.tipo_documento in tipos_evidencia_validos or adjunto.categoria_documento == 'evidencia':
                    # Intentar obtener la imagen si es JPEG o PNG
                    if adjunto.extension and adjunto.extension.lower() in ['jpg', 'jpeg', 'png']:
                        imagenes.append(adjunto)
            
            if imagenes:
                elementos_evidencia.append(Paragraph("Miniaturas de Evidencia Fotográfica:", subtitle_style))
                
                # Crear miniaturas
                for adjunto in imagenes[:3]:  # Máximo 3 imágenes por página
                    try:
                        # Resolver ruta física real del archivo. ruta_archivo se guarda de forma
                        # relativa a la carpeta 'static' (ej. 'uploads/solicitudes/1/foto.jpg'),
                        # por lo que hay que anteponer la carpeta static de la app para localizarla
                        # en disco, sin importar el directorio de trabajo actual del proceso.
                        ruta_relativa = adjunto.ruta_archivo
                        ruta_imagen = ruta_relativa
                        if not os.path.isabs(ruta_imagen) or not os.path.exists(ruta_imagen):
                            ruta_candidata = os.path.join(current_app.static_folder, ruta_relativa)
                            if os.path.exists(ruta_candidata):
                                ruta_imagen = ruta_candidata

                        if os.path.exists(ruta_imagen):
                            # Crear miniatura usando PIL
                            with PILImage.open(ruta_imagen) as img:
                                # Convertir a RGB por si la imagen es PNG con transparencia (RGBA)
                                if img.mode in ('RGBA', 'P'):
                                    img = img.convert('RGB')
                                # Redimensionar a tamaño miniatura
                                img.thumbnail((400, 400))
                                # Guardar temporalmente
                                temp_path = tempfile.mktemp(suffix='.jpg')
                                img.save(temp_path, format='JPEG')
                                
                                # Agregar imagen al PDF
                                elementos_evidencia.append(Paragraph(f"{adjunto.nombre_original}", normal_style))
                                elementos_evidencia.append(Image(temp_path, width=2.5*inch, height=1.875*inch))
                                elementos_evidencia.append(Paragraph("", normal_style))
                        else:
                            current_app.logger.warning(f"No se encontró la imagen de evidencia en disco: {ruta_relativa}")
                            elementos_evidencia.append(Paragraph(f"[Imagen no disponible: {adjunto.nombre_original}]", normal_style))
                    except Exception as e:
                        current_app.logger.error(f"Error procesando miniatura: {str(e)}")
                        elementos_evidencia.append(Paragraph(f"Error procesando {adjunto.nombre_original}", normal_style))
            
            elements.extend(elementos_evidencia)
        else:
            elements.append(Paragraph("4. Documentos Adjuntos:", subtitle_style))
            elements.append(Paragraph("No hay documentos adjuntos registrados.", normal_style))
        
        # Firmas y auditoría
        elements.append(Paragraph("5. Auditoría y Firmas:", subtitle_style))
        
        auditoria_data = [
            ["Campo", "Valor"],
            ["Sistema Generador", "SIGEM - Sistema Integral de Gestión Municipal"],
            ["Versión", "3.0"],
            ["Fecha Generación", datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
            ["Usuario Autorizante", usuario.nombre if usuario else "Sistema"],
            ["IP Registrada", "127.0.0.1"],
            ["Hash de Auditoría", f"{solicitud_id}_{timestamp}"]
        ]
        
        auditoria_table = Table(auditoria_data, colWidths=[2.5*inch, 4*inch])
        auditoria_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7B1FA2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(auditoria_table)
        
        # Footer con información institucional
        footer_style = ParagraphStyle(
            'FooterStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            alignment=TA_CENTER,
            spaceBefore=20,
            spaceAfter=0
        )
        
        elements.append(Paragraph("Este documento forma parte del Expediente de Auditoría del Sistema SIGEM", footer_style))
        elements.append(Paragraph("Municipio de Atarjea, Guanajuato - Sistema auditado para transparencia pública", footer_style))
        elements.append(Paragraph(f"Archivo generado automáticamente: {filename}", footer_style))
        
        # Construir PDF
        doc.build(elements)
        
        # Registrar la generación en la auditoría
        from .models import AuditoriaLog, db
        auditoria_entry = AuditoriaLog(
            user_id=usuario_id,
            accion="Generación de Ficha Técnica en PDF",
            tabla_afectada="solicitudes",
            registro_id=str(solicitud_id),
            detalle_cambio=f"PDF generado: {filename}, Folio: {solicitud.folio}",
            ip_address="127.0.0.1",
            fecha=datetime.utcnow()
        )
        db.session.add(auditoria_entry)
        db.session.commit()
        
        return pdf_path
        
    except Exception as e:
        # CERO CAÍDAS (ORDEN TÉCNICA MAESTRA): se registra el detalle
        # técnico completo (exc_info) para diagnóstico, y se re-lanza la
        # excepción para que la ruta que invoca esta función decida cómo
        # informar al operador (nunca debe llegar como un 500 crudo).
        current_app.logger.error(f"Error generando ficha técnica PDF (solicitud #{solicitud_id}): {str(e)}", exc_info=True)
        raise

def generar_reporte_completo_solicitud(solicitud_id):
    """
    Genera un reporte PDF completo para una solicitud específica.
    Similar a la ficha técnica pero más detallado para distribución interna.
    """
    try:
        solicitud = Solicitud.query.get_or_404(solicitud_id)
        ciudadano = Ciudadano.query.get(solicitud.CURP)
        usuario = Solicitud.query.get(solicitud_id).usuario
        
        # Crear directorio para expedientes de auditoría (ruta portable, funciona en cualquier PC y como .exe)
        expediente_path = obtener_ruta_expedientes()
        
        # Generar nombre de archivo único
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Reporte_Completo_{solicitud.folio}_{timestamp}.pdf"

        pdf_path = os.path.join(expediente_path, filename)
        
        # Crear PDF
        c = canvas.Canvas(pdf_path, pagesize=letter)
        
        # Encabezado institucional
        c.setFont("Helvetica-Bold", 18)
        c.drawString(100, 750, "Sistema Integral de Gestión Municipal (SIGEM)")
        c.setFont("Helvetica", 14)
        c.drawString(100, 730, "Municipio de Atarjea, Guanajuato")
        c.drawString(100, 710, "Reporte de Solicitud de Apoyo")
        
        # Folio destacado
        c.setFont("Helvetica-Bold", 16)
        c.drawString(400, 750, f"Folio: {solicitud.folio}")
        
        # Separador
        c.line(50, 680, 550, 680)
        
        # Datos del Ciudadano
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 660, "DATOS DEL CIUDADANO:")
        c.setFont("Helvetica", 11)
        c.drawString(50, 645, f"CURP: {solicitud.CURP}")
        c.drawString(50, 630, f"Nombre: {ciudadano.Nombre} {ciudadano.Apellido_Paterno} {ciudadano.Apellido_Materno or ''}")
        c.drawString(50, 615, f"Fecha Nacimiento: {ciudadano.Fecha_Nacimiento.strftime('%d/%m/%Y') if ciudadano.Fecha_Nacimiento else 'No disponible'}")
        c.drawString(50, 600, f"Género: {ciudadano.Genero or 'No disponible'}")
        c.drawString(50, 585, f"Domicilio: {ciudadano.Direccion or 'No disponible'}")
        c.drawString(50, 570, f"Teléfono: {ciudadano.Telefono or 'No disponible'}")
        
        # Datos de la Solicitud
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 550, "DATOS DE LA SOLICITUD:")
        c.setFont("Helvetica", 11)
        c.drawString(50, 535, f"Comunidad: {solicitud.Comunidad}")
        c.drawString(50, 520, f"Programa: {solicitud.Programa}")
        c.drawString(50, 505, f"Tipo de Apoyo: {solicitud.Tipo_Apoyo}")
        c.drawString(50, 490, f"Monto: ${solicitud.Monto:.2f}" if solicitud.Monto else f"Monto: $0.00")
        c.drawString(50, 475, f"Fecha Solicitud: {solicitud.Fecha_Solicitud.strftime('%d/%m/%Y %H:%M')}")
        c.drawString(50, 460, f"Estatus: {solicitud.Estatus}")
        
        # Autorizante
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 440, "AUTORIZANTE:")
        c.setFont("Helvetica", 11)
        c.drawString(50, 425, f"Nombre: {usuario.nombre if usuario else 'No disponible'}")
        c.drawString(50, 410, f"Email: {usuario.email if usuario else 'No disponible'}")
        c.drawString(50, 395, f"Rol: {usuario.rol if usuario else 'No disponible'}")
        c.drawString(50, 380, f"Dependencia: {usuario.dependencia.nombre if usuario and usuario.dependencia else 'No disponible'}")
        
        # Separador
        c.line(50, 370, 550, 370)
        
        # Información de auditoría
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 350, "INFORMACIÓN DE AUDITORÍA:")
        c.setFont("Helvetica", 10)
        c.drawString(50, 335, f"Sistema: SIGEM v3.0")
        c.drawString(50, 320, f"Fecha Generación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        c.drawString(50, 305, f"ID Solicitud: #{solicitud_id}")
        c.drawString(50, 290, f"Folio Auditoría: {solicitud.folio}")
        
        # Footer institucional
        c.setFont("Helvetica", 9)
        c.drawString(50, 50, "Municipio de Atarjea, Guanajuato - Sistema auditado para transparencia pública")
        c.drawString(50, 35, "Este documento forma parte del Expediente de Auditoría SIGEM")
        
        # Guardar PDF
        c.save()
        
        return pdf_path
        
    except Exception as e:
        current_app.logger.error(f"Error generando reporte completo (solicitud #{solicitud_id}): {str(e)}", exc_info=True)
        raise