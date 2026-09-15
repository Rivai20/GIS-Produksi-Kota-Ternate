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
            "CASE WHEN type_name IN ('fish', 'Hasil Tangkapan Ikan') THEN 'fish' ELSE 'leaf' END AS type_name, "
            "CASE WHEN type_name IN ('fish', 'Hasil Tangkapan Ikan') THEN '🐟' ELSE '🌿' END AS emoji, "
            'latitude, longitude FROM production_records WHERE status = %s',
            ('verified',),
        )
        markers.extend(cursor.fetchall())

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

        return jsonify({'districts': districts, 'markers': markers})
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
    cursor.execute('DELETE FROM production_records WHERE id = %s', (record_id,))
    connection.commit()
    deleted = cursor.rowcount
    cursor.close()
    connection.close()
    if not deleted:
        return jsonify({'error': 'Data produksi tidak ditemukan'}), 404
    return jsonify({'message': 'Data produksi berhasil dihapus'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
