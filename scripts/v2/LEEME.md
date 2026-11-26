# Mapa propio de eucalipto (v2)

La v1 usa la clase "Silvicultura" de MapBiomas, que mezcla eucalipto y pino y deja parte del eucalipto dentro de "Bosque (Andes)". La v2 es un mapa propio que separa **eucalipto** de **pino**, año por año de 2011 a 2024, a 30 m, y lo lleva a la misma celda MODIS de 500 m (`cell_id`) que el resto de la base.

## Por qué ya no depende del MAG ni del IGM

El plan original esperaba los polígonos "Eucalipto" del mapa 1:25 000 (IGM/SIGTIERRAS) y el registro de plantaciones del MAG para entrenar el clasificador. Esos datos tardan y desde el entorno de Claude los portales del Estado no responden. Por eso la v2 se entrena con **polígonos dibujados por fotointerpretación** en Earth Engine (paso 1). Si después llegan los datos oficiales, entran como etiquetas extra o como validación independiente (variables `IEE` y `MAG` del paso 2), sin rehacer nada.

## Pasos

| Paso | Quién | Dónde | Qué hace | Tiempo |
|---|---|---|---|---|
| 1. `01_etiquetas_eucalipto.js` | David (cuenta del proyecto en Earth Engine) | Code Editor | Dibujar polígonos de 6 clases y guardarlos como asset | 6 a 8 horas de dibujo |
| 2a. `02_clasificacion_eucalipto_v2.js` con `ETAPA = 1` | David | Code Editor | Tabla de muestras (píxeles de 2021-2023) | 1 a 3 h de cola |
| 2b. Mismo script con `ETAPA = 2` | David | Code Editor | Imprime la validación y crea 16 tareas: `euc_clase_2011` a `euc_clase_2024`, `hansen_lossyear_sierra` y `validacion_eucalipto_v2` | 1 a 2 días de cola |
| 3. Bajar la carpeta `eucalipto_v2` de Google Drive | David | Drive | Subirla completa a `incendios/base_eucalipto/v2/tif/` en los archivos del proyecto | — |
| 4. `build_eucalipto_v2.py` | Claude | Python | Variables `euc_*` por celda y año, control de calidad y comparación con la v1 | medio día |
| 5. `14_base_firelab.py` y modelos | Claude | Python | La base FIRELAB toma la v2 sola si existe `base_eucalipto/v2/panel_anual_v2.parquet` | medio día |

Antes de correr los scripts de Earth Engine hay que cambiar `users/USUARIO/...` por la carpeta de assets del proyecto.

### Opcional: polígonos del mapa 1:25 000

Si se consiguen las geodatabases por cantón (geoportal del IGM, geodescargas, o SIGTIERRAS):

```bash
python preparar_iee.py CARPETA_CON_CANTONES iee_eucalipto.zip
```

Busca "Eucalipto" y "Pino" en todos los campos de texto, une los cantones y deja un shapefile con `clase` (1 eucalipto, 2 pino). Se sube en Earth Engine (Assets > NEW > Shape files) y se pone su ruta en `IEE` del paso 2. Ojo: esos polígonos son de 2009-2011; el paso 2 descarta los píxeles con tala de Hansen desde 2013.

## Método (resumen para el artículo)

- **Imágenes:** Landsat 5, 7, 8 y 9 Collection 2 nivel 2, máscara QA_PIXEL (nubes, sombras, cirros, nieve) y saturación; TM/ETM+ armonizados a OLI con los coeficientes de Roy et al. (2016).
- **Compuesto anual:** ventana de 3 años centrada en el año (huecos rellenados con 5 años), por la nubosidad de la Sierra. Por eso un cambio se "ve" con hasta un año de suavizado.
- **Predictores:** medianas de azul, verde, rojo, NIR, SWIR1 y SWIR2; NDVI, NBR y NDMI; percentiles 10 y 90 de NDVI y NDMI (fenología); elevación y pendiente (Copernicus DEM 30 m).
- **Clases:** 1 eucalipto, 2 pino, 3 bosque nativo, 4 páramo/arbustal/herbazal, 5 pasto/cultivo, 6 otros (urbano, suelo, agua).
- **Entrenamiento:** píxeles de los polígonos en los compuestos de 2021, 2022 y 2023, un solo Random Forest (300 árboles) para todos los años. En eucalipto y pino solo entran píxeles sin pérdida de Hansen desde 2013.
- **Validación:** 20 % de los bloques de 0,1° fuera del entrenamiento; matriz de confusión, exactitud global, del productor y del usuario. Meta: exactitud del usuario y del productor de eucalipto ≥ 80 %. Si no se alcanza, se dibuja una segunda ronda de polígonos donde el mapa falla.
- **Malla de salida:** la de Hansen (0,00025°), recortada a la Sierra (Ecuador > 800 m).

## Variables de `panel_anual_v2.parquet`

| Variable | Descripción | Unidad |
|---|---|---|
| `euc_pct`, `euc_ha` | Eucalipto en la celda | %, ha |
| `pino_pct` | Pino en la celda (control) | % |
| `plant_pct_v2` | Eucalipto + pino (comparable con `plant_pct` de la v1) | % |
| `forest_nat_pct`, `nonforest_nat_pct`, `native_pct` | Bosque nativo, páramo/arbustal, suma de ambos | % |
| `agri_pct`, `otros_pct` | Pasto/cultivo; urbano, suelo y agua | % |
| `edge_euc_native_m_km2`, `edge_euc_agri_m_km2` | Borde eucalipto-vegetación nativa y eucalipto-agro | m/km² |
| `dist_euc_m` | Distancia del centro de la celda al eucalipto más cercano (a ~83 m) | m |
| `euc_pct_vec3km` | % de eucalipto en la ventana de 7 × 7 celdas (~3,2 km) | % |
| `euc_loss_ha`, `yrs_since_euc_loss` | Pérdida Hansen dentro del eucalipto del año anterior (cosecha, tala o incendio) y años desde la última | ha, años |
| `frac_valida` | Fracción de la celda con dato (se descartan las celdas con < 20 %) | 0-1 |

Las columnas usan los mismos nombres que espera `config.py` (bloque "v2") y `14_base_firelab.py`.

## Prueba

`build_eucalipto_v2.py` se probó con rásteres sintéticos (dos años, un año partido en dos archivos, una tala simulada): los porcentajes suman 100 %, las celdas coinciden con `celdas_estatico.parquet` y la pérdida de eucalipto por tala (738 ha) cuadra con la caída del área de eucalipto entre años (744 ha). Los scripts de Earth Engine pasaron la revisión de sintaxis, pero solo se pueden probar de verdad corriéndolos en Earth Engine.
