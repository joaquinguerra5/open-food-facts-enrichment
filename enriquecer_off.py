#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enriquecer_off.py
-----------------
Enriquece una lista de EAN/GTIN (export de GS1 Argentina) con datos de
Open Food Facts y sus bases hermanas (Open Beauty / Pet Food / Products Facts).

Flujo:
  1. Lee 'Muestra GS1 - data.csv' (la fila 1 es basura; los encabezados reales
     estan en la fila 2).
  2. Por cada fila consulta la API de OFF y vuelca TODO lo que devuelva.
  3. Escribe un CSV nuevo con clave EAN + columnas de OFF. Se conservan las 500
     filas; cada una lleva estado = encontrado / no_encontrado / error.
  4. Guarda el JSON crudo completo de cada producto encontrado en off_raw/.

Caracteristicas:
  - Solo libreria estandar de Python (no requiere 'pip install').
  - Reanudable y con cache: si se corre de nuevo no repite consultas.
  - Respeta a OFF: User-Agent identificatorio, ritmo limitado y reintentos.

Uso:
  python enriquecer_off.py                 # corrida completa
  python enriquecer_off.py --limit 8       # prueba con las primeras 8 filas
  python enriquecer_off.py --refresh       # ignora la cache y vuelve a consultar
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ----------------------------- Configuracion -----------------------------
INPUT_FILE    = "Muestra GS1 - data.csv"
OUTPUT_CSV    = "off_enriquecido.csv"
RAW_DIR       = "off_raw"
PROGRESS_FILE = os.path.join(RAW_DIR, "_progress.json")
SUMMARY_FILE  = "off_resumen.txt"

# OFF pide un User-Agent identificatorio con un contacto.
USER_AGENT       = "OFF-GS1-Enricher/1.0 (joacoguerrae@gmail.com)"
REQUESTS_PER_MIN = 100      # ritmo amable hacia OFF (~1.67 req/seg)
# Verificado: con USE_UNIFIED el endpoint product_type=all ya devuelve productos
# de TODAS las bases (food/beauty/petfood/products), asi que el loop de hermanas
# es redundante. Se deja en False por velocidad; poner True solo como respaldo.
QUERY_SIBLINGS   = False    # consultar Beauty / Pet Food / Products Facts aparte
USE_UNIFIED      = True     # product_type=all -> 1 request cubre todas las bases
MAX_RETRIES      = 4
TIMEOUT          = 30

# Columnas del archivo de entrada que contienen el codigo de barras.
COL_EAN  = "ean"     # 14 digitos con ceros a la izquierda (ej. 07797906054826)
COL_GTIN = "GTIN"    # EAN-13 / UPC-12 (ej. 7797906054826)

# Bloques enormes o ruidosos que NO van al CSV (quedan completos en el JSON crudo).
DROP_KEYS = {
    "knowledge_panels", "images", "selected_images", "ecoscore_data",
    "ecoscore_extended_data", "nutriscore", "_keywords", "attribute_groups",
    "source", "sources", "sources_fields", "languages_codes",
    "ingredients_hierarchy", "ingredients_original_tags", "weighers_tags",
}

OFF_HOST = "https://world.openfoodfacts.org"
SIBLING_HOSTS = [
    ("beauty",   "https://world.openbeautyfacts.org"),
    ("petfood",  "https://world.openpetfoodfacts.org"),
    ("products", "https://world.openproductsfacts.org"),
]
HOST_BY_SRC = {
    "food":     "https://world.openfoodfacts.org",
    "beauty":   "https://world.openbeautyfacts.org",
    "petfood":  "https://world.openpetfoodfacts.org",
    "products": "https://world.openproductsfacts.org",
    "product":  "https://world.openproductsfacts.org",
}

# Orden preferido de las primeras columnas de OFF en el CSV (las que existan).
PREFERRED = [
    "code", "product_name", "product_name_es", "generic_name", "brands",
    "quantity", "categories", "categories_tags", "labels", "countries",
    "nutriscore_grade", "nova_group", "ecoscore_grade",
    "ingredients_text", "ingredients_text_es", "allergens", "traces",
    "additives_tags", "image_url", "image_front_url", "last_modified_t",
]

# --------------------------- HTTP con reintentos ---------------------------
_last_req = [0.0]
_min_interval = 60.0 / REQUESTS_PER_MIN


def _throttle():
    dt = time.time() - _last_req[0]
    if dt < _min_interval:
        time.sleep(_min_interval - dt)
    _last_req[0] = time.time()


def fetch_json(url):
    """GET con reintentos. Devuelve (kind, data) con kind en ok/notfound/error."""
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return "ok", json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "notfound", None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            return "error", None
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                json.JSONDecodeError):
            time.sleep(2 ** attempt)
            continue
    return "error", None


# ------------------------------- Lookup OFF -------------------------------
def lookup_off(code):
    """Consulta OFF (unificado si USE_UNIFIED). Devuelve (status, product, src)."""
    url = "%s/api/v2/product/%s.json" % (OFF_HOST, code)
    if USE_UNIFIED:
        url += "?product_type=all"
    kind, data = fetch_json(url)
    if kind == "ok" and data.get("status") == 1 and data.get("product"):
        prod = data["product"]
        return "found", prod, (prod.get("product_type") or "food")
    if kind == "error":
        return "error", None, None
    return "notfound", None, None


def lookup_sibling(code, host):
    """Consulta una base hermana. Devuelve (status, product)."""
    url = "%s/api/v2/product/%s.json" % (host, code)
    kind, data = fetch_json(url)
    if kind == "ok" and data.get("status") == 1 and data.get("product"):
        return "found", data["product"]
    if kind == "error":
        return "error", None
    return "notfound", None


def lookup_product(candidates):
    """Prueba los codigos candidatos en OFF y, si no aparece, en las hermanas.
    Devuelve (product|None, source_db, matched_code, status)."""
    saw_error = False

    # Etapa 1: OFF (unificado cubre todas las bases si el parametro es honrado).
    for code in candidates:
        status, prod, src = lookup_off(code)
        if status == "found":
            return prod, src, code, "encontrado"
        if status == "error":
            saw_error = True

    # Etapa 2: bases hermanas con el codigo primario (respaldo por si el
    # unificado no devolviera los no-alimentos).
    if QUERY_SIBLINGS and candidates:
        primary = candidates[0]
        for name, host in SIBLING_HOSTS:
            status, prod = lookup_sibling(primary, host)
            if status == "found":
                return prod, name, primary, "encontrado"
            if status == "error":
                saw_error = True

    return None, None, None, ("error" if saw_error else "no_encontrado")


# ----------------------------- Normalizacion -----------------------------
def only_digits(s):
    return "".join(c for c in (s or "") if c.isdigit())


def build_candidates(ean_raw, gtin_raw):
    """Lista ordenada y sin repetidos de codigos a probar contra OFF."""
    cands = []

    def add(v):
        if v and v not in cands:
            cands.append(v)

    g = only_digits(gtin_raw)
    e = only_digits(ean_raw)
    add(g)                       # GTIN tal cual (EAN-13 o UPC-12)
    add(e.lstrip("0"))           # EAN sin ceros a la izquierda
    base = (e or g).lstrip("0")  # normalizado a EAN-13
    if base:
        add(base.zfill(13))
    add(e)                       # EAN tal cual (14 digitos)
    return cands[:4]


# ------------------------------ Aplanado JSON ------------------------------
def _is_scalar(x):
    return x is None or isinstance(x, (str, int, float, bool))


def flatten(obj, prefix=""):
    """Aplana un JSON anidado. dict -> a.b.c ; lista de escalares -> 'x|y|z' ;
    lista de objetos -> texto JSON (no se pierde nada)."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, prefix + str(k) + "."))
    elif isinstance(obj, list):
        key = prefix[:-1]
        if all(_is_scalar(x) for x in obj):
            out[key] = "|".join("" if x is None else str(x) for x in obj)
        else:
            out[key] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix[:-1] if prefix else "value"] = obj
    return out


def product_to_row(prod):
    pruned = {k: v for k, v in prod.items() if k not in DROP_KEYS}
    flat = flatten(pruned)
    # Normaliza None/bools a texto plano para el CSV.
    clean = {}
    for k, v in flat.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, bool):
            clean[k] = "true" if v else "false"
        else:
            clean[k] = v
    return clean


# ------------------------------ Entrada CSV ------------------------------
def read_input(path):
    """Lee el CSV de entrada.

    Soporta dos variantes:
    - Formato GS1/PeYa: fila 1 es basura ('PeYa,...'), header real en fila 2.
    - Formato simple:   header en fila 1 directamente.

    La columna GTIN es opcional: si no existe se trabaja solo con 'ean'.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise SystemExit("El archivo de entrada no tiene datos suficientes.")

    # Autodeteccion: si la fila 1 NO contiene la columna EAN, es la fila basura.
    first_row_idx = {name.strip(): i for i, name in enumerate(rows[0])}
    if COL_EAN in first_row_idx:
        header_row = 0          # header en fila 1 → formato simple
    else:
        header_row = 1          # header en fila 2 → formato GS1 con fila basura
        if len(rows) < 3:
            raise SystemExit("El archivo parece tener fila basura pero no hay datos.")

    header = [c.strip() for c in rows[header_row]]
    idx = {name: i for i, name in enumerate(header)}

    if COL_EAN not in idx:
        raise SystemExit("No encuentro la columna '%s' en el header: %s"
                         % (COL_EAN, header))

    i_ean  = idx[COL_EAN]
    i_gtin = idx.get(COL_GTIN, -1)   # GTIN es opcional
    i_tit  = idx.get("titulo", -1)

    records = []
    for r in rows[header_row + 1:]:
        if not any(c.strip() for c in r):
            continue  # fila vacia
        ean   = r[i_ean].strip()  if i_ean  < len(r) else ""
        gtin  = r[i_gtin].strip() if 0 <= i_gtin < len(r) else ""
        titulo = r[i_tit].strip() if 0 <= i_tit  < len(r) else ""
        records.append({"ean": ean, "gtin": gtin, "titulo": titulo})
    return records


# ------------------------------- Progreso -------------------------------
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_progress(progress):
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)


def raw_path(ean):
    safe = only_digits(ean) or "sin_codigo"
    return os.path.join(RAW_DIR, safe + ".json")


# --------------------------------- Main ---------------------------------
def main():
    # En Windows la consola suele ser cp1252 y algunos titulos traen caracteres
    # que no soporta (ej. el simbolo numero). Forzamos UTF-8 tolerante para que
    # un print de progreso nunca tire abajo la corrida.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Enriquecer EAN con Open Food Facts")
    ap.add_argument("--input", default=INPUT_FILE)
    ap.add_argument("--output", default=OUTPUT_CSV)
    ap.add_argument("--limit", type=int, default=0,
                    help="procesar solo las primeras N filas (0 = todas)")
    ap.add_argument("--refresh", action="store_true",
                    help="ignorar cache/progreso y volver a consultar")
    args = ap.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    records = read_input(args.input)
    if args.limit > 0:
        records = records[:args.limit]
    total = len(records)
    print("Filas a procesar: %d" % total)

    progress = {} if args.refresh else load_progress()
    results = []          # filas finales (metadata + datos OFF aplanados)
    off_keys = set()      # union de columnas OFF
    counts = {"encontrado": 0, "no_encontrado": 0, "error": 0}
    by_source = {}
    not_found_list = []
    t0 = time.time()

    for n, rec in enumerate(records, 1):
        ean = rec["ean"]
        cached = progress.get(ean) if not args.refresh else None

        if cached and cached.get("estado") != "error":
            estado = cached["estado"]
            matched = cached.get("matched_code", "")
            src = cached.get("source_db", "")
            data = {}
            if estado == "encontrado" and os.path.exists(raw_path(ean)):
                try:
                    with open(raw_path(ean), encoding="utf-8") as f:
                        data = product_to_row(json.load(f))
                except (OSError, json.JSONDecodeError):
                    data = {}
            tag = "cache"
        else:
            cands = build_candidates(ean, rec["gtin"])
            prod, src, matched, estado = lookup_product(cands)
            src = src or ""
            matched = matched or ""
            data = {}
            if estado == "encontrado" and prod is not None:
                try:
                    with open(raw_path(ean), "w", encoding="utf-8") as f:
                        json.dump(prod, f, ensure_ascii=False)
                except OSError:
                    pass
                data = product_to_row(prod)
            progress[ean] = {"estado": estado, "matched_code": matched,
                             "source_db": src}
            tag = "api"
            if n % 10 == 0:
                save_progress(progress)

        counts[estado] = counts.get(estado, 0) + 1
        if estado == "encontrado":
            by_source[src] = by_source.get(src, 0) + 1
            off_keys.update(data.keys())
            off_url = "%s/product/%s" % (HOST_BY_SRC.get(src, OFF_HOST), matched)
        else:
            off_url = ""
            if estado == "no_encontrado":
                not_found_list.append(ean)

        results.append({"EAN": ean, "matched_code": matched, "estado": estado,
                        "source_db": src, "off_url": off_url, "_data": data})

        marca = (" %.40s" % rec["titulo"]) if rec["titulo"] else ""
        print("[%4d/%4d] %-14s %-13s %-8s%s" %
              (n, total, ean, estado, tag, marca))

    save_progress(progress)

    # ----- Orden de columnas: metadata + preferidas + resto alfabetico -----
    meta_cols = ["EAN", "matched_code", "estado", "source_db", "off_url"]
    ordered = [c for c in PREFERRED if c in off_keys]
    rest = sorted(off_keys - set(ordered))
    off_cols = ordered + rest
    header = meta_cols + off_cols

    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for row in results:
            out = {k: row[k] for k in meta_cols}
            out.update(row["_data"])
            w.writerow(out)

    elapsed = time.time() - t0
    lines = [
        "Resumen enriquecimiento Open Food Facts",
        "=" * 42,
        "Archivo entrada : %s" % args.input,
        "Archivo salida  : %s" % args.output,
        "Filas totales   : %d" % total,
        "Encontrados     : %d" % counts.get("encontrado", 0),
        "No encontrados  : %d" % counts.get("no_encontrado", 0),
        "Errores         : %d" % counts.get("error", 0),
        "Columnas OFF    : %d" % len(off_cols),
        "Tiempo          : %.1f s" % elapsed,
        "",
        "Encontrados por base:",
    ]
    for src, c in sorted(by_source.items(), key=lambda kv: -kv[1]):
        lines.append("  %-10s %d" % (src, c))
    lines.append("")
    lines.append("No encontrados (EAN):")
    lines.extend("  " + e for e in not_found_list)
    summary = "\n".join(lines)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(summary + "\n")

    print("\n" + summary)
    print("\nListo. CSV: %s  |  JSON crudo: %s/  |  Resumen: %s"
          % (args.output, RAW_DIR, SUMMARY_FILE))


if __name__ == "__main__":
    main()
