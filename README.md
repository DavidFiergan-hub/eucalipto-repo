# Base de datos de eucalipto / plantación forestal por celda (v1, octubre 2026)

## Qué es

Una base **por celda y año** lista para unir con las cicatrices de MODIS MCD64A1.

- **Celdas:** las mismas de MCD64A1 (grilla sinusoidal MODIS de 463 m, "500 m"). Cada celda trae `modis_h`, `modis_v`, `modis_line` y `modis_sample`, así que se une directo con el píxel de MCD64A1 sin reproyectar.
- **Cobertura:** todo el Ecuador continental, con 1 165 885 celdas, de las cuales 423 566 están en la Sierra. Galápagos queda fuera.
- **Periodo:** 2001-2024, anual (27,98 millones de filas).

## Advertencia principal: v1 usa plantación forestal, no eucalipto puro

Desde este entorno no hubo acceso a los portales del Estado (IGM/SIGTIERRAS, MAATE, MAG). Por eso la v1 usa la clase **"Silvicultura" de MapBiomas Ecuador Colección 3** (30 m) como **proxy de plantación forestal (eucalipto + pino)**.

- Para la Sierra da unas 57 000 ha en 2024. Las cifras oficiales de plantaciones son de 171 000 a 259 000 ha a nivel nacional, así que **subestima**: MapBiomas mete parte del eucalipto en "Bosque (Andes)" y no detecta las hileras ni las cortinas angostas.
- Por eso las columnas se llaman `plant_*` y no `euc_*`. Cuando tengamos el mapa real de eucalipto (polígonos "Eucalipto" del mapa IEE/MAGAP 1:25 000 o la clasificación Sentinel-2 de `scripts/gee_clasificacion_eucalipto.js`), se vuelve a correr `scripts/build_eucalipto.py` cambiando la máscara de plantación. Así salen `euc_pct`, `euc_dist`, etc. con exactamente la misma estructura.
- La variable `arbol_mosaico_pct2000` (cobertura arbórea de Hansen dentro del mosaico agropecuario) sirve como proxy del eucalipto disperso en linderos, que es muy común en el valle interandino.

## Archivos

| Archivo | Contenido |
|---|---|
| `data/celdas_estatico.parquet` | Una fila por celda: id, índices MODIS, lon/lat del centro, elevación, región y arbolado en mosaicos |
| `data/panel_anual/panel_AAAA.parquet` (un archivo por año) | Una fila por celda y año, con las variables de plantación, cobertura, bordes, distancia y cosecha |
| `data/sierra_2024.csv.gz` | Extracto del año 2024 para la Sierra (estático + anual) para abrir en Excel, R o QGIS |
| `data/diccionario_variables.xlsx` | Diccionario, resumen por región y año, y fuentes |
| `data/mapa_control_2024.png` | Mapa de control: % de plantación y distancia a la plantación más cercana |
| `scripts/build_eucalipto.py` | Script reproducible (Python: rasterio, numpy, scipy, pandas) |
| `scripts/gee_clasificacion_eucalipto.js` | Clasificación de eucalipto con Sentinel-2/1 en Google Earth Engine para la v2 |

Para unir las tablas: `cell_id` (= fila_global × 86400 + columna_global de la grilla MODIS 500 m). En Python: `pd.read_parquet(...)`; en R: `arrow::read_parquet(...)`.

## Variables

### Estáticas (`data/celdas_estatico.parquet`)

| Variable | Descripción | Unidad | Fuente |
|---|---|---|---|
| `cell_id` | Identificador único de la celda MODIS 500 m | — | Grilla MCD64A1 |
| `modis_h`, `modis_v` | Tile MODIS (Ecuador: h09-h10, v08-v09) | — | Grilla MCD64A1 |
| `modis_line`, `modis_sample` | Fila y columna dentro del tile (0-2399) | — | Grilla MCD64A1 |
| `lon`, `lat` | Centro de la celda (WGS84) | grados | — |
| `elev_m` | Elevación en el centro | m | Copernicus DEM GLO-90 |
| `region` | Sierra (centro ≥ 1000 m), Costa (< 1000 m al oeste de la cordillera), Amazonia (< 1000 m al este) | — | Derivada del DEM |
| `arbol_mosaico_pct2000` | Cobertura arbórea media dentro de los píxeles de mosaico agropecuario; proxy de árboles dispersos y linderos | % | Hansen treecover2000 + MapBiomas 2001 |
| `area_valida_km2` | Área de la celda con dato válido de MapBiomas | km² | MapBiomas |

### Anuales (`data/panel_anual/panel_AAAA.parquet` (un archivo por año))

| Variable | Descripción | Unidad |
|---|---|---|
| `year` | Año | — |
| `plant_pct` | Porcentaje de la celda con plantación forestal (Silvicultura) | % |
| `plant_ha` | Superficie de plantación en la celda | ha |
| `native_pct` | Vegetación nativa (bosque + formaciones naturales no boscosas) | % |
| `forest_nat_pct` | Bosque natural (bosque, bosque abierto, manglar, inundable) | % |
| `nonforest_nat_pct` | Páramo, herbazal, arbustal andino y humedales | % |
| `agri_pct` | Mosaico agropecuario y banano | % |
| `urban_pct` | Infraestructura urbana | % |
| `edge_plant_native_m_km2` | Densidad de borde plantación–vegetación nativa (lados compartidos entre píxeles de 30 m) | m/km² |
| `edge_plant_agri_m_km2` | Densidad de borde plantación–agropecuario | m/km² |
| `dist_plant_m` | Distancia del centro de la celda a la plantación más cercana (0 si la celda tiene plantación). Calculada a ~90 m | m |
| `plant_pct_vec3km` | % de plantación en una ventana de 7 × 7 celdas (~3,2 km) | % |
| `plant_loss_ha` | Pérdida de dosel (Hansen) en el año, dentro de lo que era plantación el año anterior; equivale a cosecha, tala o incendio | ha |
| `yrs_since_plant_loss` | Años desde la última pérdida > 0,09 ha en la plantación de la celda; vacío si no hubo pérdida desde 2001 | años |

## Cómo se calculó (resumen)

1. Se reclasificó MapBiomas Col. 3 de cada año en plantación (9), bosque natural (3, 4, 5, 6), formación natural no boscosa (11, 12, 13, 81, 82), agropecuario (21, 74) y urbano (24). "No observado" (27) se tomó como sin dato.
2. Cada píxel de 30 m se asignó a la celda MODIS que contiene su centro, y se calcularon los porcentajes sobre los píxeles válidos.
3. Bordes: se sumaron los lados compartidos entre un píxel de plantación y uno nativo (o agropecuario) en 4-vecindad, por la longitud del lado.
4. Distancia: transformada de distancia euclidiana sobre la máscara de plantación reducida a ~90 m.
5. Cosecha: pixeles de `lossyear` de Hansen v1.12 iguales al año, dentro de la plantación del año anterior. Ojo: en 2001 se usa el mapa de 2001.

Control de calidad: el área válida suma 248 700 km² (Ecuador continental ≈ 248 000 km²). La plantación en la Sierra es de 52 800 ha en 2001 y 56 900 ha en 2024, consistente con las estadísticas de MapBiomas por provincia (Azuay, Cotopaxi, Pichincha, Loja y Cañar a la cabeza).

## Próximos pasos para la v2 (eucalipto real)

1. Conseguir los polígonos "Eucalipto" del mapa 1:25 000 (IGM/SIGTIERRAS, por cantón) y el registro de plantaciones del MAG. Ver `docs/fuentes_base_datos_eucalipto.docx`.
2. Correr `gee_clasificacion_eucalipto.js` para tener eucalipto a 10 m (2017-2024) y, con Landsat, hacia atrás.
3. Volver a correr `build_eucalipto.py` con esa máscara para generar `euc_pct`, `euc_dist`, `euc_edge_native`, etc., y dejar `plant_*` como control (pino + eucalipto).

## Cargar el panel completo

```python
import pandas as pd, glob
panel = pd.concat(pd.read_parquet(f) for f in sorted(glob.glob("data/panel_anual/panel_*.parquet")))
celdas = pd.read_parquet("data/celdas_estatico.parquet")
base = panel.merge(celdas, on="cell_id")
```

```r
library(arrow); library(dplyr)
panel <- open_dataset("data/panel_anual") |> collect()
celdas <- read_parquet("data/celdas_estatico.parquet")
base <- left_join(panel, celdas, by = "cell_id")
```
