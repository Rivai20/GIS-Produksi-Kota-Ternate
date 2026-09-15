import json
import os
import tempfile
import zipfile

import mysql.connector
import shapefile

ARCHIVE = 'Kota Ternate_Maluku Utara_50K_LapakGIS.zip'
DISTRICT_NAMES = {
    'Kota Ternate Selatan': 'Ternate Selatan',
    'Kota Ternate Tengah': 'Ternate Tengah',
    'Kota Ternate Utara': 'Ternate Utara',
    'Pulau Ternate': 'Pulau Ternate',
}


def largest_part(shape):
    starts = list(shape.parts) + [len(shape.points)]
    return max(
        (shape.points[starts[index]:starts[index + 1]] for index in range(len(starts) - 1)),
        key=len,
    )


with zipfile.ZipFile(ARCHIVE) as archive:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        archive.extractall(folder)
        reader = shapefile.Reader(os.path.join(folder, 'ADMINISTRASI_AR_50K.shp'), encoding='utf-8')
        boundaries = {}
        for record, district_shape in zip(reader.iterRecords(), reader.iterShapes()):
            name = record[0]
            city = record[17]
            if city == 'Kota Ternate' and name in DISTRICT_NAMES:
                boundaries[DISTRICT_NAMES[name]] = [
                    [latitude, longitude]
                    for longitude, latitude in largest_part(district_shape)
                ]

connection = mysql.connector.connect(
    host='127.0.0.1', port=3306, user='root', password='', database='gis_ternate'
)
cursor = connection.cursor()
cursor.execute(
    "DELETE FROM districts WHERE name IN ('Ternate Barat', 'Moti', 'Pulau Hiri', 'Pulau Batang Dua')"
)
for name, coords in boundaries.items():
    cursor.execute('SELECT id FROM districts WHERE name = %s', (name,))
    if cursor.fetchone():
        cursor.execute('UPDATE districts SET coords = %s WHERE name = %s', (json.dumps(coords), name))
    else:
        cursor.execute(
            'INSERT INTO districts '
            '(name, value, cluster, coords, production_ikan, production_pertanian, '
            'production_total, commodity, type_name) VALUES (%s, 0, 1, %s, 0, 0, 0, %s, %s)',
            (name, json.dumps(coords), 'Belum ada data', 'Belum ada data'),
        )
connection.commit()
cursor.close()
connection.close()
print('Batas SHP dipasang:', ', '.join(boundaries))
print('Zona di luar cakupan utama dihapus dari aplikasi.')
