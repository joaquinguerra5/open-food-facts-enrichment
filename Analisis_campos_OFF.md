# Análisis de campos de Open Food Facts — ¿qué conviene conservar?

> Basado en la documentación de OFF + la data real de esta prueba (501 GTIN, **262 encontrados**).
> Todos los porcentajes de llenado son **sobre los 262 productos encontrados**, no sobre los 501.

---

## 1. Resumen ejecutivo

La corrida trajo **1333 columnas** de OFF. La conclusión es clara: **la gran mayoría no vale la pena en el CSV de trabajo**.

- **132** columnas están 100% vacías.
- **537** se llenan en <5% de los productos.
- Las columnas que SÍ están siempre llenas (100%) son casi todas **metadata interna de OFF** (quién editó, revisiones, timestamps, flags de calidad), no información del producto.
- La info realmente útil (nutrientes, ingredientes, marca) vive en el rango **40–70% de llenado**.
- Cada concepto viene **repetido 3 a 6 veces** (versión legible + `_tags` + `_hierarchy` + `_lc` + variantes de idioma).

**Recomendación:** conservar el **JSON crudo completo** (ya lo hacemos, en `off_raw/`, sin pérdida) y trabajar sobre un **CSV curado de ~32 columnas**. Pasar de 1333 a ~32 no pierde nada importante y vuelve el archivo usable.

### Sobre el "costo de traerlos"

Hay que separar dos costos:

| Tipo de costo | ¿Cambia si traigo menos campos? |
|---|---|
| **Red / requests / rate-limit** | ❌ **No.** El endpoint devuelve el producto entero en 1 request. Filtrar campos no ahorra requests ni evita el límite de 100/min. |
| **Tamaño de descarga + parseo** | 🟡 Un poco. Se puede pedir `?fields=campo1,campo2,...` para bajar payloads más chicos y parsear más rápido. |
| **Usabilidad del CSV** | ✅ **Mucho.** 1333 columnas son inmanejables en Excel/Sheets/pandas; 32 son cómodas. |
| **Ruido / redundancia / interpretación** | ✅ **Mucho.** Menos columnas = menos "¿qué es esto?" y menos campos basura. |

En criollo: **traer todo no cuesta más plata ni más tiempo de API** (ya bajamos el JSON entero igual). El costo de "traer todo" es **de usabilidad**: un CSV gigante y ruidoso. Por eso la jugada es guardar el crudo completo y curar el CSV.

---

## 2. La trampa del llenado: "lleno" no es "útil"

Cuatro campos clave vienen casi siempre "llenos", pero su valor real es `unknown`:

| Campo | % con algún valor | % con valor **útil** | Detalle |
|---|---|---|---|
| `nutriscore_grade` | 98% | **43%** | 123 de 262 dicen `unknown` |
| `ecoscore_grade` | 98% | **34%** | 155 `unknown` + 13 `not-applicable` |
| `nova_group` | 47% | **47%** | acá sí, lleno = útil (valores 1/3/4) |
| `pnns_groups_1` | 98% | **52%** | 122 `unknown` |

**Lección:** al decidir, no mirar solo si la columna trae algo, sino **qué** trae. Igual conviene conservar Nutri-Score / NOVA / Eco-Score: cuando traen un valor real, son oro; solo hay que saber que para productos argentinos faltan seguido.

---

## 3. Veredicto por familia de campos

| Familia | # cols | Llenas >50% | Veredicto | Por qué |
|---|---|---|---|---|
| **nutriments.*** | 403 | 50 | 🟡 **Traer ~13** | Solo ~13 nutrientes `_100g` tienen datos. Las otras ~390 son variantes `_value`/`_unit`/`_serving`/`_prepared` y nutrientes exóticos casi vacíos. |
| **otros (escalares)** | 436 | 35 | 🟡 **Curar** | Mezcla todo: acá están los buenos (product_name, brands, categories…) y mucha metadata. |
| **ingredients*** | 142 | 16 | 🟡 **Traer 3-4** | Vale `ingredients_text`, `ingredients_n`, `allergens`. El resto son variantes de idioma y arrays explotados. |
| **tags/clasif** (`_tags`,`_hierarchy`,`_lc`) | 127 | 41 | ❌ **Descartar** | Versiones máquina redundantes de campos que ya traemos legibles. |
| **variantes de idioma** | 115 | 4 | ❌ **Descartar** | `product_name_fr/de/it/...` casi siempre vacías. Alcanza con la principal (es/en). |
| **scores (nutri/nova/eco)** | 41 | 9 | 🟡 **Traer 3** | `nutriscore_grade`, `nova_group`, `ecoscore_grade`. El resto (`_tags`, `nutrition_score_*`) es ruido. |
| **metadata/edición** | 26 | 20 | ❌ **Descartar** | `creator`, `editors_tags`, `rev`, `*_t`, `states`, `completeness`, `data_quality_*`… housekeeping interno de OFF. |
| **packaging*** | 23 | 0 | ❌ **Descartar** | Prácticamente sin datos para estos productos. |
| **imágenes** | 15 | 12 | 🟡 **Traer 2-4** | `image_front_url` (94%) muy útil; ingredientes/nutrición según necesidad. |
| **nutrient_levels.*** | 5 | 0 | 🟡 **Opcional** | Semáforo bajo/moderado/alto de grasa/azúcar/sal. Lindo pero parcial. |

---

## 4. ✅ Campos recomendados (keep-list de ~32)

### 4.1 Identificación y trazabilidad (de nuestro script — costo cero)
| Campo | Para qué |
|---|---|
| `EAN` | Clave: el GTIN original de tu archivo (con ceros) |
| `matched_code` | Con qué código matcheó en OFF |
| `estado` | encontrado / no_encontrado / error |
| `source_db` | food / beauty / product |
| `off_url` | Link directo a la ficha en OFF |

### 4.2 Comercial / descriptivo
| Campo | % llenado | Ejemplo |
|---|---|---|
| `product_name` | 95.8% | Papas Tradicional |
| `brands` | 83.6% | McCain |
| `quantity` | 67.6% | 700g |
| `product_quantity` | 63.7% | 700 *(numérico, para calcular)* |
| `serving_size` | 55.7% | 1 unit (8 g) |
| `categories` | 66.4% | Frutas recubiertas de chocolate… |
| `countries` | 99.6% | Argentina |

### 4.3 Salud / clasificación
| Campo | % útil | Ejemplo | Nota |
|---|---|---|---|
| `nutriscore_grade` | 43% | e / d / c | seguido `unknown` |
| `nova_group` | 47% | 4 | grado de procesamiento |
| `ecoscore_grade` | 34% | b / a | seguido `unknown` |

### 4.4 Ingredientes y alérgenos
| Campo | % llenado | Ejemplo |
|---|---|---|
| `ingredients_text` | 53.4% | Frambuesas congeladas, chocolate amargo… |
| `ingredients_n` | 53.4% | 17 |
| `allergens` | 37.8% | leche, soja |
| `additives_n` | 53.1% | 1 |
| `additives_tags` | 32.4% | en:e322 |

### 4.5 Tabla nutricional (por 100 g) — solo estos ~10
`nutriments.energy-kcal_100g` (68.7%) · `fat_100g` (67.6%) · `saturated-fat_100g` (62.6%) · `carbohydrates_100g` (66.0%) · `sugars_100g` (63.0%) · `fiber_100g` (50.4%) · `proteins_100g` (67.6%) · `salt_100g` (61.5%) · `sodium_100g` (61.5%) · `added-sugars_100g` (50.0%)

### 4.6 Imágenes
| Campo | % llenado |
|---|---|
| `image_front_url` | 94.3% |
| `image_url` | 94.3% |

---

## 5. 🟡 Según el caso (traer solo si los vas a usar)

| Campo | % llenado | Cuándo sirve |
|---|---|---|
| `labels` | 38.9% | "Sin TACC", "Kosher", "Vegano"… filtros dietéticos |
| `traces` | 13.7% | Alérgenos por contaminación cruzada |
| `origins` | 28.6% | País de origen del producto |
| `manufacturing_places` | 26.0% | Dónde se fabrica |
| `stores` | 27.1% | En qué cadenas se vio |
| `image_ingredients_url` / `image_nutrition_url` | 55% / 63% | Si necesitás la foto de la etiqueta |
| `nutrient_levels.*` | parcial | Semáforo bajo/moderado/alto |
| `nutriments.energy-kj_100g` | 54.6% | kJ además de kcal |

---

## 6. ❌ A descartar del CSV (queda todo en el JSON crudo igual)

- **Metadata/edición (~26 cols):** `creator`, `editors_tags`, `informers_tags`, `correctors_tags`, `checkers_tags`, `rev`, `created_t`, `last_modified_t`, `last_updated_t`, `entry_dates_tags`, `last_edit_dates_tags`, `states*`, `complete`, `completeness`, `data_quality_*_tags`, `misc_tags`, `schema_version`, `popularity_key`, `interface_version_*`, `_id`, `id`, `lang`, `lc`, `languages_*`. → *Es cómo OFF gestiona el dato, no el dato.*
- **Variantes de idioma (~115 cols):** `product_name_fr`, `_de`, `_it`, `generic_name_xx`, `ingredients_text_xx`… → *Casi todas vacías; alcanza la principal.*
- **Versiones máquina redundantes (~127 cols):** `categories_tags`, `categories_hierarchy`, `categories_lc`, `categories_properties_tags`, `labels_tags`, `brands_tags`, `countries_tags/hierarchy/lc`… → *Repiten en formato máquina lo que ya tenés legible.*
- **Ruido de nutriments (~390 cols):** todo lo que termina en `_value`, `_unit`, `_serving`, `_prepared`, y nutrientes exóticos (<5% de llenado). → *Te quedás solo con los `_100g` del punto 4.5.*
- **Scores redundantes:** `nutrition_grades_tags`, `nova_groups_tags`, `ecoscore_tags`, `nutrition_score_*`, `pnns_groups_*_tags`.
- **packaging\* (~23 cols)** y **las 132 columnas 100% vacías.**

---

## 7. Campos para atributos dietéticos y claims de salud

> Pregunta clave: **¿hay campos estructurados para Sin TACC, Vegano, Kosher, Alto en proteínas?**
> Respuesta corta: **sí para certificaciones y vegano/vegetariano; no para "alto en proteínas"** (hay que derivarlo).

### 7.1 `labels_tags` — el mejor para certificaciones declaradas

**Completamente estructurado.** Lista de tags normalizados, parseables con un split `|`. Representa lo que el fabricante *declara* en el envase y OFF cargó.

| Certificación | Tag en OFF | Frecuencia en los 262 |
|---|---|---|
| Sin TACC / sin gluten | `en:no-gluten` | 28 |
| Kosher | `en:kosher` | 23 |
| Vegetariano | `en:vegetarian` | 22 |
| Vegano | `en:vegan` | 15 |
| Kosher OU | `en:orthodox-union-kosher` | 13 |
| Sin GMO | `en:no-gmos` | 13 |
| Halal | `en:halal` | 12 |
| Sin lactosa | `en:no-lactose` | 5 |

El campo `labels` (sin `_tags`) es la misma info en texto libre legible ("Kosher, Sin TACC") — útil para mostrar, inútil para filtrar. **Usar `labels_tags` para lógica, `labels` para mostrar.**

Llenado: **38.9%**. Los productos sin certificaciones declaradas simplemente no tienen el campo.

### 7.2 `ingredients_analysis_tags` — vegano/vegetariano inferido de ingredientes

**Estructurado.** OFF analiza el texto de ingredientes automáticamente e infiere el estado, aunque el fabricante no haya puesto sello. Cubre casos que `labels_tags` no alcanza.

| Tag | Significado | Frec. |
|---|---|---|
| `en:vegan` | Todos los ingredientes son veganos | 27 |
| `en:non-vegan` | Tiene al menos 1 ingrediente no vegano | 51 |
| `en:vegan-status-unknown` | No pudo determinar | 53 |
| `en:vegetarian` | Vegetariano confirmado | 38 |
| `en:maybe-vegetarian` | Posiblemente vegetariano | 13 |
| `en:non-vegetarian` | No es vegetariano | 9 |
| `en:palm-oil-free` | Sin aceite de palma | 81 |
| `en:palm-oil` | Contiene aceite de palma | 12 |

**Diferencia clave con `labels_tags`:** este lo *deduce OFF* del texto de ingredientes, no de un sello declarado. Conviene usar **ambos**: `labels_tags` para lo certificado, `ingredients_analysis_tags` para lo inferido.

Llenado: **53.4%** (llena cuando hay texto de ingredientes cargado).

### 7.3 `allergens_tags` y `traces_tags` — alérgenos estructurados

Versión normalizada de `allergens` y `traces`. Tags del tipo `en:milk`, `en:gluten`, `en:soybeans`, `en:nuts`, `en:peanuts`. Permiten filtrar sin ambigüedad de texto libre ni diferencias de idioma.

| Campo | % llenado | Ejemplo |
|---|---|---|
| `allergens_tags` | 37.8% | `en:milk\|en:soybeans` |
| `traces_tags` | 13.7% | `en:nuts\|en:peanuts` |

`traces_tags` es contaminación cruzada — relevante para personas con alergia severa, no solo intolerancia.

### 7.4 `nutrient_levels.*` — semáforo bajo/moderado/alto

**Estructurado.** Exactamente 3 valores posibles: `low`, `moderate`, `high`. OFF los calcula según umbrales propios (basados en la regulación europea por 100g).

| Campo | % llenado | Distribución en la muestra |
|---|---|---|
| `nutrient_levels.fat` | 48.5% | low 53 · moderate 46 · high 28 |
| `nutrient_levels.saturated-fat` | 45.0% | low 55 · high 39 · moderate 24 |
| `nutrient_levels.sugars` | 45.0% | low 62 · high 37 · moderate 19 |
| `nutrient_levels.salt` | 45.4% | low 62 · moderate 38 · high 19 |

**Nota:** OFF no calcula `nutrient_levels.proteins` ni `nutrient_levels.fiber`. Para esos hay que derivar (ver 7.5).

### 7.5 Columnas derivadas — "Alto en proteínas" y similares

OFF no trae estos claims calculados. Se generan a partir de `nutriments.*_100g` aplicando los umbrales del Reglamento UE 1924/2006 (referencia habitual):

| Flag derivada | Campo base | Umbral |
|---|---|---|
| `flag_alto_proteinas` | `nutriments.proteins_100g` | ≥ 20 g/100g |
| `flag_fuente_proteinas` | `nutriments.proteins_100g` | ≥ 10 g/100g |
| `flag_alto_fibra` | `nutriments.fiber_100g` | ≥ 6 g/100g |
| `flag_fuente_fibra` | `nutriments.fiber_100g` | ≥ 3 g/100g |
| `flag_bajo_azucar` | `nutriments.sugars_100g` | ≤ 5 g/100g |
| `flag_sin_azucar` | `nutriments.sugars_100g` | ≤ 0.5 g/100g |
| `flag_bajo_sodio` | `nutriments.salt_100g` | ≤ 0.12 g/100g |
| `flag_bajo_grasa` | `nutriments.fat_100g` | ≤ 3 g/100g |

Alcance: solo los productos con `nutriments.*` cargado (~60-68% del total encontrado).

### 7.6 Resumen: qué agregar a la keep-list por este motivo

```
labels_tags                    → certificaciones estructuradas (Sin TACC, Vegano, Kosher, Halal…)
labels                         → versión legible para mostrar
ingredients_analysis_tags      → vegano/vegetariano/palma inferido automáticamente por OFF
allergens_tags                 → alérgenos normalizados (en:milk, en:gluten…)
traces_tags                    → contaminación cruzada normalizada
nutrient_levels.fat            → semáforo grasa        (low / moderate / high)
nutrient_levels.saturated-fat  → semáforo grasas sat.  (low / moderate / high)
nutrient_levels.sugars         → semáforo azúcar       (low / moderate / high)
nutrient_levels.salt           → semáforo sal          (low / moderate / high)
```

Y calcular en el script estas columnas derivadas (no requieren requests extra):
```
flag_alto_proteinas   flag_fuente_proteinas
flag_alto_fibra       flag_fuente_fibra
flag_bajo_azucar      flag_sin_azucar
flag_bajo_sodio       flag_bajo_grasa
```

---

## 8. Recomendación final

1. **Conservar `off_raw/` (JSON crudo completo).** Es lossless, no cuesta nada y te cubre si mañana necesitás un campo raro.
2. **Generar un CSV curado de ~32 columnas** (puntos 4.x) como archivo de trabajo. → *Puedo armarlo ahora mismo.*
3. **Si en el futuro se prioriza velocidad/peso de descarga,** el script puede pedir `?fields=...` con la keep-list y bajar payloads más chicos (no cambia el nº de requests ni el rate-limit, pero parsea más rápido).
4. **Tener presente la "trampa del llenado":** Nutri-Score / Eco-Score vienen seguido `unknown` para productos argentinos. No es un bug; es la cobertura de OFF.
