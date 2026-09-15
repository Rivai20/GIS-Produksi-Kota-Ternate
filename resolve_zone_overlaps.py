import json

import mysql.connector
from shapely.geometry import Polygon
from shapely.ops import unary_union

connection = mysql.connector.connect(
    host='127.0.0.1', port=3306, user='root', password='', database='gis_ternate'
)
cursor = connection.cursor(dictionary=True)
cursor.execute('SELECT name, coords FROM districts')
rows = {row['name']: json.loads(row['coords']) for row in cursor.fetchall()}

# Keep public polygons for the three mapped mainland districts.
def make_polygon(coords):
    return Polygon([(longitude, latitude) for latitude, longitude in coords]).buffer(0)

public_zones = {
    name: make_polygon(rows[name])
    for name in ('Ternate Utara', 'Ternate Tengah', 'Ternate Selatan')
}
occupied = unary_union(list(public_zones.values()))

# Barat remains the local five-district scope, clipped to the public zones.
barat = make_polygon(rows['Ternate Barat']).difference(occupied).buffer(0)

# GADM's Pulau Ternate ring overlaps other districts, so use the public center
# and a north-island outline, then clip it to all existing zones.
pulau_outline = make_polygon([
    [0.892, 127.325], [0.889, 127.350], [0.874, 127.372],
    [0.850, 127.381], [0.838, 127.360], [0.842, 127.330],
    [0.858, 127.315],
])
pulau = pulau_outline.difference(occupied.union(barat)).buffer(0)

final_zones = {
    'Ternate Utara': public_zones['Ternate Utara'],
    'Ternate Tengah': public_zones['Ternate Tengah'],
    'Ternate Selatan': public_zones['Ternate Selatan'].difference(public_zones['Ternate Tengah']).buffer(0),
    'Ternate Barat': barat,
    'Pulau Ternate': pulau,
}

for name, shape in final_zones.items():
    if shape.is_empty:
        raise RuntimeError(f'Zona kosong setelah pemotongan: {name}')
    if shape.geom_type == 'MultiPolygon':
        shape = max(shape.geoms, key=lambda item: item.area)
    coords = [[latitude, longitude] for longitude, latitude in shape.exterior.coords]
    cursor.execute(
        'UPDATE districts SET coords = %s WHERE name = %s',
        (json.dumps(coords, separators=(',', ':')), name),
    )

connection.commit()
print('Zona dipotong agar tidak saling bertumpuk:', ', '.join(final_zones))
cursor.close()
connection.close()
