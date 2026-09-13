export const MAP_VIEW_KEY = 'uzgeodata.mapView';
export const DEFAULT_MAP_VIEW = { center: [40.2, 70.5], zoom: 6 };

export function readMapView(storage) {
  try {
    const view = JSON.parse(storage.getItem(MAP_VIEW_KEY));
    if (Array.isArray(view?.center) && view.center.length === 2
      && view.center.every(Number.isFinite) && Math.abs(view.center[0]) <= 85
      && Math.abs(view.center[1]) <= 180 && Number.isFinite(view.zoom)
      && view.zoom >= 0 && view.zoom <= 19) return view;
  } catch { /* Blocked storage and old or malformed entries use the default. */ }
  return DEFAULT_MAP_VIEW;
}

export function saveMapView(storage, center, zoom) {
  try { storage.setItem(MAP_VIEW_KEY, JSON.stringify({ center, zoom })); } catch { /* Optional persistence. */ }
}

export function collectionBounds(features) {
  let south = Infinity, north = -Infinity, west = Infinity, east = -Infinity;
  for (const { geometry } of features) {
    const rings = geometry?.type === 'Polygon' ? geometry.coordinates
      : geometry?.type === 'MultiPolygon' ? geometry.coordinates.flat() : [];
    for (const ring of rings) for (const [lng, lat] of ring) {
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      south = Math.min(south, lat); north = Math.max(north, lat);
      west = Math.min(west, lng); east = Math.max(east, lng);
    }
  }
  return Number.isFinite(south) ? [[south, west], [north, east]] : null;
}
