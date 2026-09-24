"""Package saved monthly values and derive catchment morphology; no acquisition.

python PIPELINES/build_catchment_statistics.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import deque
from pathlib import Path

import numpy as np
from pyproj import Geod
from shapely import union_all
from shapely.geometry import shape
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'PUBLISHED'
OUTPUT = PUBLIC / 'data/atlas/catchments'
GEOD = Geod(ellps='WGS84')
NULL = -2147483648
SCALE = 10000


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')


def leaf_order(properties):
    children = {key: [] for key in properties}
    for key, p in properties.items():
        parent = int(p['NEXT_DOWN'])
        if parent in children:
            children[parent].append(key)
    remaining = {key: len(value) for key, value in children.items()}
    queue = deque(key for key, count in remaining.items() if count == 0)
    order = []
    while queue:
        key = queue.popleft()
        order.append(key)
        parent = int(properties[key]['NEXT_DOWN'])
        if parent in remaining:
            remaining[parent] -= 1
            if remaining[parent] == 0:
                queue.append(parent)
    if len(order) != len(properties):
        raise ValueError('Drainage network contains a cycle')
    return order, children


def geometric_measures(geometry):
    """Dissolved boundary; never sum the perimeters of adjacent sub-basins."""
    polygons = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    area, perimeter = 0.0, 0.0
    for polygon in polygons:
        polygon = orient(polygon, sign=1.0)
        polygon_area, _ = GEOD.geometry_area_perimeter(polygon)
        area += abs(polygon_area) / 1e6
        # External boundaries of every connected component, excluding hole rims.
        perimeter += GEOD.geometry_length(polygon.exterior) / 1000
    hull = list(geometry.convex_hull.exterior.coords)[:-1]
    span = 0.0
    for position, (lon, lat) in enumerate(hull):
        others = hull[position + 1:]
        if others:
            _, _, distances = GEOD.inv([lon] * len(others), [lat] * len(others),
                                      [point[0] for point in others], [point[1] for point in others])
            span = max(span, max(distances) / 1000)
    return {'geometry_area_km2': area, 'outer_perimeter_km': perimeter,
            'boundary_span_km': span,
            'circularity': 4 * math.pi * area / perimeter ** 2 if perimeter else None,
            'elongation_ratio': 2 * math.sqrt(area / math.pi) / span if span else None}


def encode_matrix(values):
    """Quantize to 0.0001 units, delta within each basin, byte-shuffle, gzip."""
    finite = np.isfinite(values)
    scaled = np.rint(np.where(finite, values, 0) * SCALE)
    if np.any((scaled[finite] <= NULL) | (scaled[finite] > 2147483647)):
        raise ValueError('Value exceeds the matrix encoding range')
    packed = np.where(finite, scaled, NULL).astype('<i4')
    packed[:, 1:] = np.diff(packed, axis=1)  # int32 modular differences, including the null sentinel
    shuffled = packed.view('u1').reshape(-1, 4).T.copy().tobytes()
    return gzip.compress(shuffled, compresslevel=9, mtime=0)


def build():
    exact_path = ROOT / 'GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson'
    geometry_path = PUBLIC / 'data/hydroclimate/reference-basins-level12.geojson'
    attribute_path = PUBLIC / 'data/hydroclimate/reference-basin-attributes.json'
    history_path = PUBLIC / 'data/atlas/history'
    index_path = history_path / 'index.json'
    exact, displayed, attributes, history_index = map(read, [exact_path, geometry_path, attribute_path, index_path])
    ids = sorted(int(f['properties']['hybas_id']) for f in displayed['features'])
    position = {key: i for i, key in enumerate(ids)}
    features = {int(f['properties']['HYBAS_ID']): f for f in exact['features']}
    if set(features) != set(ids):
        raise ValueError('Exact and displayed basin membership differ')
    properties = {key: f['properties'] for key, f in features.items()}
    for f in displayed['features']:
        p = f['properties']
        if int(p['next_down']) != int(properties[int(p['hybas_id'])]['NEXT_DOWN']):
            raise ValueError('Display and exact drainage routing differ')
    order, children = leaf_order(properties)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    previous_files = [entry['url'].split('/')[-1] for entry in read(OUTPUT / 'index.json')['series'].values()] if (OUTPUT / 'index.json').exists() else []
    matrices = {key: np.full((len(ids), history_index['months']), np.nan) for key in history_index['series']}
    provenance = {key: {} for key in matrices}
    provenance_ids = {key: [] for key in matrices}
    fingerprints = []
    for key in ids:
        path = history_path / f'{key}.json'
        fingerprints.append(f'{key}:{sha(path)}\n')
        record = read(path)
        if int(record['basin_id']) != key or record['years'] != history_index['years']:
            raise ValueError(f'History identity or dates differ: {key}')
        for name, matrix in matrices.items():
            series = record['series'][name]
            if len(series['values']) != history_index['months']:
                raise ValueError(f'History length differs: {key}/{name}')
            matrix[position[key]] = [np.nan if v is None else v for v in series['values']]
            meta = {k: v for k, v in series.items() if k not in ['values', 'observed_months', 'missing_months']}
            signature = json.dumps(meta, sort_keys=True)
            if signature not in provenance[name]:
                provenance[name][signature] = len(provenance[name])
            provenance_ids[name].append(provenance[name][signature])
    manifests = {}
    for name, matrix in matrices.items():
        data = encode_matrix(matrix)
        digest = hashlib.sha256(data).hexdigest()
        filename = f'{name}-{digest[:12]}.bin.gz'
        (OUTPUT / filename).write_bytes(data)
        manifests[name] = {'url': f'/data/atlas/catchments/{filename}', 'bytes': len(data), 'sha256': digest,
                           'meta': history_index['series'][name],
                           'provenance': [json.loads(value) for value in provenance[name]],
                           'provenance_ids': provenance_ids[name]}
        print(f'{name}: {len(data):,} bytes', flush=True)

    # Process each child once, and release its dissolved shape after its parent uses it.
    geometries, accumulated, summaries = {}, {}, {}
    attrs = {int(key): i for i, key in enumerate(attributes['ids'])}
    def value(key, name):
        result = attributes['values'][name][attrs[key]]
        return float(result) if result is not None and math.isfinite(result) and result != -9999 else None
    for step, key in enumerate(order):
        p = properties[key]
        area = float(p['SUB_AREA'])
        if not math.isfinite(area) or area <= 0:
            raise ValueError(f'Invalid basin area: {key}')
        geom = shape(features[key]['geometry'])
        if not geom.is_valid:
            raise ValueError(f'Invalid exact geometry: {key}')
        geometry = union_all([geom] + [geometries.pop(child) for child in children[key]])
        geometries[key] = geometry
        low, high, elevation, slope = [value(key, name) for name in
            ['ele_mt_smn', 'ele_mt_smx', 'ele_mt_sav', 'slp_dg_sav']]
        item = {'area': area, 'count': 1, 'low': low, 'high': high,
                'elevation_sum': (elevation or 0) * area, 'elevation_area': area if elevation is not None else 0,
                'slope_sum': (slope or 0) * area / 10, 'slope_area': area if slope is not None else 0,
                'extreme_count': int(low is not None and high is not None), 'max_dist': float(p['DIST_MAIN'])}
        for child in children[key]:
            other = accumulated.pop(child)
            for field in ['area', 'count', 'elevation_sum', 'elevation_area', 'slope_sum', 'slope_area', 'extreme_count']:
                item[field] += other[field]
            for field, operation in [('low', min), ('high', max), ('max_dist', max)]:
                candidates = [x for x in [item[field], other[field]] if x is not None]
                item[field] = operation(candidates) if candidates else None
        accumulated[key] = item
        mean = item['elevation_sum'] / item['elevation_area'] if item['elevation_area'] else None
        complete = item['extreme_count'] == item['count']
        relief = item['high'] - item['low'] if complete else None
        summaries[str(key)] = {
            **geometric_measures(geometry), 'basin_count': item['count'], 'traced_area_km2': item['area'],
            'reported_upstream_area_km2': float(p['UP_AREA']),
            'lowest_elevation_m': item['low'] if complete else None,
            'highest_elevation_m': item['high'] if complete else None,
            'relief_m': relief, 'mean_elevation_m': mean,
            'mean_slope_deg': item['slope_sum'] / item['slope_area'] if item['slope_area'] else None,
            'elevation_area_coverage': item['elevation_area'] / item['area'],
            'slope_area_coverage': item['slope_area'] / item['area'],
            'elevation_extreme_basin_coverage': item['extreme_count'] / item['count'],
            'hypsometric_integral': (mean - item['low']) / relief if relief and item['elevation_area'] >= item['area'] * (1 - 1e-9) else None,
            'upstream_outlet_path_km': max(0, item['max_dist'] - float(p['DIST_MAIN'])),
        }
        if step % 1000 == 0:
            print(f'Morphology {step + 1}/{len(order)}', flush=True)
    write(OUTPUT / 'morphology.json', {
        'method': 'catchment_morphology_v1', 'source_geometry_sha256': sha(exact_path),
        'source_attributes_sha256': sha(attribute_path), 'basins': summaries,
        'notes': [
            'Selected level-12 sub-basin plus all NEXT_DOWN-connected upstream sub-basins, including virtual links.',
            'WGS84 geodesic area and external perimeter of dissolved unsimplified HydroBASINS polygons; hole rims excluded.',
            'Boundary span is maximum geodesic distance between vertices of the longitude/latitude convex hull; an approximate basin length, not river length.',
            'Upstream outlet path is max(DIST_MAIN) minus outlet DIST_MAIN; excludes distance above the furthest sub-basin outlet and virtual-link distances.',
            'Elevation extrema use HydroATLAS ele_mt_smn/smx. They are DEM-derived elevations, not surveyed points or point coordinates.',
            'Mean elevation and slope use SUB_AREA weighting; slope scale is divided by 10. Relief=max-min elevation.',
            'Circularity=4*pi*geometry_area/outer_perimeter^2; elongation=2*sqrt(geometry_area/pi)/boundary_span.',
            'Hypsometric integral=(area-weighted mean elevation-min)/(max-min), a summary approximation.',
        ],
    })
    write(OUTPUT / 'index.json', {
        'version': 1, 'ids': ids, 'areas_km2': [float(properties[key]['SUB_AREA']) for key in ids],
        'next_down': [int(properties[key]['NEXT_DOWN']) for key in ids],
        'months': history_index['months'], 'years': history_index['years'],
        'scale': SCALE, 'null_sentinel': NULL, 'encoding': 'gzip-byte-shuffled-delta-int32-le-basin-major',
        'max_quantization_error': 0.5 / SCALE, 'series': manifests,
        'history_sha256': hashlib.sha256(''.join(fingerprints).encode()).hexdigest(),
        'history_index_sha256': sha(index_path), 'display_geometry_sha256': sha(geometry_path),
        'attribute_sha256': sha(attribute_path),
        'morphology_url': '/data/atlas/catchments/morphology.json',
    })
    current_files = {entry['url'].split('/')[-1] for entry in manifests.values()}
    for filename in previous_files:
        old = OUTPUT / filename
        if filename not in current_files and old.resolve().parent == OUTPUT.resolve():
            old.unlink(missing_ok=True)
    print('Catchment statistics package complete.', flush=True)


if __name__ == '__main__':
    build()
