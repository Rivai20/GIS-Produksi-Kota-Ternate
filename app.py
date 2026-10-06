import json
import os
from decimal import Decimal, InvalidOperation
from functools import wraps

import mysql.connector
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'gis-ternate-development-key')


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', '127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', 'gis_ternate'),
    )


def current_user():
    return session.get('user')


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if current_user() is None:
            return jsonify({'error': 'Silakan login terlebih dahulu'}), 401
        return view(*args, **kwargs)
    return wrapped_view


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({'error': 'Silakan login terlebih dahulu'}), 401
            if user['role'] not in roles:
                return jsonify({'error': 'Role Anda tidak memiliki akses ini'}), 403
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


def allowed_production_type(role):
    return 'fish' if role == 'admin_perikanan' else 'agriculture'


def is_fish_type(type_name):
    return type_name in ('fish', 'Hasil Tangkapan Ikan')


DATASET_TABLES = {
    'fish': {'fish_production': True},
    'agriculture': {
        'crop_production': True,
        'horticulture_production': False,
    },
}
DATASET_FIELDS = {
    'fish_production': ('district_name', 'commodity', 'year', 'production_ton'),
    'crop_production': ('district_name', 'commodity', 'year', 'production_ton'),
    'horticulture_production': ('commodity', 'year', 'production_ton'),
}


def dataset_domain_for_role(role):
    if role == 'admin_perikanan':
        return 'fish'
    if role == 'admin_pertanian':
        return 'agriculture'
    return None


def dataset_table_config(domain, table_name):
    tables = DATASET_TABLES.get(domain, {})
    if table_name not in tables:
        return None
    return {'has_district': tables[table_name]}


def serialize_dataset_row(row):
    if row is None:
        return None
    return {
        key: format(value, 'f') if isinstance(value, Decimal) else value
        for key, value in row.items()
    }


def decode_json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def validate_dataset_entry(data, table_name):
    domain = next((key for key, tables in DATASET_TABLES.items() if table_name in tables), None)
    config = dataset_table_config(domain, table_name)
    if config is None:
        return None, 'Tabel dataset tidak valid'

    commodity = str(data.get('commodity', '')).strip()
    if not commodity or len(commodity) > 100:
        return None, 'Nama komoditas wajib diisi dan maksimal 100 karakter'

    entry = {'commodity': commodity}
    if config['has_district']:
        district_name = str(data.get('district_name', '')).strip()
        if not district_name or len(district_name) > 40:
            return None, 'Kecamatan wajib diisi dan maksimal 40 karakter'
        entry['district_name'] = district_name

    try:
        year = int(data.get('year'))
    except (TypeError, ValueError):
        return None, 'Tahun harus berupa angka yang valid'
    if year < 1900 or year > 2100:
        return None, 'Tahun harus berada antara 1900 dan 2100'

    try:
        production = Decimal(str(data.get('production_ton', '')))
    except (InvalidOperation, ValueError):
        return None, 'Produksi harus berupa angka yang valid'
    if not production.is_finite() or production < 0 or production > Decimal('1000000'):
        return None, 'Produksi harus antara 0 dan 1.000.000 ton'

    entry['year'] = year
    entry['production_ton'] = format(production.quantize(Decimal('0.001')), '.3f')
    return entry, None


def insert_dataset_entry(cursor, table_name, entry, source_file):
    fields = DATASET_FIELDS[table_name] + ('source_file',)
    columns = ', '.join(f'`{field}`' for field in fields)
    placeholders = ', '.join(['%s'] * len(fields))
    values = tuple(entry[field] for field in DATASET_FIELDS[table_name]) + (source_file,)
    cursor.execute(
        f'INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})',
        values,
    )


def update_dataset_entry(cursor, table_name, record_id, entry):
    assignments = ', '.join(f'`{field}` = %s' for field in entry)
    cursor.execute(
        f'UPDATE `{table_name}` SET {assignments} WHERE id = %s',
        tuple(entry.values()) + (record_id,),
    )


def row_matches_snapshot(current, snapshot):
    return serialize_dataset_row(current) == snapshot


def calculate_clusters(districts, metric='all', cluster_count=3):
    if len(districts) < cluster_count:
        return
    if metric == 'fish':
        points = [(district['production']['ikan'],) for district in districts]
    elif metric == 'agriculture':
        points = [(district['production']['pertanian'],) for district in districts]
    else:
        points = [
            (district['production']['ikan'], district['production']['pertanian'], district['production']['total'])
            for district in districts
        ]
    ordered_points = sorted(points, key=lambda point: point[-1])
    centers = [ordered_points[0], ordered_points[len(ordered_points) // 2], ordered_points[-1]]
    assignments = [0] * len(points)

    for _ in range(20):
        next_assignments = []
        for point in points:
            distances = [sum((value - center[index]) ** 2 for index, value in enumerate(point)) for center in centers]
            next_assignments.append(distances.index(min(distances)))
        if next_assignments == assignments:
            break
        assignments = next_assignments
        for index in range(cluster_count):
            members = [point for point, assignment in zip(points, assignments) if assignment == index]
            if members:
                centers[index] = tuple(
                    sum(point[axis] for point in members) / len(members)
                    for axis in range(len(points[0]))
                )

    cluster_order = sorted(range(cluster_count), key=lambda index: centers[index][-1])
    labels = {cluster_index: rank + 1 for rank, cluster_index in enumerate(cluster_order)}
    for district, assignment in zip(districts, assignments):
        district['cluster'] = labels[assignment]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if current_user() is not None:
            return redirect(url_for('index'))
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('SELECT id, username, password_hash, full_name, role FROM users WHERE username = %s', (username,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    if user is None or not check_password_hash(user['password_hash'], password):
        return render_template('login.html', error='Username atau password salah'), 401

    session['user'] = {
        'id': user['id'],
        'username': user['username'],
        'full_name': user['full_name'],
        'role': user['role'],
    }
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/session')
def session_info():
    return jsonify({'authenticated': current_user() is not None, 'user': current_user()})


@app.route('/api/dataset')
def dataset():
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT name, value, cluster, coords, production_ikan, '
            'production_pertanian, production_total, commodity, type_name '
            'FROM districts ORDER BY id'
        )
        districts = cursor.fetchall()
        cursor.execute('''
            SELECT district_name, SUM(production_ton) AS production
            FROM fish_production
            WHERE year = (SELECT MAX(year) FROM fish_production)
            GROUP BY district_name
        ''')
        latest_fish = {row['district_name']: float(row['production']) for row in cursor.fetchall()}
        cursor.execute('''
            SELECT district_name, SUM(production_ton) AS production
            FROM crop_production
            WHERE year = (SELECT MAX(year) FROM crop_production)
            GROUP BY district_name
        ''')
        latest_agriculture = {
            row['district_name']: float(row['production']) for row in cursor.fetchall()
        }
        cursor.execute('''
            SELECT markers.district_name, records.type_name,
                   SUM(records.production) AS production
            FROM production_records records
                        JOIN production_markers markers
                            ON markers.latitude = records.latitude
                         AND markers.longitude = records.longitude
            WHERE records.status = 'verified'
            GROUP BY markers.district_name, records.type_name
        ''')
        verified_updates = {}
        for row in cursor.fetchall():
            district_updates = verified_updates.setdefault(row['district_name'], {})
            metric = 'ikan' if is_fish_type(row['type_name']) else 'pertanian'
            district_updates[metric] = district_updates.get(metric, 0) + float(row['production'])
        cursor.execute(
            'SELECT id, label, value, type_name, emoji, latitude, longitude, district_name '
            'FROM production_markers ORDER BY id'
        )
        markers = cursor.fetchall()
        cursor.execute(
            "SELECT CONCAT('Pengajuan: ', commodity) AS label, "
            "CONCAT(production, ' ton') AS value, "
            "CASE WHEN records.type_name IN ('fish', 'Hasil Tangkapan Ikan') THEN 'fish' ELSE 'leaf' END AS type_name, "
            "CASE WHEN records.type_name IN ('fish', 'Hasil Tangkapan Ikan') THEN '🐟' ELSE '🌿' END AS emoji, "
            'records.latitude, records.longitude, markers.district_name FROM production_records records '
            'JOIN production_markers markers ON markers.latitude = records.latitude '
            'AND markers.longitude = records.longitude WHERE records.status = %s',
            ('verified',),
        )
        markers.extend(cursor.fetchall())

        commodity_details = []
        for table_name, domain, has_district in (
            ('fish_production', 'fish', True),
            ('crop_production', 'agriculture', True),
            ('horticulture_production', 'agriculture', False),
        ):
            district_column = 'district_name' if has_district else 'NULL AS district_name'
            scope = 'Kecamatan' if has_district else 'Seluruh Kota'
            cursor.execute(f'''
                SELECT %s AS domain, %s AS source_table, {district_column},
                       commodity, year, production_ton, %s AS scope
                FROM `{table_name}`
                WHERE year = (SELECT MAX(year) FROM `{table_name}`)
                ORDER BY commodity, district_name
            ''', (domain, table_name, scope))
            commodity_details.extend(cursor.fetchall())

        cursor.execute('''
            SELECT CASE WHEN records.type_name IN ('fish', 'Hasil Tangkapan Ikan')
                        THEN 'fish' ELSE 'agriculture' END AS domain,
                   'production_records' AS source_table, markers.district_name,
                   records.commodity, YEAR(records.created_at) AS year,
                   records.production AS production_ton, 'Kecamatan' AS scope
            FROM production_records records
            JOIN production_markers markers
              ON markers.latitude = records.latitude
             AND markers.longitude = records.longitude
            WHERE records.status = 'verified'
            ORDER BY records.created_at DESC
        ''')
        verified_details = cursor.fetchall()
        verified_detail_scopes = {
            (record['domain'], record['district_name']) for record in verified_details
        }
        commodity_details = [
            record for record in commodity_details
            if record['district_name'] is None
            or (record['domain'], record['district_name']) not in verified_detail_scopes
        ]
        commodity_details.extend(verified_details)
        for record in commodity_details:
            record['production_ton'] = float(record['production_ton'])

        for district in districts:
            if isinstance(district['coords'], str):
                district['coords'] = json.loads(district['coords'])
            imported_fish = latest_fish.get(district['name'], 0)
            imported_agriculture = latest_agriculture.get(district['name'], 0)
            updates = verified_updates.get(district['name'], {})
            production_fish = updates.get('ikan', imported_fish)
            production_agriculture = updates.get('pertanian', imported_agriculture)
            district['production'] = {
                'ikan': production_fish,
                'pertanian': production_agriculture,
                'total': production_fish + production_agriculture,
            }
            district.pop('production_ikan')
            district.pop('production_pertanian')
            district.pop('production_total')
        for marker in markers:
            marker['coords'] = [float(marker.pop('latitude')), float(marker.pop('longitude'))]
        metric = request.args.get('commodity', 'all')
        if metric not in ('all', 'fish', 'agriculture'):
            return jsonify({'error': 'Filter komoditas tidak valid'}), 400
        calculate_clusters(districts, metric=metric)

        return jsonify({
            'districts': districts,
            'markers': markers,
            'commodity_details': commodity_details,
        })
    except mysql.connector.Error as error:
        return jsonify({'error': f'Koneksi MySQL gagal: {error}'}), 500
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route('/api/production', methods=['GET', 'POST'])
@login_required
def production_records():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    if request.method == 'GET':
        query = (
            'SELECT p.*, u.full_name AS creator_name FROM production_records p '
            'JOIN users u ON u.id = p.created_by'
        )
        params = []
        if current_user()['role'] in ('admin_pertanian', 'admin_perikanan'):
            query += " WHERE p.status = 'pending' AND p.type_name IN (%s, %s)"
            if allowed_production_type(current_user()['role']) == 'fish':
                params.extend(['fish', 'Hasil Tangkapan Ikan'])
            else:
                params.extend(['leaf', 'Hasil Pertanian'])
        query += ' ORDER BY p.created_at DESC'
        cursor.execute(query, params)
        records = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(records)

    data = request.get_json(silent=True) or request.form
    required = ('commodity', 'production', 'marker_id')
    if any(not str(data.get(field, '')).strip() for field in required):
        cursor.close()
        connection.close()
        return jsonify({'error': 'Komoditas, produksi, dan titik lokasi wajib dipilih'}), 400
    try:
        production = Decimal(str(data['production']))
    except (InvalidOperation, ValueError):
        cursor.close()
        connection.close()
        return jsonify({'error': 'Produksi harus berupa angka yang valid'}), 400
    if production <= 0 or production > Decimal('1000000'):
        cursor.close()
        connection.close()
        return jsonify({'error': 'Produksi harus lebih dari 0 dan maksimal 1.000.000 ton'}), 400
    cursor.execute(
        'SELECT label, type_name, latitude, longitude FROM production_markers WHERE id = %s',
        (data['marker_id'],),
    )
    marker = cursor.fetchone()
    if marker is None:
        cursor.close()
        connection.close()
        return jsonify({'error': 'Titik lokasi tidak tersedia. Silakan pilih titik yang ada di peta.'}), 400
    cursor.execute(
        'INSERT INTO production_records '
        '(commodity, production, type_name, latitude, longitude, location, status, created_by) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (data['commodity'], production, marker['type_name'], marker['latitude'],
         marker['longitude'], marker['label'], 'pending', current_user()['id']),
    )
    connection.commit()
    record_id = cursor.lastrowid
    cursor.close()
    connection.close()
    return jsonify({'id': record_id, 'message': 'Data berhasil dikirim dan menunggu verifikasi'}), 201


@app.route('/api/production/<int:record_id>/verify', methods=['PATCH'])
@roles_required('admin_pertanian', 'admin_perikanan')
def verify_production(record_id):
    status = (request.get_json(silent=True) or {}).get('status', 'verified')
    if status not in ('verified', 'rejected'):
        return jsonify({'error': 'Status verifikasi tidak valid'}), 400
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT type_name FROM production_records WHERE id = %s', (record_id,))
    record = cursor.fetchone()
    if record is None:
        cursor.close()
        connection.close()
        return jsonify({'error': 'Data produksi tidak ditemukan'}), 404
    record_type = 'fish' if is_fish_type(record[0]) else 'agriculture'
    if record_type != allowed_production_type(current_user()['role']):
        cursor.close()
        connection.close()
        return jsonify({'error': 'Admin hanya dapat memverifikasi jenis produksi sesuai bidangnya'}), 403
    cursor.execute(
        'UPDATE production_records SET status = %s, verified_by = %s WHERE id = %s',
        (status, current_user()['id'], record_id),
    )
    connection.commit()
    updated = cursor.rowcount
    cursor.close()
    connection.close()
    if not updated:
        return jsonify({'error': 'Data produksi tidak ditemukan'}), 404
    return jsonify({'message': f'Data berhasil {status}'}), 200


@app.route('/api/production/<int:record_id>', methods=['DELETE'])
@roles_required('admin_pertanian', 'admin_perikanan')
def delete_production(record_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT type_name FROM production_records WHERE id = %s', (record_id,))
    record = cursor.fetchone()
    if record is None:
        cursor.close()
        connection.close()
        return jsonify({'error': 'Data produksi tidak ditemukan'}), 404
    record_type = 'fish' if is_fish_type(record[0]) else 'agriculture'
    if record_type != allowed_production_type(current_user()['role']):
        cursor.close()
        connection.close()
        return jsonify({'error': 'Admin hanya dapat menghapus data sesuai bidangnya'}), 403
    cursor.execute('DELETE FROM production_records WHERE id = %s', (record_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return jsonify({'message': 'Data produksi berhasil dihapus'})


@app.route('/api/commodity-data', methods=['GET', 'POST'])
@login_required
def commodity_data():
    role = current_user()['role']
    if request.method == 'GET':
        domain = request.args.get('domain', '')
        role_domain = dataset_domain_for_role(role)
        if role_domain and domain and domain != role_domain:
            return jsonify({'error': 'Admin hanya dapat mengakses dataset sesuai bidangnya'}), 403
        domain = role_domain or domain
        tables = DATASET_TABLES.get(domain)
        if tables is None:
            return jsonify({'error': 'Domain dataset tidak valid'}), 400

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        records = []
        for table_name in tables:
            cursor.execute(f'SELECT * FROM `{table_name}` ORDER BY year DESC, commodity')
            for record in cursor.fetchall():
                record['table_name'] = table_name
                record['production_ton'] = float(record['production_ton'])
                records.append(record)
        cursor.close()
        connection.close()
        return jsonify({'domain': domain, 'records': records})

    if role not in ('admin_pertanian', 'admin_perikanan'):
        return jsonify({'error': 'Gunakan pengajuan untuk meminta perubahan data'}), 403
    data = request.get_json(silent=True) or {}
    domain = data.get('domain', '')
    table_name = data.get('table_name', '')
    if domain != dataset_domain_for_role(role) or dataset_table_config(domain, table_name) is None:
        return jsonify({'error': 'Admin hanya dapat mengelola dataset sesuai bidangnya'}), 403
    entry, error = validate_dataset_entry(data, table_name)
    if error:
        return jsonify({'error': error}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        insert_dataset_entry(cursor, table_name, entry, 'Input manual admin')
        connection.commit()
        return jsonify({'id': cursor.lastrowid, 'message': 'Data berhasil ditambahkan'}), 201
    except mysql.connector.IntegrityError:
        connection.rollback()
        return jsonify({'error': 'Data dengan kecamatan, komoditas, dan tahun tersebut sudah ada'}), 409
    finally:
        cursor.close()
        connection.close()


@app.route('/api/commodity-data/<table_name>/<int:record_id>', methods=['PATCH', 'DELETE'])
@roles_required('admin_pertanian', 'admin_perikanan')
def mutate_commodity_data(table_name, record_id):
    data = request.get_json(silent=True) or {}
    domain = data.get('domain', '')
    if (domain != dataset_domain_for_role(current_user()['role'])
            or dataset_table_config(domain, table_name) is None):
        return jsonify({'error': 'Admin hanya dapat mengelola dataset sesuai bidangnya'}), 403

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        if request.method == 'DELETE':
            cursor.execute(f'DELETE FROM `{table_name}` WHERE id = %s', (record_id,))
            if not cursor.rowcount:
                connection.rollback()
                return jsonify({'error': 'Data komoditas tidak ditemukan'}), 404
            connection.commit()
            return jsonify({'message': 'Data berhasil dihapus'})

        entry, error = validate_dataset_entry(data, table_name)
        if error:
            return jsonify({'error': error}), 400
        cursor.execute(f'SELECT id FROM `{table_name}` WHERE id = %s', (record_id,))
        if cursor.fetchone() is None:
            connection.rollback()
            return jsonify({'error': 'Data komoditas tidak ditemukan'}), 404
        update_dataset_entry(cursor, table_name, record_id, entry)
        connection.commit()
        return jsonify({'message': 'Data berhasil diperbarui'})
    except mysql.connector.IntegrityError:
        connection.rollback()
        return jsonify({'error': 'Perubahan membuat duplikat kecamatan, komoditas, dan tahun'}), 409
    finally:
        cursor.close()
        connection.close()


@app.route('/api/commodity-requests', methods=['GET', 'POST'])
@login_required
def commodity_requests():
    role = current_user()['role']
    if request.method == 'GET':
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if role in ('admin_pertanian', 'admin_perikanan'):
            domain = dataset_domain_for_role(role)
            cursor.execute('''
                SELECT requests.*, creator.full_name AS creator_name
                FROM dataset_change_requests requests
                JOIN users creator ON creator.id = requests.created_by
                WHERE requests.domain = %s AND requests.status = 'pending'
                ORDER BY requests.created_at DESC
            ''', (domain,))
        else:
            domain = request.args.get('domain')
            if domain and domain not in DATASET_TABLES:
                cursor.close()
                connection.close()
                return jsonify({'error': 'Domain dataset tidak valid'}), 400
            query = '''
                SELECT requests.*, reviewer.full_name AS reviewer_name
                FROM dataset_change_requests requests
                LEFT JOIN users reviewer ON reviewer.id = requests.reviewed_by
                WHERE requests.created_by = %s
            '''
            params = [current_user()['id']]
            if domain:
                query += ' AND requests.domain = %s'
                params.append(domain)
            query += ' ORDER BY requests.created_at DESC'
            cursor.execute(query, params)
        records = cursor.fetchall()
        for record in records:
            record['payload'] = decode_json_value(record['payload'])
            record['original_data'] = decode_json_value(record['original_data'])
        cursor.close()
        connection.close()
        return jsonify(records)

    if role != 'user':
        return jsonify({'error': 'Admin mengelola perubahan langsung dari panel dataset'}), 403
    data = request.get_json(silent=True) or {}
    domain = data.get('domain', '')
    table_name = data.get('table_name', '')
    operation = data.get('operation', '')
    if dataset_table_config(domain, table_name) is None:
        return jsonify({'error': 'Tabel tidak sesuai dengan domain dataset'}), 400
    if operation not in ('create', 'update', 'delete'):
        return jsonify({'error': 'Operasi perubahan tidak valid'}), 400

    record_id = None
    original_data = None
    payload = {}
    if operation in ('update', 'delete'):
        try:
            record_id = int(data.get('record_id'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Data target tidak valid'}), 400
        if record_id <= 0:
            return jsonify({'error': 'Data target tidak valid'}), 400
    if operation in ('create', 'update'):
        payload, error = validate_dataset_entry(data.get('data') or {}, table_name)
        if error:
            return jsonify({'error': error}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if operation in ('update', 'delete'):
            cursor.execute(
                f'SELECT * FROM `{table_name}` WHERE id = %s FOR UPDATE',
                (record_id,),
            )
            target = cursor.fetchone()
            if target is None:
                connection.rollback()
                return jsonify({'error': 'Data komoditas tidak ditemukan'}), 404
            original_data = serialize_dataset_row(target)

        cursor.execute('''
            INSERT INTO dataset_change_requests
                (domain, table_name, operation, record_id, payload, original_data, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (domain, table_name, operation, record_id, json.dumps(payload),
              json.dumps(original_data) if original_data is not None else None,
              current_user()['id']))
        request_id = cursor.lastrowid
        connection.commit()
        return jsonify({
            'id': request_id,
            'message': 'Permintaan perubahan dikirim dan menunggu verifikasi admin bidang terkait',
        }), 201
    finally:
        cursor.close()
        connection.close()


@app.route('/api/commodity-requests/<int:request_id>/review', methods=['PATCH'])
@roles_required('admin_pertanian', 'admin_perikanan')
def review_commodity_request(request_id):
    data = request.get_json(silent=True) or {}
    decision = data.get('status')
    if decision not in ('approved', 'rejected'):
        return jsonify({'error': 'Keputusan harus approved atau rejected'}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT * FROM dataset_change_requests WHERE id = %s FOR UPDATE',
            (request_id,),
        )
        change_request = cursor.fetchone()
        if change_request is None:
            connection.rollback()
            return jsonify({'error': 'Permintaan tidak ditemukan'}), 404
        if change_request['domain'] != dataset_domain_for_role(current_user()['role']):
            connection.rollback()
            return jsonify({'error': 'Admin hanya dapat memproses permintaan sesuai bidangnya'}), 403
        if change_request['status'] != 'pending':
            connection.rollback()
            return jsonify({'error': 'Permintaan ini sudah diproses'}), 409

        table_name = change_request['table_name']
        operation = change_request['operation']
        payload = decode_json_value(change_request['payload'])
        original_data = decode_json_value(change_request['original_data'])
        if decision == 'approved':
            if operation == 'create':
                insert_dataset_entry(cursor, table_name, payload, 'Permohonan user')
            else:
                cursor.execute(
                    f'SELECT * FROM `{table_name}` WHERE id = %s FOR UPDATE',
                    (change_request['record_id'],),
                )
                current_record = serialize_dataset_row(cursor.fetchone())
                if current_record is None:
                    connection.rollback()
                    return jsonify({'error': 'Data target sudah tidak tersedia'}), 409
                if not row_matches_snapshot(current_record, original_data):
                    connection.rollback()
                    return jsonify({'error': 'Data target berubah sejak permintaan dibuat'}), 409
                if operation == 'update':
                    update_dataset_entry(cursor, table_name, change_request['record_id'], payload)
                else:
                    cursor.execute(
                        f'DELETE FROM `{table_name}` WHERE id = %s',
                        (change_request['record_id'],),
                    )

        cursor.execute('''
            UPDATE dataset_change_requests
            SET status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (decision, current_user()['id'], request_id))
        connection.commit()
        return jsonify({'message': f'Permintaan berhasil {decision}'})
    except mysql.connector.IntegrityError:
        connection.rollback()
        return jsonify({'error': 'Perubahan membuat duplikat data pada dataset'}), 409
    finally:
        cursor.close()
        connection.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
