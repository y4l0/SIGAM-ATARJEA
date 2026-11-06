-"""
Utilidades para gestión de archivos del Sistema de Apoyos Municipales
Municipio de Atarjea, Guanajuato
"""
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

# python-magic requiere la librería binaria 'libmagic', la cual normalmente
# NO está disponible en Windows sin instalar dependencias adicionales
# (python-magic-bin). Para que el sistema NUNCA se caiga por esta causa,
# el import se hace de forma segura: si falla, se desactiva la validación
# de tipo MIME real (se sigue validando extensión y tamaño normalmente).
try:
    import magic
    MAGIC_DISPONIBLE = True
except Exception:
    magic = None
    MAGIC_DISPONIBLE = False


class GestorArchivosMunicipales:
    """Gestor especializado para archivos del sistema municipal"""
    
    TIPOS_DOCUMENTO = {
        'identificacion': {
            'extensiones': {'pdf', 'png', 'jpg', 'jpeg'},
            'tamano_maximo': 5 * 1024 * 1024,  # 5MB
            'descripcion': 'Identificación Oficial (INE, Pasaporte, Cédula)'
        },
        'comprobante_domicilio': {
            'extensiones': {'pdf', 'png', 'jpg', 'jpeg'},
            'tamano_maximo': 5 * 1024 * 1024,  # 5MB
            'descripcion': 'Comprobante de Domicilio (Recibo, Contrato)'
        },
        'evidencia_fotografica': {
            'extensiones': {'png', 'jpg', 'jpeg'},
            'tamano_maximo': 3 * 1024 * 1024,  # 3MB
            'descripcion': 'Evidencia Fotográfica del Apoyo'
        }
    }
    
    @staticmethod
    def validar_extension_archivo(nombre_archivo, tipo_documento):
        """
        Valida que la extensión del archivo sea permitida para el tipo de documento
        
        Args:
            nombre_archivo: Nombre del archivo a validar
            tipo_documento: Tipo de documento (identificacion, comprobante_domicilio, evidencia_fotografica)
        
        Returns:
            bool: True si la extensión es válida, False en caso contrario
        """
        if tipo_documento not in GestorArchivosMunicipales.TIPOS_DOCUMENTO:
            return False
        
        extension_permitida = nombre_archivo.rsplit('.', 1)[1].lower() if '.' in nombre_archivo else ''
        extensiones_validas = GestorArchivosMunicipales.TIPOS_DOCUMENTO[tipo_documento]['extensiones']
        
        return extension_permitida in extensiones_validas
    
    @staticmethod
    def validar_tamano_archivo(archivo_stream, tipo_documento):
        """
        Valida que el tamaño del archivo no exceda el límite permitido
        
        Args:
            archivo_stream: Stream del archivo a validar
            tipo_documento: Tipo de documento
        
        Returns:
            bool: True si el tamaño es válido, False en caso contrario
        """
        if tipo_documento not in GestorArchivosMunicipales.TIPOS_DOCUMENTO:
            return False
        
        # Guardar posición actual
        posicion_actual = archivo_stream.tell()
        archivo_stream.seek(0, 2)  # Ir al final del archivo
        tamano = archivo_stream.tell()
        archivo_stream.seek(posicion_actual)  # Regresar a la posición original
        
        tamano_maximo = GestorArchivosMunicipales.TIPOS_DOCUMENTO[tipo_documento]['tamano_maximo']
        
        return tamano <= tamano_maximo
    
    @staticmethod
    def validar_tipo_mime(archivo_stream):
        """
        Valida el tipo MIME real del archivo usando magic
        
        Args:
            archivo_stream: Stream del archivo a validar
        
        Returns:
            str: Tipo MIME detectado o None si no se puede determinar
            (None también si la librería 'magic' no está disponible en el
            sistema; en ese caso simplemente se omite esta validación
            adicional y el archivo se acepta según extensión y tamaño)
        """
        if not MAGIC_DISPONIBLE:
            return None
        try:
            # Leer primeros bytes para detección
            posicion_actual = archivo_stream.tell()
            muestra = archivo_stream.read(2048)
            archivo_stream.seek(posicion_actual)
            
            mime = magic.Magic(mime=True)
            tipo_mime = mime.from_buffer(muestra)
            return tipo_mime
        except Exception:
            return None

    
    @staticmethod
    def generar_nombre_seguro(nombre_original, tipo_documento, solicitud_id):
        """
        Genera un nombre de archivo seguro y único
        
        Args:
            nombre_original: Nombre original del archivo
            tipo_documento: Tipo de documento
            solicitud_id: ID de la solicitud
        
        Returns:
            str: Nombre de archivo seguro y único
        """
        # Obtener extensión
        if '.' in nombre_original:
            extension = nombre_original.rsplit('.', 1)[1].lower()
        else:
            extension = ''
        
        # Generar nombre único
        nombre_unico = f"{uuid.uuid4().hex[:16]}_{tipo_documento}_{solicitud_id}"
        
        if extension:
            nombre_unico = f"{nombre_unico}.{extension}"
        
        return nombre_unico
    
    @staticmethod
    def obtener_ruta_destino(tipo_documento, nombre_archivo):
        """
        Obtiene la ruta de destino para el archivo según su tipo
        
        Args:
            tipo_documento: Tipo de documento
            nombre_archivo: Nombre del archivo
        
        Returns:
            str: Ruta completa de destino
        """
        directorios = {
            'identificacion': current_app.config.get('UPLOAD_FOLDER_IDENTIFICACIONES', 'static/uploads/identificaciones'),
            'comprobante_domicilio': current_app.config.get('UPLOAD_FOLDER_COMPROBANTES', 'static/uploads/comprobantes'),
            'evidencia_fotografica': current_app.config.get('UPLOAD_FOLDER_EVIDENCIAS', 'static/uploads/evidencias')
        }
        
        directorio_base = directorios.get(tipo_documento, 'static/uploads')
        
        # Asegurar que el directorio existe
        os.makedirs(directorio_base, exist_ok=True)
        
        return os.path.join(directorio_base, nombre_archivo)
    
    @staticmethod
    def guardar_archivo(archivo_stream, ruta_destino):
        """
        Guarda el archivo en la ruta especificada
        
        Args:
            archivo_stream: Stream del archivo
            ruta_destino: Ruta donde guardar el archivo
        
        Returns:
            bool: True si se guardó correctamente, False en caso contrario
        """
        try:
            # Guardar archivo
            archivo_stream.seek(0)
            with open(ruta_destino, 'wb') as f:
                f.write(archivo_stream.read())
            return True
        except Exception as e:
            current_app.logger.error(f"Error al guardar archivo: {str(e)}")
            return False
    
    @staticmethod
    def eliminar_archivo(ruta_archivo):
        """
        Elimina un archivo del sistema
        
        Args:
            ruta_archivo: Ruta del archivo a eliminar
        
        Returns:
            bool: True si se eliminó correctamente, False en caso contrario
        """
        try:
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)
                return True
            return False
        except Exception as e:
            current_app.logger.error(f"Error al eliminar archivo: {str(e)}")
            return False
    
    @staticmethod
    def obtener_informacion_archivo(ruta_archivo):
        """
        Obtiene información detallada de un archivo
        
        Args:
            ruta_archivo: Ruta del archivo
        
        Returns:
            dict: Información del archivo o None si no existe
        """
        if not os.path.exists(ruta_archivo):
            return None
        
        try:
            estadisticas = os.stat(ruta_archivo)
            return {
                'tamano_bytes': estadisticas.st_size,
                'tamano_humano': GestorArchivosMunicipales._formatear_tamano(estadisticas.st_size),
                'fecha_modificacion': estadisticas.st_mtime,
                'fecha_creacion': estadisticas.st_ctime
            }
        except Exception:
            return None
    
    @staticmethod
    def _formatear_tamano(tamano_bytes):
        """Formatea el tamaño en bytes a formato humano"""
        for unidad in ['B', 'KB', 'MB', 'GB']:
            if tamano_bytes < 1024.0:
                return f"{tamano_bytes:.2f} {unidad}"
            tamano_bytes /= 1024.0
        return f"{tamano_bytes:.2f} TB"
    
    @staticmethod
    def validar_archivo_completo(archivo, tipo_documento, solicitud_id):
        """
        Valida completamente un archivo antes de guardarlo
        
        Args:
            archivo: Objeto archivo de Flask
            tipo_documento: Tipo de documento
            solicitud_id: ID de la solicitud
        
        Returns:
            dict: Resultado de la validación con información
        """
        resultado = {
            'valido': False,
            'error': None,
            'nombre_archivo': None,
            'ruta_destino': None,
            'tamano_bytes': 0
        }
        
        # Validar que se haya subido un archivo
        if not archivo or archivo.filename == '':
            resultado['error'] = 'No se seleccionó ningún archivo'
            return resultado
        
        # Validar extensión
        if not GestorArchivosMunicipales.validar_extension_archivo(archivo.filename, tipo_documento):
            extensiones = ', '.join(GestorArchivosMunicipales.TIPOS_DOCUMENTO[tipo_documento]['extensiones'])
            resultado['error'] = f'Extensión no permitida. Use: {extensiones}'
            return resultado
        
        # Validar tamaño
        if not GestorArchivosMunicipales.validar_tamano_archivo(archivo.stream, tipo_documento):
            tamano_max_mb = GestorArchivosMunicipales.TIPOS_DOCUMENTO[tipo_documento]['tamano_maximo'] / (1024 * 1024)
            resultado['error'] = f'Archivo demasiado grande. Tamaño máximo: {tamano_max_mb}MB'
            return resultado
        
        # Validar tipo MIME
        tipo_mime = GestorArchivosMunicipales.validar_tipo_mime(archivo.stream)
        if tipo_mime:
            # Verificar que el tipo MIME coincida con la extensión
            extensiones_validas_mime = {
                'application/pdf': {'pdf'},
                'image/png': {'png'},
                'image/jpeg': {'jpg', 'jpeg'},
                'image/jpg': {'jpg', 'jpeg'}
            }
            
            extension_archivo = archivo.filename.rsplit('.', 1)[1].lower() if '.' in archivo.filename else ''
            if tipo_mime in extensiones_validas_mime:
                if extension_archivo not in extensiones_validas_mime[tipo_mime]:
                    resultado['error'] = f'El tipo de archivo no coincide con la extensión. Tipo detectado: {tipo_mime}'
                    return resultado
        
        # Generar nombre seguro
        nombre_seguro = GestorArchivosMunicipales.generar_nombre_seguro(
            archivo.filename, tipo_documento, solicitud_id
        )
        
        # Obtener ruta de destino
        ruta_destino = GestorArchivosMunicipales.obtener_ruta_destino(tipo_documento, nombre_seguro)
        
        # Obtener tamaño
        archivo.stream.seek(0, 2)
        tamano = archivo.stream.tell()
        archivo.stream.seek(0)
        
        resultado.update({
            'valido': True,
            'nombre_archivo': nombre_seguro,
            'ruta_destino': ruta_destino,
            'tamano_bytes': tamano,
            'tipo_mime': tipo_mime
        })
        
        return resultado