#!/usr/bin/env python3
"""Convierte un GPX oficial de etapa al objeto que embebe index.html (DATA.stages).

Uso:
  python3 tools/gpx2stage.py ruta.gpx --number 1 --date 2026-08-22 \
      --start "Mónaco" --finish "Mónaco" --type ITT [--distance-km 9.4]

El GPX oficial trae ~10.000 puntos por etapa; el visor trabaja con 400-1200
(Douglas-Peucker), que es la densidad de los datos del Tour y mantiene el
trazado indistinguible a cualquier zoom razonable.
"""
import argparse, json, math, sys
import xml.etree.ElementTree as ET

GPX_NS = ('http://www.topografix.com/GPX/1/0', 'http://www.topografix.com/GPX/1/1')


def read_gpx(path):
    root = ET.parse(path).getroot()
    pts = []
    for ns in GPX_NS:
        for p in root.iter(f'{{{ns}}}trkpt'):
            ele = p.find(f'{{{ns}}}ele')
            pts.append((float(p.get('lon')), float(p.get('lat')),
                        float(ele.text) if ele is not None else 0.0))
        if pts:
            break
    if not pts:
        sys.exit(f'{path}: no se encontró ningún <trkpt>. ¿Es un GPX de verdad?')
    return pts


def haversine(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = p2 - p1, math.radians(b[0] - a[0])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def total_km(pts):
    return sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) / 1000.0


def elevation_gain(pts, threshold=8.0):
    """Desnivel positivo acumulado. El umbral descarta el ruido del barómetro/SRTM,
    que si no infla la cifra muy por encima de la oficial."""
    gain, ref = 0.0, pts[0][2]
    for _, _, e in pts[1:]:
        if e > ref + threshold:
            gain += e - ref
            ref = e
        elif e < ref:
            ref = e
    return gain


def perp_distance(p, a, b):
    """Distancia perpendicular de p al segmento a-b, en grados escalados a metros."""
    kx = math.cos(math.radians(a[1])) * 111320.0
    ky = 110540.0
    px, py = (p[0] - a[0]) * kx, (p[1] - a[1]) * ky
    bx, by = (b[0] - a[0]) * kx, (b[1] - a[1]) * ky
    seg = bx * bx + by * by
    if seg == 0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / seg))
    return math.hypot(px - t * bx, py - t * by)


def douglas_peucker(pts, tol):
    """Iterativo, no recursivo: 10.000 puntos desbordan la pila en la versión recursiva."""
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        worst_d, worst_i = -1.0, -1
        for i in range(lo + 1, hi):
            d = perp_distance(pts[i], pts[lo], pts[hi])
            if d > worst_d:
                worst_d, worst_i = d, i
        if worst_d > tol:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [p for p, k in zip(pts, keep) if k]


def simplify_to_target(pts, target):
    """Busca por bisección la tolerancia que deja ~target puntos."""
    if len(pts) <= target:
        return pts, 0.0
    lo, hi = 0.1, 500.0
    best = pts
    for _ in range(40):
        mid = (lo + hi) / 2
        out = douglas_peucker(pts, mid)
        if len(out) > target:
            lo = mid
        else:
            best, hi = out, mid
        if abs(len(out) - target) <= target * 0.02:
            return out, mid
    return best, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('gpx')
    ap.add_argument('--number', type=int, required=True)
    ap.add_argument('--date', required=True, help='ISO, ej 2026-08-22')
    ap.add_argument('--start', required=True)
    ap.add_argument('--finish', required=True)
    ap.add_argument('--type', required=True,
                    choices=['ITT', 'TTT', 'flat', 'hilly', 'mountain'])
    ap.add_argument('--distance-km', type=float, default=None,
                    help='Distancia OFICIAL. Si se omite se usa la medida sobre el GPX.')
    ap.add_argument('--elevation-m', type=int, default=None,
                    help='Desnivel OFICIAL. Si se omite se calcula desde el GPX.')
    ap.add_argument('--target-points', type=int, default=1000)
    a = ap.parse_args()

    raw = read_gpx(a.gpx)
    gpx_km = total_km(raw)
    gain = elevation_gain(raw)
    simple, tol = simplify_to_target(raw, a.target_points)
    err = abs(total_km(simple) - gpx_km) / gpx_km * 100

    print(f'{a.gpx}', file=sys.stderr)
    print(f'  puntos      {len(raw)} -> {len(simple)}  (tolerancia {tol:.1f} m)',
          file=sys.stderr)
    print(f'  longitud    {gpx_km:.1f} km  (tras simplificar: '
          f'{total_km(simple):.1f} km, desvío {err:.2f} %)', file=sys.stderr)
    print(f'  desnivel+   {gain:.0f} m', file=sys.stderr)

    stage = {
        'number': a.number,
        'date': a.date,
        'start': a.start,
        'finish': a.finish,
        'type': a.type,
        'title': f'{a.start} → {a.finish}',
        'distance_km': a.distance_km if a.distance_km is not None else round(gpx_km, 1),
        'gpx_km': round(gpx_km, 1),
        'elevation_gain_m': a.elevation_m if a.elevation_m is not None else int(round(gain)),
        'coords': [[round(x, 5), round(y, 5), round(e, 1)] for x, y, e in simple],
        'gpx_note': False,
        'markers': [
            {'lng': round(simple[0][0], 5), 'lat': round(simple[0][1], 5),
             'cls': 'blue', 'label': 'Km 0', 'sub': a.start},
            {'lng': round(simple[-1][0], 5), 'lat': round(simple[-1][1], 5),
             'cls': 'red', 'label': 'Meta', 'sub': a.finish},
        ],
        'official_climbs': [],
    }
    print(json.dumps(stage, ensure_ascii=False))


if __name__ == '__main__':
    main()
