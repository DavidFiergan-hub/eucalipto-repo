# Base de datos del eucalipto en la Sierra del Ecuador: fuentes y construcción

Preparado para el estudio de probabilidad de incendios y efecto del eucalipto (escala nacional, celdas de 500 m o 1 km, cicatrices MODIS MCD64A1, GNN con atención). Fecha: octubre 2026.

## Resumen en cinco líneas

1. **No existe un mapa nacional, público y actualizado de eucalipto.** Hay que construirlo; las fuentes oficiales sirven como etiquetas de entrenamiento y validación, no como capa final.
2. **La mejor fuente de etiquetas es el mapa de cobertura y uso 1:25 000 del IEE/MAGAP (SIGTIERRAS, 2009-2015)**, que tiene la clase **"Eucalipto"** separada de "Pino" y "Misceláneo forestal" (verificado en la memoria técnica del cantón Mejía: 958 ha de eucalipto).
3. **Cuidado con MapBiomas Ecuador:** su clase "Silvicultura" describe sobre todo pino, y la leyenda de la Colección 3 dice que el "Bosque (Andes)" puede incluir **bosques plantados de eucalipto**. Usarlo tal cual mezclaría eucalipto con bosque nativo, justo el sesgo que queremos evitar.
4. **El mapa propio se hace con Sentinel-2 (+ Sentinel-1) en Google Earth Engine**, a 10 m, solo en la Sierra (≈ 2 000-3 500 m), y luego se agrega a la celda de 500 m o 1 km.
5. **Variables finales por celda:** % de eucalipto, distancia a la plantación más cercana, longitud de borde eucalipto-vegetación nativa, % de eucalipto en el vecindario, edad/cosecha reciente y altura del dosel.

---

## 1. Fuentes, una por una

Prioridad: **A** = imprescindible, **B** = muy útil, **C** = complementaria.

### 1.1 Mapas oficiales de cobertura y plantaciones

| Fuente | Qué aporta sobre eucalipto | Acceso | Resolución / escala | Periodo | Prioridad |
|---|---|---|---|---|---|
| **Mapa de Cobertura y Uso de la Tierra y Sistemas Productivos, IEE / MAGAP / SIGTIERRAS** | Clase **"Eucalipto"** explícita (uso: protección o producción), además de "Pino" y "Misceláneo forestal". Polígonos interpretados visualmente sobre ortofotos | Por cantón: memorias técnicas y geodatabases en [geoportaligm.gob.ec/geodescargas](https://www.geoportaligm.gob.ec/geodescargas/mejia/mt_mejia_sistemas_productivos.pdf); portal [SIGTIERRAS](http://www.sigtierras.gob.ec/cobertura-y-uso-de-la-tierra/) (geoportal, centro de descargas, metadatos) | 1:25 000, vector | Ortofotos 2005-2009 y RapidEye 2010-2011 (publicado 2013-2015) | **A** (etiquetas) |
| **Versión editada 2020 del mismo mapa (MAG)** | Compilación nacional del anterior; el BID reporta 258 658 ha de plantaciones comerciales con base en él | [Datos Abiertos Ecuador](https://datosabiertos.gob.ec/dataset/mapa-de-cobertura-y-uso-de-la-tierra-y-sistemas-productivos-agropecuarios) (la página no respondió en la prueba; pedir al MAG si falla) | 1:25 000, vector | 2009-2015, editado 2020 | **A** |
| **Mapas de Cobertura y Uso de la Tierra (CUT) del MAATE** | Clase "Plantación forestal" (nivel 2), sin especie. Serie larga para ver expansión | Geoportal / SUIA del MAATE (Mapa Interactivo Ambiental); también los cita MapBiomas como referencia | Aprox. 1:100 000 | 1990, 2000, 2008, 2014, 2016, 2018, 2020, 2022 | **A** (máscara "plantación" y serie temporal) |
| **Registro forestal y programas de aprovechamiento de plantaciones (MAG, Subsecretaría de Producción Forestal)** | Plantaciones registradas con especie, edad, superficie, coordenadas de predios y licencias de corta. 171 332 ha registradas en 2023 (BID) | Visor SPF del MAG ([spf.agricultura.gob.ec](https://spf.agricultura.gob.ec/spf/manuales/Manual-plantaciones-sep.pdf)); los datos por predio requieren **solicitud formal** (LOTAIP o convenio EPN-MAG). Base legal: AM MAATE-MAG-2023-23 ([Ecolex](https://www.ecolex.org/details/legislation/acuerdo-ministerial-no-maate-mag-2023-23-expide-el-procedimiento-para-la-gestion-del-registro-forestal-lex-faoc220609/)) | Polígonos de predio | 2012-presente | **A** (etiquetas recientes y edad) |
| **Programa de Incentivos Forestales (MAG)** | Plantaciones comerciales incentivadas, con especie y año de siembra | Solicitud al MAG | Predio | 2013-presente | B |
| **Mapa de Ecosistemas del Ecuador Continental (MAATE 2013)** | Define qué es "vegetación nativa" para el borde (páramo, bosque montano, matorral) | Geoportal MAATE | 1:100 000 | 2013 | **A** (para bordes) |

Nota práctica: la clase "Eucalipto" del mapa 1:25 000 es el insumo más valioso de todo el inventario. Conviene descargar y unir los cantones de la Sierra (Carchi a Loja) en una sola capa al inicio del proyecto.

### 1.2 Mapas derivados de satélite (abiertos)

| Fuente | Qué aporta | Acceso | Resolución | Periodo | Prioridad |
|---|---|---|---|---|---|
| **MapBiomas Ecuador, Colecciones 2 y 3** | Cobertura anual; clase 9 "Silvicultura". **El eucalipto puede estar dentro de "Bosque (Andes)"** según la [leyenda Col. 3](https://ecuador.mapbiomas.org/wp-content/uploads/sites/7/2025/10/DESCRIPCION-DE-LA-LEYENDA-COLECCION-3.pdf) | [ecuador.mapbiomas.org](https://ecuador.mapbiomas.org/en/map/coleccion-2-0/); assets públicos en GEE; [ATBD Col. 2](https://ecuador.mapbiomas.org/wp-content/uploads/sites/7/2024/11/ATBD-Ecuador-Coleccion-2.0-MapBiomas-Ecuador.pdf) | 30 m (Landsat) | 1985-2023 (anual) | **A** como cobertura base, no como eucalipto |
| **Spatial Database of Planted Trees (SDPT v2.1), WRI** | Polígonos de plantaciones casi globales, a menudo con especie; mezcla fuentes de distinta fecha | [datasets.wri.org](https://datasets.wri.org/datasets/spatial-database-of-planted-trees-sdpt-version-21) (ZIP y API) | Polígono | Varía por país (verificar fuente para Ecuador) | B |
| **Global 30 m Forest Age Map, natural vs. plantado (GFAM-N/P)** | Separa bosque plantado de natural y da edad desde la última perturbación | [doi:10.17632/yfm4sw8h25.1](https://doi.org/10.17632/yfm4sw8h25.1); [preprint ESSD](https://essd.copernicus.org/preprints/essd-2025-674/essd-2025-674-manuscript-version2.pdf) | 30 m | 1985-2024 | B (edad y covariable de clasificación) |
| **Global map of planting years of plantations** (Du et al. 2022) | Año de establecimiento de plantaciones | [figshare](https://figshare.com/articles/dataset/A_global_map_of_planting_years_of_plantations/19070084) | 30 m | 1982-2020 | C |
| **Hansen Global Forest Change** | Pérdida de cobertura arbórea por año: detecta **cosechas** (eucalipto se corta cada 8-15 años) | GEE `UMD/hansen/global_forest_change_2024_v1_12` | 30 m | 2001-2024 | B |
| **Altura del dosel: GEDI L2A/L4A, Meta-WRI 1 m, ETH 10 m** | Diferencia eucalipto (alto, 15-40 m) de matorral; ayuda a clasificar | GEE (`LARSE/GEDI/...`, `projects/meta-forest-monitoring-okw37/...`) | 25 m huellas / 1 m / 10 m | 2019-2023 | B |
| ESA WorldCover, Dynamic World | Árboles vs. pasto vs. cultivo, sin especie | GEE | 10 m | 2020-2021 / 2015-presente | C |

### 1.3 Imágenes para clasificar el eucalipto

| Sensor | Uso | Acceso | Resolución | Periodo |
|---|---|---|---|---|
| **Sentinel-2 L2A (MSI)** | Clasificación principal: bandas red-edge y SWIR separan eucalipto de pino y bosque nativo; compuestos de temporada seca | GEE `COPERNICUS/S2_SR_HARMONIZED` + Cloud Score+ | 10-20 m | 2017-presente |
| **Sentinel-1 GRD (VV, VH)** | Textura y estructura del dosel; no le afectan las nubes (crítico en la Sierra) | GEE `COPERNICUS/S1_GRD` | 10 m | 2015-presente |
| **Landsat 5/7/8/9** | Retroceder el mapa a 2001-2016 para que coincida con MCD64A1 | GEE colección 2 L2 | 30 m | 1984-presente |
| PlanetScope / mosaicos NICFI | Verificación visual de muestras y bordes | Planet (programa NICFI para trópicos; confirmar disponibilidad actual) | 3-5 m | 2015-presente |
| Ortofotos IGM / SIGTIERRAS | Fotointerpretación de puntos de entrenamiento | Geoportal IGM | 0.3-1 m | 2005-2011 (por zonas) |
| Google Earth Pro (histórico) | Verificación visual por fecha | Gratuito | Submétrica | Variable |

### 1.4 Datos de campo y ocurrencias

| Fuente | Qué aporta | Acceso | Nota |
|---|---|---|---|
| **GBIF** (*Eucalyptus*, Ecuador) | Solo **131 registros georreferenciados** (90 de una especie, casi todos *E. globulus*) | [api.gbif.org](https://api.gbif.org/v1/occurrence/search?country=EC&scientificName=Eucalyptus&hasCoordinate=true&limit=0) | Insuficiente para entrenar; sirve para validar |
| iNaturalist (se integra en GBIF) | Fotos verificables de eucalipto en ciudades y carreteras | inaturalist.org | Sesgo hacia vías y Quito |
| **Evaluación Nacional Forestal (ENF), MAATE / ONU-REDD** | Parcelas permanentes con especie, DAP y altura; incluye estratos de plantación | Solicitud al MAATE ([manual de campo](https://un-redd.org/sites/default/files/2021-10/Dia_2_Grupo_1_2_Manual_de_Campo_Ecuador.pdf)) | Coordenadas suelen ser reservadas; pedir por convenio |
| Inspecciones de cosecha del MAG | Cada licencia trae coordenadas UTM, especie, edad, árboles y volumen ([ejemplo Cayambe](https://www.timbertradeportal.com/files/upload/ecuador/Informe-preliminar-Plantaciones-Forestales.pdf)) | Solicitud al MAG | Excelentes puntos "eucalipto seguro" |
| **Campañas propias (EPN)** | Puntos GPS de eucalipto, pino, nativo, páramo, pasto; carga de hojarasca y combustible; foto con dron | A levantar | Ver sección 4 |
| Tesis de UTN, ESPOCH, UNL, USFQ, ESPE | Inventarios locales de eucalipto con coordenadas | Repositorios universitarios | Útiles por zonas (Imbabura, Chimborazo, Loja) |

### 1.5 Datos de incendios para cruzar con el eucalipto

| Fuente | Uso | Acceso | Resolución | Periodo |
|---|---|---|---|---|
| **MODIS MCD64A1 C6.1** | Respuesta principal (área quemada mensual) | GEE `MODIS/061/MCD64A1` | 500 m | 2000-presente |
| VIIRS VNP14IMG / FIRMS | Focos activos; capta incendios pequeños | [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov) | 375 m | 2012-presente |
| Sentinel-2 dNBR | Validar cicatrices < 10 ha en zonas con eucalipto | GEE | 20 m | 2017-presente |
| Registros de la SNGR y del Cuerpo de Bomberos de Quito | Eventos con fecha, lugar y a veces vegetación afectada (los incendios de Quito 2024 en Guápulo y Auqui involucraron eucalipto) | Solicitud LOTAIP | Puntos | Variable |

### 1.6 Literatura clave

| Referencia | Para qué sirve |
|---|---|
| Zapata-Ríos et al. 2021, *J. Mt. Sci.* (en la carpeta) | Usó cobertura MAE/MAGAP 2014 nivel 1; el bosque reduce la probabilidad. Justifica separar plantación de bosque nativo |
| Balaguer-Beser et al. 2026, *Fire Ecology* (en la carpeta) | Índices Sentinel-2 (NDMI, MSI, BSI) y meteorología en quemas de Loja; plantilla para el trabajo de campo |
| Lin et al. 2023, *Forests* 14(9):1864 ([enlace](https://www2.mdpi.com/1999-4907/14/9/1864)) | Mapeo de eucalipto con Sentinel-1/2 multitemporal + Random Forest en GEE (OA 98 %). Receta replicable |
| Heliyon 2023, *Spatial distribution and expansion of Eucalyptus in its hotspots* ([enlace](https://www.sciencedirect.com/science/article/pii/S2405844023016006)) | Expansión de eucalipto en paisajes agrícolas (fuera de Ecuador); método de detección de cambio |
| Ross et al. 2017, *Land* 6(3):46 ([doi](https://doi.org/10.3390/land6030046)) | Cambio de uso en el páramo centro-sur del Ecuador 1979-2014, incluye plantaciones |
| *Mapping the páramo land-cover in the Northern Andes*, IJRS 2021 ([doi](https://www.tandfonline.com/doi/full/10.1080/01431161.2021.1964709)) | Clasificación del páramo y sus plantaciones con satélite |
| *Conversion of Andean montane forest to exotic forest plantation…* Podocarpus ([enlace](https://www.researchgate.net/publication/365951438)) | Efectos de plantaciones exóticas en el sur del Ecuador |
| BID, *Diagnóstico de la cadena forestal sustentable de Ecuador* ([PDF](https://publications.iadb.org/publications/spanish/document/Diagnostico-de-la-cadena-forestalsustentable-de-Ecuador-cadena-forestal-sostenible.pdf)) | Cifras oficiales de plantaciones (258 658 ha en mapa; 171 332 ha registradas en 2023) y fuentes del MAG |
| Primicias, 29-09-2024 ([enlace](https://primicias.ec/ciencia-tecnologia/incendios-forestales-quito-guapulo-eucaliptos-combustible-79982)) | Contexto: el problema es la plantación abandonada con hojarasca acumulada, no solo la especie. Motiva la variable de manejo/edad |

---

## 2. Cómo construir el mapa de eucalipto (flujo en GEE)

1. **Área de estudio:** Sierra (límite de región natural del INEC o cota > 1 500 m), con zona de amortiguamiento de 5 km.
2. **Etiquetas:**
   - Eucalipto: polígonos "Eucalipto" del mapa IEE/MAGAP 1:25 000 que **sigan siendo árbol hoy** (filtrar con altura de dosel > 8 m y sin pérdida en Hansen), más predios del registro del MAG y puntos de campo.
   - Pino: clase "Pino" del mismo mapa.
   - Bosque nativo, páramo, matorral, pasto/cultivo, urbano: MapBiomas Col. 3 + mapa de ecosistemas, en zonas donde no haya plantación según el 1:25 000.
   - Revisar visualmente una muestra con Planet o ortofotos. Meta: ≥ 500 puntos por clase, estratificados de Carchi a Loja.
3. **Predictores:** medianas estacionales de Sentinel-2 (B2-B12, NDVI, NDRE, NDMI, red-edge), Sentinel-1 VV/VH y textura GLCM, altura de dosel, elevación y pendiente.
4. **Clasificador:** Random Forest (o segmentación SNIC + RF, como Lin et al. 2023), a 10 m.
5. **Validación:** independiente y espacialmente separada (bloques), matriz de confusión, exactitud del productor y del usuario para eucalipto, área ajustada con el método de Olofsson.
6. **Serie temporal:** repetir con Landsat para 2001, 2005, 2010, 2015 (o anual con el flujo de MapBiomas) para que el eucalipto varíe en el tiempo como el MCD64A1. Si no alcanza, usar un mapa estático 2020-2023 y declarar el supuesto.

---

## 3. Variables de eucalipto por celda (500 m o 1 km)

| Variable | Definición | Cómo se calcula | Unidad |
|---|---|---|---|
| `euc_pct` | Fracción de la celda cubierta por eucalipto | Media del ráster binario 10 m dentro de la celda (`reduceResolution` en GEE) | % |
| `euc_dist` | Distancia del centro de la celda a la plantación más cercana | Distancia euclidiana desde píxeles de eucalipto (`fastDistanceTransform`), luego valor en el centroide | m (usar log) |
| `euc_edge_native` | Longitud de borde eucalipto-vegetación nativa (bosque, páramo, matorral) | Píxeles de eucalipto con un vecino nativo (kernel 3×3) × 10 m, sumados por celda | m/km² |
| `euc_edge_agri` | Borde eucalipto-pasto/cultivo (zona de quemas agrícolas) | Igual que el anterior con la clase agropecuaria | m/km² |
| `euc_pct_nb` | % de eucalipto en el vecindario (1-3 km) | Media focal; en la GNN también aparece por las aristas, pero sirve para la línea base logística | % |
| `euc_patch_mean` | Tamaño medio de parche (hilera/cortina vs. plantación) | Componentes conectados, área media por celda | ha |
| `euc_age` / `euc_harvest` | Años desde la última cosecha o pérdida | Hansen lossyear o GFAM-N/P dentro de los píxeles de eucalipto | años |
| `euc_height` | Altura media del dosel del eucalipto | Media de altura de dosel enmascarada con eucalipto | m |
| `pine_pct` | % de pino (control) | Igual que `euc_pct` | % |
| `native_pct` | % de vegetación nativa | Igual que `euc_pct` | % |

Recomendaciones de análisis:
- Usar **región natural o piso altitudinal** como estrato, porque el eucalipto está casi solo en la Sierra (ver `resumen_variables_reunion.md`).
- Separar el efecto del eucalipto del de la cercanía a vías y poblados (el eucalipto suele estar junto a ambos): incluir esas distancias siempre y revisar colinealidad (VIF).
- Probar sensibilidad del umbral: `euc_pct` > 0, > 10 % y > 30 %.
- Propagar el error del mapa: repetir el modelo con mapas generados por bootstrap del clasificador.

---

## 4. Trabajo de campo sugerido (para la parte "Sentinel + campo" de la postulación)

- **Puntos de verdad de terreno:** 150-300 sitios en 4-5 provincias (p. ej. Imbabura, Pichincha, Cotopaxi, Chimborazo, Loja), con foto y GPS, por clase.
- **Combustible:** carga de hojarasca (g/m²), profundidad, humedad y presencia de corteza suelta en eucalipto manejado vs. abandonado; mismo protocolo en pino, páramo y matorral nativo.
- **Dron:** ortofoto y modelo de altura en 10-20 parcelas para validar bordes y altura.
- **Cicatrices recientes:** visitar incendios de 2023-2025 que tocan eucalipto para validar MCD64A1 y dNBR.

---

## 5. Gestiones a iniciar ya

1. Descargar el mapa 1:25 000 por cantón de la Sierra (IGM/SIGTIERRAS) y los CUT del MAATE 2014-2022.
2. Pedir por oficio al **MAG (Subsecretaría de Producción Forestal)** el registro de plantaciones y las licencias de aprovechamiento de eucalipto con coordenadas (2012-presente).
3. Pedir al **MAATE** las parcelas de la ENF con especie y la última versión del CUT 2022.
4. Pedir a la **SNGR** y al **Cuerpo de Bomberos de Quito** los registros de incendios forestales con coordenadas.
5. Revisar la fuente de Ecuador dentro del SDPT v2.1 de WRI.

## 6. Limitaciones a declarar

- El mapa 1:25 000 tiene más de 10 años y cobertura cantonal desigual; hay plantaciones nuevas y cosechadas desde entonces.
- Cortinas rompevientos e hileras de eucalipto son más angostas que 10 m en muchos casos; se subestimarán.
- El efecto del eucalipto puede confundirse con el uso humano del paisaje (quemas agrícolas, vías). El diseño causal debe controlarlo.
- MCD64A1 no detecta incendios menores a ≈ 10-25 ha, que son comunes en plantaciones periurbanas.
