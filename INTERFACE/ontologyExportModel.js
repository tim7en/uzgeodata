const csvValue = value => {
  if (value == null) return '';
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

export function temporalSeriesCsv(meta, points) {
  const columns = [
    'entity_type', 'entity_id', 'basin_l12', 'basin_l7', 'districts', 'province',
    'dataset', 'variable', 'unit', 'period', 'source_value', 'z_score', 'classification',
  ];
  const rows = (points || []).map(point => [
    meta.entityType, meta.entityId, meta.basin12, meta.basin7, meta.districts,
    meta.province, meta.dataset, meta.variable, meta.unit, point.period,
    point.value, point.z, point.classification,
  ]);
  return `\uFEFF${[columns, ...rows].map(row => row.map(csvValue).join(',')).join('\r\n')}`;
}

export function overlayFeatureCollection(features, metadata = {}) {
  return {
    type: 'FeatureCollection',
    name: metadata.name || 'uzgeodata-ontology-overlay',
    metadata,
    features: (features || []).filter(Boolean),
  };
}

export function downloadPayload(filename, payload, mimeType) {
  const body = typeof payload === 'string' ? payload : JSON.stringify(payload);
  const url = URL.createObjectURL(new Blob([body], {type: mimeType}));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
