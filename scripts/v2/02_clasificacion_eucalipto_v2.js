// =================================================================================================
// Mapa propio de eucalipto (v2), paso 2: clasificación anual 2011-2024 con Landsat (30 m)
// Google Earth Engine, Code Editor.
//
// Por qué Landsat y no Sentinel-2: el panel de FIRELAB-Sierra necesita la cobertura del año anterior
// para 2012-2024, o sea mapas de 2011 a 2024. Sentinel-2 en el Ecuador empieza en 2017-2019, así que
// solo Landsat da una serie pareja. Además 30 m es la misma resolución de MapBiomas (la v1), y la
// comparación v1/v2 queda limpia. Para 10 m queda ../gee_clasificacion_eucalipto.js (un solo año).
//
// Clases: 1 eucalipto, 2 pino, 3 bosque nativo, 4 páramo/arbustal/herbazal, 5 pasto/cultivo, 6 otros.
// Método:
//  - Compuesto por año con una ventana de 3 años centrada (año-1 a año+1); los huecos por nubes se
//    rellenan con una ventana de 5 años. Landsat 5/7 se armonizan a Landsat 8/9 (Roy et al. 2016).
//  - Predictores: medianas de 6 bandas, NDVI, NBR, NDMI, percentiles 10 y 90 de NDVI y NDMI, elevación
//    y pendiente. No entra la altura del dosel porque es de un solo año (2020) y sesgaría los años viejos.
//  - Entrenamiento con los polígonos del paso 1 (más IEE y MAG si existen), muestreados en los compuestos
//    de 2021, 2022 y 2023, y UN solo Random Forest que se aplica a todos los años. Mezclar años en el
//    entrenamiento lo hace robusto a las diferencias entre sensores.
//  - En eucalipto y pino solo entran píxeles sin tala Hansen desde 2013 (rodales en pie en esos años).
//  - Validación por bloques espaciales de 0,1° (20 % de los bloques fuera del entrenamiento).
//
// Se corre en dos etapas para que Earth Engine no se quede sin tiempo:
//  ETAPA = 1 -> crea la tarea "muestras_eucalipto_v2" (tabla de entrenamiento). Darle RUN y esperar.
//  ETAPA = 2 -> entrena, imprime la validación y crea una tarea por año "euc_clase_AAAA" más
//               "hansen_lossyear_sierra" y "validacion_eucalipto_v2". Darles RUN a todas.
// Los GeoTIFF quedan en Google Drive, carpeta eucalipto_v2. Bajarlos completos (Earth Engine puede
// partir un año en varios archivos; build_eucalipto_v2.py los une solo).
// =================================================================================================

var ETAPA = 1;                                                // 1 = muestras; 2 = mapas
var ETIQUETAS = 'users/USUARIO/eucalipto_etiquetas';           // CAMBIAR (salida del paso 1)
var MUESTRAS = 'users/USUARIO/muestras_eucalipto_v2';          // CAMBIAR (salida de la etapa 1)
var IEE = null;   // opcional: 'users/USUARIO/iee_eucalipto' (preparar_iee.py: polígonos con clase 1 y 2)
var MAG = null;   // opcional: puntos o polígonos del registro del MAG con clase 1 (eucalipto) o 2 (pino)
var ANIOS = [2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
var ANIOS_ENTRENAMIENTO = [2021, 2022, 2023];
var PIXELES_POR_CLASE = 1500;                                 // por año de entrenamiento
var CARPETA = 'eucalipto_v2';
var NOMBRES_CLASE = ['', 'eucalipto', 'pino', 'bosque', 'paramo', 'agro', 'otros'];

// Malla de salida: la de Hansen (0,00025°, ~28 m) recortada a la Sierra, para que la tala calce píxel a píxel
var CAJA = ee.Geometry.Rectangle([-80.5, -5.1, -77.2, 1.2], null, false);
var MALLA = [0.00025, 0, -180, 0, -0.00025, 80];

// ---- Área de estudio -------------------------------------------------------------------------------
var demCol = ee.ImageCollection('COPERNICUS/DEM/GLO30').select('DEM');
var dem = demCol.mosaic().setDefaultProjection(demCol.first().projection()).rename('elev');
var pendiente = ee.Terrain.slope(dem).rename('pendiente');
var ecuador = ee.FeatureCollection('FAO/GAUL/2015/level0').filter(ee.Filter.eq('ADM0_NAME', 'Ecuador'));
var sierra = dem.gte(800).and(ee.Image(0).paint(ecuador, 1));
var hansen = ee.Image('UMD/hansen/global_forest_change_2024_v1_12');

// ---- Landsat Collection 2 nivel 2, armonizado ------------------------------------------------------
var NOMBRES = ['azul', 'verde', 'rojo', 'nir', 'swir1', 'swir2'];
var BANDAS_TM = ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'];   // Landsat 5 y 7
var BANDAS_OLI = ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'];  // Landsat 8 y 9
var PEND = ee.Image.constant([0.8474, 0.8483, 0.9047, 0.8462, 0.8937, 0.9071]);  // TM/ETM+ -> OLI
var INTER = ee.Image.constant([0.0003, 0.0088, 0.0061, 0.0412, 0.0254, 0.0172]);

function preparar(bandas, armonizar) {
  return function (img) {
    var qa = img.select('QA_PIXEL');
    var limpio = qa.bitwiseAnd(63).eq(0)            // relleno, nube dilatada, cirro, nube, sombra, nieve
      .and(img.select('QA_RADSAT').eq(0));
    var sr = img.select(bandas).multiply(0.0000275).add(-0.2);
    if (armonizar) sr = sr.multiply(PEND).add(INTER);
    sr = sr.rename(NOMBRES).updateMask(limpio);
    return ee.Image(sr.addBands([
      sr.normalizedDifference(['nir', 'rojo']).rename('NDVI'),
      sr.normalizedDifference(['nir', 'swir2']).rename('NBR'),
      sr.normalizedDifference(['nir', 'swir1']).rename('NDMI')
    ]).copyProperties(img, ['system:time_start']));
  };
}

function landsat(ini, fin) {
  var col = function (id, bandas, armonizar) {
    return ee.ImageCollection(id).filterBounds(CAJA).filterDate(ini, fin).map(preparar(bandas, armonizar));
  };
  return col('LANDSAT/LT05/C02/T1_L2', BANDAS_TM, true)
    .merge(col('LANDSAT/LE07/C02/T1_L2', BANDAS_TM, true).filterDate('1999-01-01', '2017-01-01'))
    .merge(col('LANDSAT/LC08/C02/T1_L2', BANDAS_OLI, false))
    .merge(col('LANDSAT/LC09/C02/T1_L2', BANDAS_OLI, false));
}

function compuesto(anio, mitad) {
  var col = landsat(ee.Date.fromYMD(anio - mitad, 1, 1), ee.Date.fromYMD(anio + mitad + 1, 1, 1));
  return col.median().addBands(col.select(['NDVI', 'NDMI']).reduce(ee.Reducer.percentile([10, 90])));
}

function predictores(anio) {
  return compuesto(anio, 1).unmask(compuesto(anio, 2))
    .addBands(dem).addBands(pendiente).updateMask(sierra).float();
}

// ---- Etiquetas ---------------------------------------------------------------------------------------
function etiquetas() {
  var fc = ee.FeatureCollection(ETIQUETAS).select(['clase']);
  if (IEE) fc = fc.merge(ee.FeatureCollection(IEE).select(['clase']));
  if (MAG) fc = fc.merge(ee.FeatureCollection(MAG).select(['clase']));
  var img = ee.Image().byte().paint(fc, 'clase').rename('clase');
  // Plantaciones: solo píxeles sin tala desde 2013
  var sinTala = hansen.select('lossyear').lt(13);
  return img.updateMask(img.gt(2).or(sinTala));
}

function bloque(f) {
  var c = f.geometry().coordinates();
  var b = ee.Number(c.get(0)).multiply(10).floor().multiply(1000).add(ee.Number(c.get(1)).multiply(10).floor());
  return f.set('bloque', b, 'test', b.abs().mod(5).eq(0));
}

// ---- ETAPA 1: tabla de muestras ---------------------------------------------------------------------
if (ETAPA === 1) {
  var lab = etiquetas();
  var region = ee.FeatureCollection(ETIQUETAS).geometry().bounds(1000);
  var muestras = ee.FeatureCollection([]);
  ANIOS_ENTRENAMIENTO.forEach(function (a) {
    muestras = muestras.merge(predictores(a).addBands(lab).stratifiedSample({
      numPoints: PIXELES_POR_CLASE, classBand: 'clase', region: region, scale: 30,
      seed: a, geometries: true, tileScale: 16
    }).map(function (f) { return f.set('anio', a); }));
  });
  muestras = muestras.map(bloque);
  Export.table.toAsset({collection: muestras, description: 'muestras_eucalipto_v2', assetId: MUESTRAS});
  print('Etapa 1 lista: correr la tarea muestras_eucalipto_v2 en Tasks y después poner ETAPA = 2.');
  Map.addLayer(lab, {min: 1, max: 6, palette: ['d7301f', '00441b', '41ab5d', 'c2a5cf', 'fee391', '969696']}, 'Etiquetas');
}

// ---- ETAPA 2: entrenamiento, validación y mapas ------------------------------------------------------
if (ETAPA === 2) {
  var m = ee.FeatureCollection(MUESTRAS).filter(ee.Filter.notNull(['NDVI', 'nir', 'NDVI_p10']));
  var bandas = predictores(2023).bandNames();
  var train = m.filter(ee.Filter.eq('test', 0));
  var test = m.filter(ee.Filter.eq('test', 1));
  print('Muestras de entrenamiento por clase', train.aggregate_histogram('clase'));
  print('Muestras de validación por clase', test.aggregate_histogram('clase'));

  var rf = ee.Classifier.smileRandomForest({numberOfTrees: 300, minLeafPopulation: 2, seed: 42})
    .train(train, 'clase', bandas);
  var val = test.classify(rf);
  var cm = val.errorMatrix('clase', 'classification', [1, 2, 3, 4, 5, 6]);
  print('Matriz de confusión (filas = referencia, columnas = mapa; orden 1..6)', cm);
  print('Exactitud global', cm.accuracy(), 'Kappa', cm.kappa());
  print('Exactitud del productor por clase (1..6)', cm.producersAccuracy());
  print('Exactitud del usuario por clase (1..6)', cm.consumersAccuracy());
  print('Importancia de variables', rf.explain().get('importance'));

  ANIOS.forEach(function (a) {
    var clase = predictores(a).classify(rf).toByte();
    if (a === 2023) {
      Map.centerObject(ee.Geometry.Point([-78.45, -0.2]), 11);
      Map.addLayer(clase, {min: 1, max: 6, palette: ['d7301f', '00441b', '41ab5d', 'c2a5cf', 'fee391', '969696']}, 'Clases 2023');
    }
    Export.image.toDrive({
      image: clase.unmask(0).toByte(), description: 'euc_clase_' + a, folder: CARPETA,
      fileNamePrefix: 'euc_clase_' + a, region: CAJA, crs: 'EPSG:4326', crsTransform: MALLA,
      maxPixels: 1e13, fileFormat: 'GeoTIFF'
    });
  });
  Export.image.toDrive({
    image: hansen.select('lossyear').unmask(0).toByte(), description: 'hansen_lossyear_sierra', folder: CARPETA,
    fileNamePrefix: 'hansen_lossyear_sierra', region: CAJA, crs: 'EPSG:4326', crsTransform: MALLA, maxPixels: 1e13
  });
  Export.table.toDrive({collection: val, description: 'validacion_eucalipto_v2', folder: CARPETA,
                        selectors: ['clase', 'classification', 'anio', 'bloque', '.geo']});
}
