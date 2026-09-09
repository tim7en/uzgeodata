"""Descriptive relationships. No independent-month significance claims."""
import numpy as np


def regression(rows, x, y, block=None, repetitions=500):
    points = [r for r in rows if r.get(x) is not None and r.get(y) is not None
              and np.isfinite(r[x]) and np.isfinite(r[y])]
    result = {'n': len(points), 'slope': None, 'intercept': None, 'r': None, 'r2': None,
              'slope_interval': None, 'blocks': 0}
    if len(points) < 3:
        return result
    a, b = np.array([r[x] for r in points]), np.array([r[y] for r in points])
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return result
    slope, intercept = np.polyfit(a, b, 1)
    r = float(np.corrcoef(a, b)[0, 1])
    result.update(slope=float(slope), intercept=float(intercept), r=r, r2=r*r)
    if block:
        labels = sorted({str(p[block]) for p in points})
        result['blocks'] = len(labels)
        if len(labels) >= 5:
            groups = {label: [i for i, p in enumerate(points) if str(p[block]) == label] for label in labels}
            rng, slopes = np.random.default_rng(731), []
            for _ in range(repetitions):
                indices = [i for label in rng.choice(labels, len(labels), replace=True) for i in groups[label]]
                if np.ptp(a[indices]) > 0:
                    slopes.append(float(np.polyfit(a[indices], b[indices], 1)[0]))
            if slopes:
                result['slope_interval'] = np.quantile(slopes, [.025, .975]).tolist()
    return result


def monthly_anomalies(rows, fields, minimum_years=3):
    """Subtract each site's calendar-month mean; never pool stations' climates."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        groups[(r['station_id'], r['period'][5:7])].append(r)
    output = []
    for group in groups.values():
        means = {}
        for field in fields:
            values = [r[field] for r in group if r.get(field) is not None]
            means[field] = float(np.mean(values)) if len(values) >= minimum_years else None
        for row in group:
            copy = dict(row)
            for field in fields:
                value = row.get(field)
                copy[field + '_anomaly'] = value - means[field] if value is not None and means[field] is not None else None
            output.append(copy)
    return sorted(output, key=lambda r: (r['station_id'], r['period']))
