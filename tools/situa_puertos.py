#!/usr/bin/env python3
"""Sitúa un puerto sobre el trazado ya embebido de una etapa.

El libro de ruta da nombre, altitud y categoría de cada puerto, pero no en qué
kilómetro cae. Esto lo deduce: busca el punto del trazado cuya altitud más se
acerca a la del libro y que además sea un máximo local (una cima, no un punto
cualquiera de la subida).

  python3 tools/situa_puertos.py 20 "Collado del Alguacil:1884:ESP" ...
"""
import json, re, sys, pathlib

def cargar(numero):
    src = pathlib.Path('index.html').read_text()
    D = json.loads(re.search(r'const DATA = (\{.*?\});\n', src, re.S).group(1))
    st = next((s for s in D['stages'] if s['number'] == numero), None)
    if st is None:
        sys.exit(f'No existe la etapa {numero}')
    return st

def acumulado_m(coords):
    import math
    out, tot = [0.0], 0.0
    for i in range(1, len(coords)):
        a, b = coords[i-1], coords[i]
        R = 6371000.0
        p1, p2 = math.radians(a[1]), math.radians(b[1])
        dp, dl = p2 - p1, math.radians(b[0] - a[0])
        h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        tot += 2*R*math.asin(math.sqrt(h))
        out.append(tot)
    return out

def es_cima(elev, i, radio=12):
    lo, hi = max(0, i-radio), min(len(elev), i+radio+1)
    return elev[i] >= max(elev[lo:hi]) - 0.5

def situar(st, nombre, alt, cat, desde=0):
    """Busca la cima a partir de `desde`, nunca antes.

    Los puertos vienen en el orden del libro de ruta, así que cada uno tiene que
    caer después del anterior. Sin esta restricción, un puerto que se sube dos
    veces (el doble Purche de la etapa 20) hace que el emparejamiento por
    altitud devuelva el paso equivocado y los puertos salgan desordenados.
    """
    coords = st['coords']
    elev = [c[2] for c in coords]
    cum = acumulado_m(coords)
    total = cum[-1]
    cand = [i for i in range(desde, len(elev)) if es_cima(elev, i)]
    if not cand:
        cand = list(range(desde, len(elev))) or [len(elev) - 1]
    i = min(cand, key=lambda j: abs(elev[j] - alt))
    km_oficial = cum[i] / total * st['distance_km']
    return {'name': nombre, 'cat': cat, 'i': i,
            'km': round(km_oficial, 1), 'alt': round(elev[i])}

if __name__ == '__main__':
    numero = int(sys.argv[1])
    st = cargar(numero)
    puertos = []
    desde = 0
    for spec in sys.argv[2:]:
        nombre, alt, cat = spec.rsplit(':', 2)
        p = situar(st, nombre, float(alt), cat, desde)
        desde = p['i'] + 1
        d = p['alt'] - float(alt)
        aviso = '' if abs(d) <= 25 else f'   <-- OJO: {d:+.0f} m respecto al libro'
        print(f"  {p['cat']:>3}  km {p['km']:>6.1f}  {p['alt']:>5} m  {nombre}{aviso}",
              file=sys.stderr)
        puertos.append(p)
    print(json.dumps(puertos, ensure_ascii=False))
