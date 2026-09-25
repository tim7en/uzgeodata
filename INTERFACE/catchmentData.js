import { decodeMatrix } from './catchmentStatisticsModel.js';

const matrices = new Map();
export async function json(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok || !response.headers.get('content-type')?.includes('json')) throw Error('Catchment statistics are not available.');
  return response.json();
}
export async function matrix(index, name, signal) {
  const entry = index.series[name];
  if (matrices.has(entry.url)) return matrices.get(entry.url);
  if (typeof DecompressionStream === 'undefined') throw Error('This browser cannot read compressed statistics. Use a current browser.');
  const response = await fetch(entry.url, { signal });
  if (!response.ok) throw Error('Monthly catchment data could not load.');
  const compressed = await response.arrayBuffer();
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', compressed))].map(b => b.toString(16).padStart(2, '0')).join('');
  if (hash !== entry.sha256) throw Error('Monthly catchment data failed its integrity check. Retry after refreshing.');
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const values = decodeMatrix(new Uint8Array(await new Response(stream).arrayBuffer()), index);
  if (matrices.size >= 2) matrices.delete(matrices.keys().next().value);
  matrices.set(entry.url, values);
  return values;
}
