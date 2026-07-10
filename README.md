# OFF_api — Enriquecimiento de GTIN/EAN con Open Food Facts

Script principal: **`enriquecer_off.py`**. Toma una lista de códigos GTIN/EAN desde un CSV y consulta la API pública de [Open Food Facts](https://world.openfoodfacts.org/) (y sus bases hermanas Open Beauty / Pet Food / Products Facts, en una sola llamada unificada) para traer **toda la información disponible** de cada producto: nombre, marca, categorías, Nutri-Score, NOVA, Eco-Score, ingredientes, alérgenos, aditivos, tabla nutricional, imágenes, etc.

## Requisitos

- **Python 3.x** (probado con 3.13). Solo librería estándar — **no requiere `pip install`**.
- Conexión a internet. No requiere API key (OFF es pública; el script manda un `User-Agent` identificatorio, exigido por OFF).

## Uso

```bash
# Corrida completa (usa el input por defecto: "Muestra GS1 - data.csv")
python enriquecer_off.py

# Con otro archivo de entrada y salida
python enriquecer_off.py --input input_off.csv --output off_enriquecido_1000.csv

# Prueba con las primeras N filas
python enriquecer_off.py --limit 8

# Ignorar el caché y volver a consultar todo
python enriquecer_off.py --refresh
```

| Flag | Descripción | Default |
|---|---|---|
| `--input` | CSV de entrada | `Muestra GS1 - data.csv` |
| `--output` | CSV de salida | `off_enriquecido.csv` |
| `--limit N` | Procesar solo las primeras N filas (0 = todas) | `0` |
| `--refresh` | Ignorar caché/progreso y re-consultar la API | off |

## Formato del archivo de entrada

El script **autodetecta** dos variantes:

1. **Formato simple** — header en la fila 1, con una columna `ean`:
   ```csv
   ean,titulo,...
   00041333001005,Pilas Alcalinas Duracell AA Blister 2 Unidades,...
   ```
2. **Formato GS1/PeYa** — fila 1 basura (`PeYa,,,...`), header real en la fila 2, columnas `ean` y `GTIN`.

Notas:
- La columna **`ean` es obligatoria**; `GTIN` y `titulo` son opcionales (si existen, se usan para mejorar el matcheo y el log).
- Los códigos pueden venir con ceros a la izquierda (GTIN-14): el script prueba varias variantes normalizadas (tal cual, sin ceros, completado a EAN-13) hasta encontrar match.

## Archivos de salida

| Archivo | Contenido |
|---|---|
| `off_enriquecido.csv` | Una fila por EAN de entrada. Columnas: `EAN` (original, como texto), `matched_code` (variante que matcheó), `estado` (`encontrado` / `no_encontrado` / `error`), `source_db` (food / beauty / petfood / products), `off_url` + **todos los campos de OFF aplanados** (la unión de claves de todos los productos; pueden ser >1000 columnas). UTF-8 con BOM. |
| `off_raw/<ean>.json` | JSON crudo **completo** de cada producto encontrado (sin pérdida — incluye los bloques que se excluyen del CSV, como `knowledge_panels` e `images`). |
| `off_raw/_progress.json` | Caché de progreso (ver abajo). |
| `off_resumen.txt` | Estadísticas: encontrados / no encontrados, desglose por base, lista de EAN sin match. |

Los no encontrados **se conservan** en el CSV con los campos de OFF vacíos y `estado = no_encontrado`.

## Cómo funciona

- **Endpoint**: `GET https://world.openfoodfacts.org/api/v2/product/{codigo}.json?product_type=all`. El parámetro `product_type=all` hace que una sola request cubra las 4 bases (food/beauty/petfood/products) — verificado empíricamente.
- **Rate limit**: ~100 requests/min (configurable en `REQUESTS_PER_MIN`), con reintentos y backoff exponencial ante 429/5xx.
- **Caché / reanudable**: cada respuesta se guarda apenas llega y el progreso se persiste cada 10 filas. Si la corrida se corta (o la relanzás), **retoma donde quedó sin repetir consultas**. Para forzar una re-consulta usá `--refresh`.
- **Aplanado del JSON**: diccionarios anidados → `nutriments.energy-kcal_100g`; listas de escalares → `a|b|c`; listas de objetos → JSON en la celda. Los bloques enormes/ruidosos (`knowledge_panels`, `images`, `ecoscore_data`, etc., ver `DROP_KEYS`) se excluyen del CSV pero quedan en el JSON crudo.

## Configuración (constantes al inicio del script)

- `USER_AGENT` — identificación ante OFF (incluye email de contacto; actualizalo si corresponde).
- `REQUESTS_PER_MIN` — ritmo de consultas.
- `USE_UNIFIED` / `QUERY_SIBLINGS` — modo unificado (default) vs. consultar bases hermanas por separado (respaldo, más lento).
- `DROP_KEYS` — bloques del JSON que no van al CSV.

## Tips

- **Excel y ceros a la izquierda**: si abrís el CSV con doble clic, Excel puede comerse el `0` inicial del EAN. Importalo con *Datos → Desde texto/CSV* marcando la columna EAN como **Texto**.
- **Tiempo estimado**: ~1.5–2 s por producto nuevo (por el rate limit). 500 productos ≈ 10–15 min la primera vez; re-corridas desde caché tardan segundos.
- **Cobertura esperable**: OFF tiene cobertura parcial de productos argentinos (~50% en nuestras pruebas) y los no-alimentos rara vez están. Ver análisis de qué campos vale la pena usar en [`Analisis_campos_OFF.md`](Analisis_campos_OFF.md).

## Otros archivos de la carpeta

| Archivo | Qué es |
|---|---|
| `Analisis_campos_OFF.md` | Análisis de los ~1300 campos que devuelve OFF: cuáles valen la pena, tasas de llenado, campos estructurados para claims dietéticos (Sin TACC, vegano, kosher, etc.). |
