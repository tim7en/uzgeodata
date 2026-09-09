import React, { useState } from 'react';
import { ArrowUpRight, Download, ArrowRight } from 'lucide-react';
const BASE = '/data/case-studies/';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (x, digits = 1) => x == null ? '—' : Number(x).toLocaleString('en', { maximumFractionDigits: digits });
export default function Chart({ rows, fields, unit, title }) {
  const [hover, setHover] = useState(null);
  const width = 760, height = 260, left = 58, right = 22, top = 22, bottom = 42;
  const values = rows.flatMap(r => fields.map(f => r[f.key])).filter(v => v != null && Number.isFinite(v));
  if (!values.length) return <p>No eligible values for this selection.</p>;
  const min = Math.min(0, ...values), max = Math.max(...values, min + 0.01) * 1.08;
  const x = i => left + i / Math.max(1, rows.length - 1) * (width - left - right);
  const y = v => top + (max - v) / (max - min) * (height - top - bottom);
  const segments = key => {
    let path = '', active = false;
    rows.forEach((r, i) => {
      if (r[key] == null) { active = false; return; }
      path += `${active ? 'L' : 'M'}${x(i)},${y(r[key])} `;
      active = true;
    });
    return path;
  };
  const ticks = [...new Set([0, Math.floor((rows.length - 1) / 4), Math.floor((rows.length - 1) / 2), Math.floor((rows.length - 1) * 3 / 4), rows.length - 1])];
  const selected = hover == null ? null : rows[hover];
  return <figure className="cs-chart">
    <figcaption>{title} <span>{unit}</span></figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}, ${unit}. Exact values are available in the data table below.`}
      onMouseLeave={() => setHover(null)} onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const px = (event.clientX - box.left) / box.width * width;
        setHover(Math.max(0, Math.min(rows.length - 1, Math.round((px - left) / (width - left - right) * (rows.length - 1)))));
      }}>
      {[0, 1, 2, 3, 4].map(i => {
        const value = min + (max - min) * i / 4;
        return <g key={i}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="cs-grid" />
          <text x={left - 10} y={y(value) + 4} textAnchor="end">{fmt(value, max - min < 3 ? 2 : 0)}</text></g>;
      })}
      {ticks.map(i => <text key={i} x={x(i)} y={height - 13} textAnchor="middle">{rows[i].label || rows[i].period}</text>)}
      {fields.map(field => <path key={field.key} d={segments(field.key)} fill="none" stroke={field.color} strokeWidth="2.4" strokeDasharray={field.dashed ? '6 4' : undefined} />)}
      {fields.flatMap(field => rows.map((r,i)=>r[field.key]!=null && (rows.length<36 || (rows[i-1]?.[field.key]==null && rows[i+1]?.[field.key]==null)) ? <circle key={`${field.key}-${i}`} cx={x(i)} cy={y(r[field.key])} r="2.8" fill={field.color}/> : null))}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={top} y2={height - bottom} className="cs-cursor" />}
    </svg>
    <div className="cs-legend">{fields.map(f => <span key={f.key}><i style={{ background: f.color }} />{f.label}</span>)}</div>
    <div className="cs-readout">{selected ? <>{selected.label || selected.period} · {fields.map(f => `${f.label}: ${fmt(selected[f.key], 2)} ${unit}`).join(' · ')}</> : 'Move across the chart to inspect values. Gaps remain visible.'}</div>
    <details><summary>View exact chart data</summary><div className="cs-table-wrap"><table><thead><tr><th>Period</th>{fields.map(f => <th key={f.key}>{f.label} ({unit})</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}><td>{r.label || r.period}</td>{fields.map(f => <td key={f.key}>{fmt(r[f.key], 3)}</td>)}</tr>)}</tbody></table></div></details>
  </figure>;
}
