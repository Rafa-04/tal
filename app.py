from flask import Flask, request, jsonify, session, render_template, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import mysql.connector
from functools import wraps
import os
import time
from werkzeug.utils import secure_filename
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'clave_secreta_segura_12345'
bcrypt = Bcrypt(app)

# subida de archivos
UPLOAD_FOLDER = 'static/uploads/logos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Configuración de base de datos
def get_db_connection():
    try:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="conductor"
        )
    except mysql.connector.Error as err:
        print(f"Error de conexión a la base de datos: {err}")
        return None

# Función para verificar y actualizar el esquema
def verificar_esquema():
    """Verifica y actualiza el esquema de la base de datos si es necesario"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
                AND table_name = 'viaje'
                AND column_name = 'ruta_coordenadas'
        """)
        if cursor.fetchone()[0] == 0:
            print("Agregando columna ruta_coordenadas a la tabla viaje")
            cursor.execute("ALTER TABLE viaje ADD COLUMN ruta_coordenadas TEXT NULL")
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
                AND table_name = 'viaje'
                AND column_name = 'distancia_calculada'
        """)
        if cursor.fetchone()[0] == 0:
            print("Agregando columna distancia_calculada a la tabla viaje")
            cursor.execute("ALTER TABLE viaje ADD COLUMN distancia_calculada DECIMAL(10,2) NULL")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
        
    except mysql.connector.Error as err:
        print(f"Error al verificar el esquema: {err}")
        return False
    except Exception as e:
        print(f"Error inesperado en verificar_esquema: {e}")
        return False

# autenticación
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('inicio'))
        return f(*args, **kwargs)
    return decorated_function

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({'error': 'Autenticación requerida', 'authenticated': False}), 401
        return f(*args, **kwargs)
    return decorated_function

# Funciones de base de datos
def ejecutar_consulta(query, params=None, fetchone=False, commit=False):
    conn = get_db_connection()
    if conn is None:
        return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        
        if fetchone:
            result = cursor.fetchone()
        elif not commit:
            result = cursor.fetchall()
        else:
            result = True
            
        if commit:
            conn.commit()
            
        return result
    except mysql.connector.Error as err:
        print(f"Error en la consulta: {err}")
        if commit:
            conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def limpiar_archivos_huerfanos():
    """Limpia archivos de logos que ya no tienen referencia en la base de datos"""
    try:
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            logos_en_uso = ejecutar_consulta("SELECT imagen_logo FROM linea WHERE imagen_logo IS NOT NULL")
            logos_en_uso = [logo['imagen_logo'] for logo in logos_en_uso] if logos_en_uso else []
            
            archivos_en_directorio = os.listdir(app.config['UPLOAD_FOLDER'])
            
            for archivo in archivos_en_directorio:
                if archivo not in logos_en_uso:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], archivo))
                        print(f"Archivo huérfano eliminado: {archivo}")
                    except Exception as e:
                        print(f"Error al eliminar archivo huérfano {archivo}: {e}")
                        
    except Exception as e:
        print(f"Error durante la limpieza de archivos huérfanos: {e}")

# =====================================
# AUTENTICACIÓN
# =====================================

@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    """Verificar estado de autenticación"""
    if 'usuario' in session:
        return jsonify({
            'authenticated': True,
            'usuario': session['usuario'],
            'usuario_id': session['usuario_id']
        })
    return jsonify({'authenticated': False})

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Iniciar sesión"""
    data = request.get_json()
    if not data or 'nombre' not in data or 'contrasena' not in data:
        return jsonify({'error': 'Nombre y contraseña requeridos'}), 400

    usuario = ejecutar_consulta("SELECT * FROM usuario WHERE nombre_usuario = %s", 
                               (data['nombre'],), 
                               fetchone=True)
    
    if usuario and bcrypt.check_password_hash(usuario['contrasena'], data['contrasena']):
        session['usuario'] = usuario['nombre_usuario']
        session['usuario_id'] = usuario['id']
        return jsonify({
            'message': 'Login exitoso',
            'usuario': usuario['nombre_usuario'],
            'authenticated': True
        })
    
    return jsonify({'error': 'Credenciales incorrectas'}), 401

@app.route('/api/auth/register-initial', methods=['POST'])
def api_registro_inicial():
    """Registrar usuario inicial"""
    if ejecutar_consulta("SELECT * FROM usuario LIMIT 1", fetchone=True):
        return jsonify({'error': 'Ya existe un usuario registrado'}), 400

    data = request.get_json()
    if not data or 'nombre' not in data or 'contrasena' not in data:
        return jsonify({'error': 'Nombre y contraseña requeridos'}), 400

    contrasena_hash = bcrypt.generate_password_hash(data['contrasena']).decode('utf-8')
    if ejecutar_consulta("INSERT INTO usuario (id, nombre_usuario, contrasena) VALUES (%s, %s, %s)", 
                        (1, data['nombre'], contrasena_hash), 
                        commit=True):
        return jsonify({'message': 'Usuario creado correctamente'})
    
    return jsonify({'error': 'Error al crear usuario'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Cerrar sesión"""
    session.clear()
    return jsonify({'message': 'Sesión cerrada correctamente'})

# =====================================
# RUTA - USUARIO
# =====================================

@app.route('/api/opciones/cambiar-credenciales', methods=['PUT'])
@api_login_required
def api_cambiar_credenciales():
    """Cambiar credenciales de usuario"""
    print(f"Sesión actual: {session}")  
    data = request.get_json()
    
    if not data or not all(k in data for k in ['contrasena_actual', 'nuevo_usuario', 'nueva_contrasena']):
        return jsonify({'error': 'Datos incompletos'}), 400
    
    usuario_id = session['usuario_id']
    usuario = ejecutar_consulta("SELECT * FROM usuario WHERE id = %s", (usuario_id,), fetchone=True)
    
    if usuario and bcrypt.check_password_hash(usuario['contrasena'], data['contrasena_actual']):
        nuevo_nombre = data['nuevo_usuario']
        nueva_contrasena = bcrypt.generate_password_hash(data['nueva_contrasena']).decode('utf-8')
        
        if ejecutar_consulta("""
            UPDATE usuario 
            SET nombre_usuario = %s, contrasena = %s 
            WHERE id = %s
        """, (nuevo_nombre, nueva_contrasena, usuario_id), commit=True):
            return jsonify({
                'message': 'Credenciales actualizadas correctamente',
                'logout_required': True
            })
        
        return jsonify({'error': 'Error al actualizar credenciales'}), 500
    
    return jsonify({'error': 'Contraseña actual incorrecta'}), 401

@app.route('/api/opciones/eliminar-datos', methods=['DELETE'])
@api_login_required
def api_eliminar_datos():
    """Eliminar todos los datos del sistema"""
    try:
        data = request.get_json()
        if not data or 'password' not in data:
            return jsonify({'error': 'Contraseña requerida'}), 400
        
        # Verificar contraseña
        usuario_id = session['usuario_id']
        usuario = ejecutar_consulta("SELECT * FROM usuario WHERE id = %s", (usuario_id,), fetchone=True)
        
        if not usuario or not bcrypt.check_password_hash(usuario['contrasena'], data['password']):
            return jsonify({'error': 'Contraseña incorrecta'}), 401
        
        ejecutar_consulta("SET FOREIGN_KEY_CHECKS = 0", commit=True)
        
        tablas = [
            "sistema_analitico",
            "viaje",
            "vehiculo",
            "conductor",
            "linea"
        ]
        
        for tabla in tablas:
            ejecutar_consulta(f"DELETE FROM {tabla}", commit=True)
            print(f"Datos eliminados de {tabla}")
        
        limpiar_archivos_huerfanos();
        
        ejecutar_consulta("SET FOREIGN_KEY_CHECKS = 1", commit=True)
        
        return jsonify({'message': 'Toda la información ha sido eliminada correctamente'})
    
    except mysql.connector.Error as err:
        print(f"Error de base de datos: {err}")
        ejecutar_consulta("SET FOREIGN_KEY_CHECKS = 1", commit=True)
        return jsonify({'error': f'Error al eliminar datos: {err}'}), 500
    
    except Exception as e:
        print(f"Error inesperado: {e}")
        ejecutar_consulta("SET FOREIGN_KEY_CHECKS = 1", commit=True)
        return jsonify({'error': f'Error al eliminar datos: {e}'}), 500

# =====================================
# RUTA - DASHBOARD
# =====================================

@app.route('/api/dashboard', methods=['GET'])
@api_login_required
def api_dashboard():
    """Obtener estadísticas para el dashboard"""
    try:
        conductores = ejecutar_consulta("SELECT COUNT(*) as total FROM conductor", fetchone=True)
        viajes = ejecutar_consulta("SELECT COUNT(*) as total FROM viaje", fetchone=True)
        lineas = ejecutar_consulta("SELECT COUNT(*) as total FROM linea", fetchone=True)
        
        return jsonify({
            'total_conductores': conductores['total'] if conductores else 0,
            'total_viajes': viajes['total'] if viajes else 0,
            'total_lineas': lineas['total'] if lineas else 0
        })
    except Exception as e:
        print(f"Error en dashboard: {e}")
        return jsonify({'error': 'Error al obtener estadísticas'}), 500

# =====================================
# RUTA - CONDUCTORES
# =====================================

@app.route('/api/conductores', methods=['GET'])
@api_login_required
def api_conductores():
    """Obtener todos los conductores CON VEHÍCULO ASIGNADO"""
    conductores = ejecutar_consulta("""
        SELECT 
            c.cedula, c.nombre, c.apellido, c.licencia, c.fecha_registro, c.activo,
            v.matricula AS vehiculo_matricula,
            v.marca AS vehiculo_marca, 
            v.modelo AS vehiculo_modelo,
            l.nombre AS linea_nombre,
            v.capacidad AS vehiculo_capacidad
        FROM conductor c 
        INNER JOIN vehiculo v ON c.cedula = v.conductor_ci  # Cambio crucial: INNER JOIN
        LEFT JOIN linea l ON v.linea_asignada = l.id
        WHERE v.matricula IS NOT NULL  # Solo conductores con vehículo
    """)
    return jsonify({'conductores': conductores or []})

@app.route('/api/conductores/<int:cedula>', methods=['GET'])
@api_login_required
def api_conductor(cedula):
    """Obtener un conductor específico"""
    conductor = ejecutar_consulta("""
        SELECT 
            c.cedula, c.nombre, c.apellido, c.licencia, c.fecha_registro, c.activo,
            v.matricula AS vehiculo_matricula,
            v.marca AS vehiculo_marca, 
            v.modelo AS vehiculo_modelo,
            v.linea_asignada,
            v.capacidad AS vehiculo_capacidad
        FROM conductor c 
        LEFT JOIN vehiculo v ON c.cedula = v.conductor_ci
        WHERE c.cedula = %s
    """, (cedula,), fetchone=True)
    
    if not conductor:
        return jsonify({'error': 'Conductor no encontrado'}), 404
    
    return jsonify({'conductor': conductor})

@app.route('/api/conductores', methods=['POST'])
@api_login_required
def api_crear_conductor():
    """Crear un nuevo conductor"""
    data = request.get_json()
    if not data or not all(k in data for k in ['cedula', 'nombre', 'apellido', 'licencia']):
        return jsonify({'error': 'Datos incompletos'}), 400

    existe = ejecutar_consulta("SELECT cedula FROM conductor WHERE cedula = %s", 
                              (data['cedula'],), 
                              fetchone=True)
    if existe:
        return jsonify({'error': 'Ya existe un conductor con esta cédula'}), 409

    if not ejecutar_consulta("""
        INSERT INTO conductor (cedula, nombre, apellido, licencia) 
        VALUES (%s, %s, %s, %s)
    """, (data['cedula'], data['nombre'], data['apellido'], data['licencia']), 
    commit=True):
        return jsonify({'error': 'Error al registrar conductor'}), 500

    if data.get('matricula'):
        modelo = data.get('modelo', '')
        linea_asignada = data.get('linea_asignada', None)
        capacidad = data.get('capacidad', 0)
        
        if not ejecutar_consulta("""
            INSERT INTO vehiculo (matricula, marca, modelo, linea_asignada, capacidad, conductor_ci) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data['matricula'],
            data['marca'],
            modelo,
            linea_asignada,
            capacidad,
            data['cedula']
        ), commit=True):
            return jsonify({'error': 'Error al registrar vehículo del conductor'}), 500

    return jsonify({'message': 'Conductor registrado correctamente'}), 201

@app.route('/api/conductores/<int:cedula>', methods=['PUT'])
@api_login_required
def api_actualizar_conductor(cedula):
    """Actualizar un conductor existente"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos requeridos'}), 400

    campos = []
    valores = []
    for campo in ['nombre', 'apellido', 'licencia']:
        if campo in data:
            campos.append(f"{campo} = %s")
            valores.append(data[campo])
    
    if not campos:
        return jsonify({'error': 'No hay datos para actualizar'}), 400
    
    valores.append(cedula)
    query = f"UPDATE conductor SET {', '.join(campos)} WHERE cedula = %s"
    
    if ejecutar_consulta(query, valores, commit=True):
        return jsonify({'message': 'Conductor actualizado correctamente'})
    
    return jsonify({'error': 'Error al actualizar conductor'}), 500

@app.route('/api/conductores/<int:cedula>', methods=['DELETE'])
@api_login_required
def api_eliminar_conductor(cedula):
    """Eliminar un conductor"""
    # Eliminar vehículos asociados
    ejecutar_consulta("DELETE FROM vehiculo WHERE conductor_ci = %s", (cedula,), commit=True)
    # Eliminar viajes asociados
    ejecutar_consulta("DELETE FROM viaje WHERE conductor_ci = %s", (cedula,), commit=True)
    # Eliminar conductor
    if ejecutar_consulta("DELETE FROM conductor WHERE cedula = %s", (cedula,), commit=True):
        return jsonify({'message': 'Conductor eliminado correctamente'})
    
    return jsonify({'error': 'Error al eliminar conductor'}), 500

# =====================================
# RUTA - VEHÍCULOS
# =====================================

@app.route('/api/vehiculos', methods=['GET'])
@api_login_required
def api_vehiculos():
    """Obtener todos los vehículos"""
    vehiculos = ejecutar_consulta("SELECT * FROM vehiculo")
    return jsonify({'vehiculos': vehiculos or []})

@app.route('/api/vehiculos/<matricula>', methods=['GET'])
@api_login_required
def api_vehiculo(matricula):
    """Obtener un vehículo específico"""
    vehiculo = ejecutar_consulta("SELECT * FROM vehiculo WHERE matricula = %s", 
                                (matricula,), 
                                fetchone=True)
    
    if not vehiculo:
        return jsonify({'error': 'Vehículo no encontrado'}), 404
    
    return jsonify({'vehiculo': vehiculo})

@app.route('/api/vehiculos', methods=['POST'])
@api_login_required
def api_crear_vehiculo():
    """Crear un nuevo vehículo"""
    data = request.get_json()
    if not data or not all(k in data for k in ['marca', 'conductor_ci']):
        return jsonify({'error': 'Datos incompletos'}), 400

    conductor = ejecutar_consulta("SELECT cedula FROM conductor WHERE cedula = %s", 
                                 (data['conductor_ci'],), 
                                 fetchone=True)
    if not conductor:
        return jsonify({'error': 'Conductor no encontrado'}), 404

    if ejecutar_consulta("""
        INSERT INTO vehiculo (marca, modelo, linea_asignada, capacidad, conductor_ci) 
        VALUES (%s, %s, %s, %s, %s)
    """, (
        data['marca'],
        data.get('modelo', ''),
        data.get('linea_asignada', None),
        data.get('capacidad', 0),
        data['conductor_ci']
    ), commit=True):
        return jsonify({'message': 'Vehículo registrado correctamente'}), 201
    
    return jsonify({'error': 'Error al registrar vehículo'}), 500

@app.route('/api/vehiculos/<matricula>', methods=['PUT'])
@api_login_required
def api_actualizar_vehiculo(matricula):
    """Actualizar un vehículo existente"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos requeridos'}), 400

    campos = []
    valores = []
    for campo in ['marca', 'modelo', 'linea_asignada', 'capacidad', 'conductor_ci']:
        if campo in data:
            campos.append(f"{campo} = %s")
            valores.append(data[campo])
    
    if not campos:
        return jsonify({'error': 'No hay datos para actualizar'}), 400
    
    valores.append(matricula)
    query = f"UPDATE vehiculo SET {', '.join(campos)} WHERE matricula = %s"
    
    if ejecutar_consulta(query, valores, commit=True):
        return jsonify({'message': 'Vehículo actualizado correctamente'})
    
    return jsonify({'error': 'Error al actualizar vehículo'}), 500

@app.route('/api/vehiculos/<matricula>', methods=['DELETE'])
@api_login_required
def api_eliminar_vehiculo(matricula):
    """Eliminar un vehículo"""
    if ejecutar_consulta("DELETE FROM vehiculo WHERE matricula = %s", (matricula,), commit=True):
        return jsonify({'message': 'Vehículo eliminado correctamente'})
    
    return jsonify({'error': 'Error al eliminar vehículo'}), 500

# =====================================
# RUTA - LÍNEAS
# =====================================

@app.route('/api/lineas/check-name', methods=['GET'])
@api_login_required
def api_check_linea_name():
    """Verificar si un nombre de línea ya existe"""
    nombre = request.args.get('nombre')
    if not nombre:
        return jsonify({'error': 'Parámetro nombre requerido'}), 400
    
    nombre_normalizado = nombre.strip().lower()
    
    existe = ejecutar_consulta(
        "SELECT id FROM linea WHERE LOWER(TRIM(nombre)) = %s", 
        (nombre_normalizado,), 
        fetchone=True
    )
    
    return jsonify({'exists': existe is not None})

@app.route('/api/lineas', methods=['GET'])
@api_login_required
def api_lineas():
    """Obtener todas las líneas"""
    lineas = ejecutar_consulta("SELECT * FROM linea ORDER BY nombre")
    return jsonify({'lineas': lineas or []})

@app.route('/api/lineas/<int:id>', methods=['GET'])
@api_login_required
def api_linea(id):
    """Obtener una línea específica"""
    linea = ejecutar_consulta("SELECT * FROM linea WHERE id = %s", (id,), fetchone=True)
    
    if not linea:
        return jsonify({'error': 'Línea no encontrada'}), 404
    
    return jsonify({'linea': linea})

@app.route('/api/lineas', methods=['POST'])
@api_login_required
def api_crear_linea():
    """Crear una nueva línea"""
    try:
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        
        if not nombre or not descripcion:
            return jsonify({'error': 'Nombre y descripción requeridos'}), 400
        
        nombre_normalizado = nombre.strip().lower()
        
        existe = ejecutar_consulta(
            "SELECT id FROM linea WHERE LOWER(TRIM(nombre)) = %s", 
            (nombre_normalizado,), 
            fetchone=True
        )
        if existe:
            return jsonify({'error': 'Ya existe una línea con este nombre'}), 409
        
        imagen_filename = None
        if 'imagen_logo' in request.files:
            file = request.files['imagen_logo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = str(int(time.time()))
                filename = f"{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                imagen_filename = filename
        
        if ejecutar_consulta("""
            INSERT INTO linea (nombre, descripcion, imagen_logo) 
            VALUES (%s, %s, %s)
        """, (nombre, descripcion, imagen_filename), commit=True):
            return jsonify({'message': 'Línea registrada correctamente'}), 201
        
        return jsonify({'error': 'Error al registrar línea'}), 500
            
    except Exception as e:
        return jsonify({'error': 'Error al procesar la solicitud'}), 500

@app.route('/api/lineas/<int:id>', methods=['PUT'])
@api_login_required
def api_actualizar_linea(id):
    """Actualizar una línea existente"""
    try:
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        
        if not nombre or not descripcion:
            return jsonify({'error': 'Nombre y descripción requeridos'}), 400
        
        linea = ejecutar_consulta("SELECT * FROM linea WHERE id = %s", (id,), fetchone=True)
        if not linea:
            return jsonify({'error': 'Línea no encontrada'}), 404
        
        imagen_filename = linea['imagen_logo']
        if 'imagen_logo' in request.files:
            file = request.files['imagen_logo']
            if file and file.filename != '' and allowed_file(file.filename):
                if imagen_filename:
                    try:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], imagen_filename)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception as e:
                        print(f"Error al eliminar imagen anterior: {e}")
                
                filename = secure_filename(file.filename)
                timestamp = str(int(time.time()))
                filename = f"{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                imagen_filename = filename
        
        if ejecutar_consulta("""
            UPDATE linea 
            SET nombre = %s, descripcion = %s, imagen_logo = %s 
            WHERE id = %s
        """, (nombre, descripcion, imagen_filename, id), commit=True):
            return jsonify({'message': 'Línea actualizada correctamente'})
        
        return jsonify({'error': 'Error al actualizar línea'}), 500
            
    except Exception as e:
        return jsonify({'error': 'Error al procesar la solicitud'}), 500

@app.route('/api/lineas/<int:id>', methods=['DELETE'])
@api_login_required
def api_eliminar_linea(id):
    """Eliminar una línea"""
    try:
        linea = ejecutar_consulta("SELECT imagen_logo FROM linea WHERE id = %s", (id,), fetchone=True)
        
        if linea and linea['imagen_logo']:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], linea['imagen_logo'])
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error al eliminar imagen: {e}")
        
        if ejecutar_consulta("DELETE FROM linea WHERE id = %s", (id,), commit=True):
            return jsonify({'message': 'Línea eliminada correctamente'})
        
        return jsonify({'error': 'Error al eliminar línea'}), 500
            
    except Exception as e:
        return jsonify({'error': 'Error al eliminar línea'}), 500

# =====================================
# RUTA - VIAJES
# =====================================

@app.route('/api/viajes', methods=['GET'])
@api_login_required
def api_viajes():
    """Obtener todos los viajes"""
    viajes = ejecutar_consulta("""
        SELECT v.*, c.nombre, c.apellido 
        FROM viaje v 
        JOIN conductor c ON v.conductor_ci = c.cedula
    """)
    return jsonify({'viajes': viajes or []})

@app.route('/api/viajes/<int:id>', methods=['GET'])
@api_login_required
def api_viaje(id):
    """Obtener un viaje específico"""
    viaje = ejecutar_consulta("""
        SELECT v.*, 
               c.nombre AS nombre_conductor,
               c.apellido AS apellido_conductor,
               c.licencia,
               c.cedula,
               vh.marca,
               vh.matricula,
               vh.modelo,
               vh.linea_asignada,
               vh.capacidad
        FROM viaje v
        JOIN conductor c ON v.conductor_ci = c.cedula
        LEFT JOIN vehiculo vh ON c.cedula = vh.conductor_ci
        WHERE v.id = %s
    """, (id,), fetchone=True)
    
    if not viaje:
        return jsonify({'error': 'Viaje no encontrado'}), 404
    
    return jsonify({'viaje': viaje})

@app.route('/api/viajes', methods=['POST'])
@api_login_required
def api_crear_viaje():
    """Crear un nuevo viaje"""
    try:
        data = request.get_json()
        print(f"Datos recibidos para crear viaje: {data}")
        
        # Validar campos requeridos
        required_fields = ['paradas', 'rutas', 'fecha_salida', 'fecha_llegada', 'conductor_ci', 'waypoints', 'distancia']
        
        if not data or not all(k in data for k in required_fields):
            missing_fields = [field for field in required_fields if field not in data]
            print(f"Campos faltantes: {missing_fields}")
            return jsonify({'error': f'Datos incompletos. Faltan: {", ".join(missing_fields)}'}), 400
        
        # Validar tipos de datos
        try:
            conductor_ci = int(data['conductor_ci'])
            distancia = float(data['distancia'])
            waypoints = data['waypoints']
            
            if not isinstance(waypoints, list) or len(waypoints) < 2:
                return jsonify({'error': 'Se requieren al menos 2 waypoints para crear una ruta'}), 400
                
        except (ValueError, TypeError) as e:
            print(f"Error de validación de tipos: {e}")
            return jsonify({'error': 'Tipos de datos incorrectos'}), 400
        
        # Validar fechas
        try:
            fecha_salida_str = data['fecha_salida']
            fecha_llegada_str = data['fecha_llegada']
            
            if fecha_salida_str.endswith('Z'):
                fecha_salida_str = fecha_salida_str[:-1]
            if fecha_llegada_str.endswith('Z'):
                fecha_llegada_str = fecha_llegada_str[:-1]
                
            if 'T' in fecha_salida_str:
                fecha_salida = datetime.fromisoformat(fecha_salida_str)
            else:
                fecha_salida = datetime.strptime(fecha_salida_str, '%Y-%m-%d %H:%M:%S')
                
            if 'T' in fecha_llegada_str:
                fecha_llegada = datetime.fromisoformat(fecha_llegada_str)
            else:
                fecha_llegada = datetime.strptime(fecha_llegada_str, '%Y-%m-%d %H:%M:%S')
            
            if fecha_llegada <= fecha_salida:
                return jsonify({'error': 'La fecha de llegada debe ser posterior a la fecha de salida'}), 400
                
        except ValueError as e:
            print(f"Error de formato de fecha: {e}")
            return jsonify({'error': f'Formato de fecha inválido: {str(e)}'}), 400
        
        # Validar que el conductor existe
        conductor = ejecutar_consulta("SELECT cedula FROM conductor WHERE cedula = %s", 
                                    (conductor_ci,), 
                                    fetchone=True)
        if not conductor:
            return jsonify({'error': 'Conductor no encontrado'}), 404
        
        # Obtener vehículo del conductor
        vehiculo = ejecutar_consulta(
            "SELECT matricula FROM vehiculo WHERE conductor_ci = %s LIMIT 1", 
            (conductor_ci,), 
            fetchone=True
        )
        
        if not vehiculo:
            return jsonify({
                'error': 'El conductor no tiene vehículo asignado',
                'suggestion': 'Asigne un vehículo al conductor antes de crear el viaje'
            }), 400
        
        try:
            waypoints_str = ';'.join([f"{wp['lat']},{wp['lng']}" for wp in waypoints])
        except KeyError as e:
            print(f"Error en formato de waypoints: {e}")
            return jsonify({'error': f'Formato de coordenadas inválido: {str(e)}'}), 400
        
        query = """
            INSERT INTO viaje (
                paradas, rutas_asignadas, distancia_destino,
                fecha_salida, fecha_llegada, conductor_ci, vehiculo_id, 
                ruta_coordenadas, distancia_calculada, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data['paradas'],
            data['rutas'],
            distancia,
            fecha_salida.strftime('%Y-%m-%d %H:%M:%S'),
            fecha_llegada.strftime('%Y-%m-%d %H:%M:%S'),
            conductor_ci,
            vehiculo['matricula'],
            waypoints_str,
            distancia,
            'programado'
        )
        
        print(f"Query: {query % params}")
        
        # Ejecutar consulta con manejo detallado de errores
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            viaje_id = cursor.lastrowid
            cursor.close()
            conn.close()
            
            print(f"Viaje creado exitosamente con ID: {viaje_id}")
            return jsonify({
                'message': 'Viaje registrado correctamente',
                'viaje_id': viaje_id
            }), 201
        except mysql.connector.Error as err:
            print(f"Error de MySQL: {err}")
            return jsonify({
                'error': 'Error de base de datos',
                'details': str(err),
                'errno': err.errno,
                'sqlstate': err.sqlstate
            }), 500
        except Exception as e:
            print(f"Error inesperado: {e}")
            return jsonify({'error': f'Error inesperado: {str(e)}'}), 500
    
    except Exception as e:
        print(f"Error general al crear viaje: {e}")
        return jsonify({'error': f'Error interno del servidor: {str(e)}'}), 500

@app.route('/api/viajes/<int:id>', methods=['DELETE'])
@api_login_required
def api_eliminar_viaje(id):
    """Eliminar un viaje específico"""
    try:
        ejecutar_consulta("DELETE FROM sistema_analitico WHERE viaje_id = %s", (id,), commit=True)
        
        if ejecutar_consulta("DELETE FROM viaje WHERE id = %s", (id,), commit=True):
            return jsonify({'message': 'Viaje eliminado correctamente'})
        
        return jsonify({'error': 'Error al eliminar viaje'}), 500
            
    except mysql.connector.Error as err:
        print(f"Error de base de datos: {err}")
        return jsonify({'error': f'Error de base de datos: {err}'}), 500
    except Exception as e:
        print(f"Error inesperado: {e}")
        return jsonify({'error': f'Error inesperado: {e}'}), 500

# =====================================
# RUTA - VISUALIZAR MAPA DE VIAJES
# =====================================

@app.route('/ver-mapa-ruta/<int:id>')
@login_required
def ver_mapa_ruta(id):
    """Mostrar mapa de ruta de un viaje en modo solo lectura"""
    return render_template('ver_mapa.html')

# =====================================
# RUTA - ANÁLISIS
# =====================================

@app.route('/api/analiticos', methods=['GET'])
@api_login_required
def api_analiticos():
    """Obtener todos los análisis"""
    analiticos = ejecutar_consulta("SELECT * FROM sistema_analitico")
    return jsonify({'analiticos': analiticos or []})

@app.route('/api/analiticos', methods=['POST'])
@api_login_required
def api_crear_analitico():
    """Crear un nuevo análisis"""
    data = request.get_json()
    required_fields = ['viaje_id', 'tipo_analisis', 'resultado']
    
    if not data or not all(k in data for k in required_fields):
        return jsonify({'error': 'Datos incompletos'}), 400
    
    # Verificar si el viaje existe
    viaje = ejecutar_consulta("SELECT id FROM viaje WHERE id = %s", 
                             (data['viaje_id'],), 
                             fetchone=True)
    if not viaje:
        return jsonify({'error': 'Viaje no encontrado'}), 404
    
    if ejecutar_consulta("""
        INSERT INTO sistema_analitico (viaje_id, tipo_analisis, resultado, puntuacion) 
        VALUES (%s, %s, %s, %s)
    """, (
        data['viaje_id'],
        data['tipo_analisis'],
        data['resultado'],
        data.get('puntuacion', None)
    ), commit=True):
        return jsonify({'message': 'Análisis registrado correctamente'}), 201
    
    return jsonify({'error': 'Error al registrar análisis'}), 500

# =====================================
# RUTA - MAPAS
# =====================================

@app.route('/mapa-rutas')
@login_required
def mapa_rutas():
    return render_template('mapa.html')

@app.route('/api/viajes/<int:id>/ruta', methods=['POST'])
@api_login_required
def api_guardar_ruta(id):
    data = request.get_json()
    
    # Verificar que el viaje existe
    viaje = ejecutar_consulta("SELECT id FROM viaje WHERE id = %s", (id,), fetchone=True)
    if not viaje:
        return jsonify({'success': False, 'error': 'Viaje no encontrado'}), 404
    
    waypoints_str = ';'.join([f"{wp['lat']},{wp['lng']}" for wp in data['waypoints']])
    
    try:
        if ejecutar_consulta("""
            UPDATE viaje 
            SET ruta_coordenadas = %s, distancia_calculada = %s 
            WHERE id = %s
        """, (waypoints_str, data['distancia'], id), commit=True):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Error en la base de datos'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

#ruta para guardar datos temporales de ruta
@app.route('/guardar_ruta', methods=['POST'])
@api_login_required
def guardar_ruta_temporal():
    """Guardar datos de ruta temporalmente en la sesión"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400
        
        coordenadas = data.get('coordenadas', [])
        if not coordenadas or len(coordenadas) < 2:
            return jsonify({
                'success': False,
                'message': 'Se necesitan al menos 2 puntos para crear una ruta'
            }), 400
        
        for i, coord in enumerate(coordenadas):
            if not isinstance(coord, dict) or 'lat' not in coord or 'lng' not in coord:
                return jsonify({
                    'success': False,
                    'message': f'Coordenada {i+1} tiene formato inválido'
                }), 400
        
        session['ruta_temporal'] = {
            'coordenadas': coordenadas,
            'distancia': float(data.get('distancia', 0)),
            'tiempo': data.get('tiempo', '0'),
            'paradas': data.get('paradas', len(coordenadas))
        }
        
        print(f"Ruta temporal guardada: {session['ruta_temporal']}")
        
        return jsonify({
            'success': True,
            'message': 'Ruta guardada temporalmente'
        })
    except Exception as e:
        print(f"Error en guardar_ruta_temporal: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error al guardar ruta: {str(e)}'
        }), 500

@app.route('/api/ruta-temporal', methods=['GET'])
@api_login_required
def obtener_ruta_temporal():
    """Obtener datos de ruta temporal de la sesión"""
    ruta_temporal = session.get('ruta_temporal', None)
    if ruta_temporal:
        return jsonify({
            'success': True,
            'ruta': ruta_temporal
        })
    else:
        return jsonify({
            'success': False,
            'message': 'No hay ruta temporal guardada'
        })

# =====================================
# RUTAS PARA TEMPLATES
# =====================================

@app.route('/')
@app.route('/login')
def inicio():
    if 'usuario' in session:
        return redirect(url_for('dashboard'))
    
    # Verificar si existe un usuario
    usuario = ejecutar_consulta("SELECT * FROM usuario LIMIT 1", fetchone=True)
    
    if not usuario:
        return redirect(url_for('registro_inicial'))
    
    return render_template('login.html')

@app.route('/registro-inicial', methods=['GET', 'POST'])
def registro_inicial():
    if ejecutar_consulta("SELECT * FROM usuario LIMIT 1", fetchone=True):
        return redirect(url_for('inicio'))
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        contrasena = bcrypt.generate_password_hash(request.form['contrasena']).decode('utf-8')
        
        ejecutar_consulta("INSERT INTO usuario (id, nombre_usuario, contrasena) VALUES (%s, %s, %s)", 
                         (1, nombre, contrasena), commit=True)
        
        flash('Usuario creado correctamente')
        return redirect(url_for('inicio'))
    
    return render_template('registro_inicial.html')

@app.route('/cerrar-sesion')
def cerrar_sesion():
    session.clear()
    return redirect(url_for('inicio'))

@app.route('/dashboard')
@login_required
def dashboard():
    conductores = ejecutar_consulta("SELECT COUNT(*) as total FROM conductor")
    viajes = ejecutar_consulta("SELECT COUNT(*) as total FROM viaje")
    lineas = ejecutar_consulta("SELECT COUNT(*) as total FROM linea")
    
    return render_template('dashboard.html', 
                          total_conductores=conductores[0]['total'] if conductores else 0,
                          total_viajes=viajes[0]['total'] if viajes else 0,
                          total_lineas=lineas[0]['total'] if lineas else 0)

@app.route('/conductores', methods=['GET'])
@login_required
def conductores():
    lista_conductores = ejecutar_consulta("""
        SELECT c.*, v.marca, v.matricula, v.linea_asignada, v.capacidad
        FROM conductor c 
        LEFT JOIN vehiculo v ON c.cedula = v.conductor_ci
    """)
    return render_template('conductores.html', conductores=lista_conductores)

@app.route('/ver-conductor/<int:cedula>')
@login_required
def ver_conductor(cedula):
    conductor = ejecutar_consulta("""
        SELECT c.*, v.marca, v.matricula, v.linea_asignada, v.capacidad
        FROM conductor c 
        LEFT JOIN vehiculo v ON c.cedula = v.conductor_ci
        WHERE c.cedula = %s
    """, (cedula,), fetchone=True)
    
    if not conductor:
        flash('Conductor no encontrado')
        return redirect(url_for('conductores'))
    
    return render_template('ver_conductor.html', conductor=conductor)

@app.route('/registrar-conductor', methods=['GET', 'POST'])
@login_required
def registrar_conductor():
    if request.method == 'POST':
        cedula = request.form['cedula']
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        licencia = request.form['licencia']
        
        ejecutar_consulta("""
            INSERT INTO conductor (cedula, nombre, apellido, licencia) 
            VALUES (%s, %s, %s, %s)
        """, (cedula, nombre, apellido, licencia), commit=True)
        
        if request.form.get('marca'):
            ejecutar_consulta("""
                INSERT INTO vehiculo (marca, linea_asignada, capacidad, conductor_ci) 
                VALUES (%s, %s, %s, %s)
            """, (
                request.form['marca'],
                request.form.get('linea', ''),
                request.form.get('capacidad', 0),
                cedula
            ), commit=True)
        
        flash('Conductor registrado correctamente')
        return redirect(url_for('conductores'))
    
    return render_template('registrar_conductor.html')

@app.route('/eliminar-conductor/<int:cedula>')
@login_required
def eliminar_conductor(cedula):
    # Eliminar vehículos asociados
    ejecutar_consulta("DELETE FROM vehiculo WHERE conductor_ci = %s", (cedula,), commit=True)
    # Eliminar viajes asociados
    ejecutar_consulta("DELETE FROM viaje WHERE conductor_ci = %s", (cedula,), commit=True)
    # Eliminar conductor
    ejecutar_consulta("DELETE FROM conductor WHERE cedula = %s", (cedula,), commit=True)
    
    flash('Conductor eliminado correctamente')
    return redirect(url_for('conductores'))

@app.route('/viajes')
@login_required
def viajes():
    lista_viajes = ejecutar_consulta("""
        SELECT v.paradas, v.rutas_asignadas, 
               v.distancia_destino as distancia, 
               v.fecha_salida, 
               v.fecha_llegada, 
               c.nombre, c.apellido, c.cedula as conductor_ci
        FROM viaje v 
        JOIN conductor c ON v.conductor_ci = c.cedula
    """)
    
    return render_template('viajes.html', viajes=lista_viajes)

@app.route('/ver-viaje/<int:id>')
@login_required
def ver_viaje(id):
    return render_template('ver_viaje.html')

@app.route('/registrar-viaje', methods=['GET', 'POST'])
@login_required
def registrar_viaje():
    if request.method == 'POST':
        paradas = request.form['paradas']
        rutas = request.form['rutas']
        distancia = request.form['distancia']
        fecha_salida = request.form['fecha_salida']
        fecha_llegada = request.form['fecha_llegada']
        conductor_ci = request.form['conductor_ci']
        
        vehiculo = ejecutar_consulta(
            "SELECT matricula FROM vehiculo WHERE conductor_ci = %s LIMIT 1", 
            (conductor_ci,), 
            fetchone=True
        )
        
        vehiculo_id = vehiculo['matricula'] if vehiculo else None
        
        ejecutar_consulta("""
            INSERT INTO viaje (paradas, rutas_asignadas, distancia_destino, 
                              fecha_salida, fecha_llegada, conductor_ci, vehiculo_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            paradas,
            rutas,
            distancia,
            fecha_salida,
            fecha_llegada,
            conductor_ci,
            vehiculo_id
        ), commit=True)
        
        flash('Viaje registrado correctamente')
        return redirect(url_for('viajes'))
    
    conductores = ejecutar_consulta("SELECT cedula, nombre, apellido FROM conductor")
    return render_template('registrar_viaje.html', conductores=conductores)

@app.route('/eliminar-viaje')
@login_required
def eliminar_viaje():
    paradas = request.args.get('paradas')
    fecha_salida = request.args.get('fecha_salida')
    
    if not paradas or not fecha_salida:
        flash('Error: Parámetros incompletos para eliminar el viaje')
        return redirect(url_for('viajes'))
    
    ejecutar_consulta("""
        DELETE FROM viaje 
        WHERE paradas = %s AND fecha_salida = %s
    """, (paradas, fecha_salida), commit=True)
    
    flash('Viaje eliminado correctamente')
    return redirect(url_for('viajes'))

@app.route('/lineas')
@login_required
def lineas():
    try:
        lista_lineas = ejecutar_consulta("SELECT * FROM linea ORDER BY nombre")
        if lista_lineas is None:
            lista_lineas = []
        return render_template('lineas.html', lineas=lista_lineas)
    except Exception as e:
        print(f"Error al obtener líneas: {e}")
        flash("Error al cargar las líneas. Asegúrese de que la tabla existe en la base de datos.")
        return render_template('lineas.html', lineas=[])

@app.route('/registrar-linea', methods=['GET', 'POST'])
@login_required
def registrar_linea():
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            
            nombre_normalizado = nombre.strip().lower()
            existe = ejecutar_consulta(
                "SELECT id FROM linea WHERE LOWER(TRIM(nombre)) = %s", 
                (nombre_normalizado,), 
                fetchone=True
            )
            if existe:
                flash('Ya existe una línea con este nombre')
                return redirect(url_for('registrar_linea'))
            
            imagen_filename = None
            if 'imagen_logo' in request.files:
                file = request.files['imagen_logo']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = str(int(time.time()))
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    imagen_filename = filename
            
            resultado = ejecutar_consulta("""
                INSERT INTO linea (nombre, descripcion, imagen_logo) 
                VALUES (%s, %s, %s)
            """, (nombre, descripcion, imagen_filename), commit=True)
            
            if resultado is not None:
                flash('Línea registrada correctamente')
            else:
                flash('Error al registrar la línea. Verifique que la tabla existe.')
                
        except Exception as e:
            print(f"Error al registrar línea: {e}")
            flash('Error al registrar la línea.')
            
        return redirect(url_for('lineas'))
    
    return render_template('registrar_linea.html')

@app.route('/ver-linea/<int:id>')
@login_required
def ver_linea(id):
    try:
        linea = ejecutar_consulta("SELECT * FROM linea WHERE id = %s", (id,), fetchone=True)
        
        if not linea:
            flash('Línea no encontrada')
            return redirect(url_for('lineas'))
        
        return render_template('ver_linea.html', linea=linea)
    except Exception as e:
        print(f"Error al obtener línea: {e}")
        flash('Error al cargar la información de la línea.')
        return redirect(url_for('lineas'))

@app.route('/eliminar-linea/<int:id>')
@login_required
def eliminar_linea(id):
    try:
        linea = ejecutar_consulta("SELECT imagen_logo FROM linea WHERE id = %s", (id,), fetchone=True)
        
        if linea and linea['imagen_logo']:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], linea['imagen_logo'])
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error al eliminar imagen: {e}")
        
        resultado = ejecutar_consulta("DELETE FROM linea WHERE id = %s", (id,), commit=True)
        
        if resultado is not None:
            flash('Línea eliminada correctamente')
        else:
            flash('Error al eliminar la línea.')
            
    except Exception as e:
        print(f"Error al eliminar línea: {e}")
        flash('Error al eliminar la línea.')
    
    return redirect(url_for('lineas'))

@app.route('/opciones', methods=['GET', 'POST'])
@login_required
def opciones():
    if request.method == 'POST':
        accion = request.form.get('accion')
        
        if accion == 'cambiar_credenciales':
            usuario_id = session['usuario_id']
            contrasena_actual = request.form['contrasena_actual']
            
            usuario = ejecutar_consulta("SELECT * FROM usuario WHERE id = %s", (usuario_id,), fetchone=True)
            
            if usuario and bcrypt.check_password_hash(usuario['contrasena'], contrasena_actual):
                nuevo_nombre = request.form['nuevo_usuario']
                nueva_contrasena = bcrypt.generate_password_hash(request.form['nueva_contrasena']).decode('utf-8')
                
                ejecutar_consulta("""
                    UPDATE usuario 
                    SET nombre_usuario = %s, contrasena = %s 
                    WHERE id = %s
                """, (nuevo_nombre, nueva_contrasena, usuario_id), commit=True)
                
                flash('Credenciales actualizadas correctamente')
                return redirect(url_for('cerrar_sesion'))
            
            flash('Contraseña actual incorrecta')
        
        elif accion == 'eliminar_datos':
            # Eliminar todos los viajes
            ejecutar_consulta("DELETE FROM viaje", commit=True)
            # Eliminar todos los vehículos
            ejecutar_consulta("DELETE FROM vehiculo", commit=True)
            # Eliminar todos los conductores
            ejecutar_consulta("DELETE FROM conductor", commit=True)
            # Eliminar todas las líneas
            ejecutar_consulta("DELETE FROM linea", commit=True)
            
            flash('Toda la información ha sido eliminada correctamente')
    
    return render_template('opciones.html')

if __name__ == '__main__':
    if verificar_esquema():
        print("Esquema verificado y actualizado correctamente")
    else:
        print("Hubo problemas al verificar el esquema")
    
    limpiar_archivos_huerfanos()
    app.run(debug=True, port=5000)