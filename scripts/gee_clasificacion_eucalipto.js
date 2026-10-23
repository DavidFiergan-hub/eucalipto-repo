// Clasificación de eucalipto en la Sierra del Ecuador con Sentinel-2 + Sentinel-1 (Google Earth Engine)
// Resultado: ráster binario de eucalipto a 10 m que reemplaza a "plant_*" (MapBiomas Silvicultura)
// en la base de datos. Las variables euc_pct, euc_dist, euc_edge_native se calculan con el mismo
// script de Python (build_eucalipto.py) cambiando la clase de plantación por este ráster.
//
// Antes de correr:
//  1. Subir como asset los polígonos de la clase "Eucalipto" del mapa de cobertura y uso 1:25 000
//     (IEE/MAGAP, SIGTIERRAS) de los cantones de la Sierra -> users/<usuario>/iee_eucalipto
//  2. Subir puntos de campo (opcional) con la columna "clase" (1 = eucalipto, 2 = pino, 3 = nativo,
//     4 = pasto/cultivo, 5 = urbano/suelo) -> users/<usuario>/puntos_campo

var ANIO = 2023;
var iee = ee.FeatureCollection('users/<usuario>/iee_eucalipto');   // CAMBIAR
var mb = ee.Image('projects/mapbiomas-public/assets/ecuador/collection3/mapbiomas_ecuador_collection3_integration_v1')
  .select('classification_' + ANIO);  // verificar el nombre del asset en ecuador.mapbiomas.org

// Área de estudio: Ecuador continental >= 1000 m
var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').select('DEM').mosaic();
var ecuador = ee.FeatureCollection('FAO/GAUL/2015/level0').filter(ee.Filter.eq('ADM0_NAME', 'Ecuador'))
  .geometry().intersection(ee.Geometry.Rectangle([-81.2, -5.1, -75.1, 1.6]), 100);
var sierra = dem.gte(1000).clip(ecuador);

// Sentinel-2 con Cloud Score+
var csPlus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
function s2(start, end) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(ecuador).filterDate(start, end)
    .linkCollection(csPlus, ['cs_cdf'])
    .map(function (img) { return img.updateMask(img.select('cs_cdf').gte(0.6)).divide(10000); })
    .select(['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12']);
}
function indices(img) {
  return img.addBands([
    img.normalizedDifference(['B8', 'B4']).rename('NDVI'),
    img.normalizedDifference(['B8', 'B5']).rename('NDRE'),
    img.normalizedDifference(['B8', 'B11']).rename('NDMI'),
    img.normalizedDifference(['B8A', 'B12']).rename('NBR')
  ]);
}
// Dos temporadas (seca jun-sep, húmeda ene-abr) y dos años para llenar nubes
var seca = indices(s2((ANIO - 1) + '-06-01', ANIO + '-09-30').filter(ee.Filter.calendarRange(6, 9, 'month')).median())
  .regexpRename('$', '_seca');
var humeda = indices(s2((ANIO - 1) + '-01-01', ANIO + '-04-30').filter(ee.Filter.calendarRange(1, 4, 'month')).median())
  .regexpRename('$', '_hum');

// Sentinel-1 (estructura del dosel, sin nubes)
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(ecuador)
  .filterDate((ANIO - 1) + '-01-01', ANIO + '-12-31')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .select(['VV', 'VH']).median();
var s1tex = s1.select('VH').multiply(100).toInt().glcmTexture({size: 3}).select(['VH_contrast', 'VH_ent']);

// Altura de dosel (Meta/WRI 1 m, reducido) y topografía
var altura = ee.ImageCollection('projects/meta-forest-monitoring-okw37/assets/CanopyHeight').mosaic()
  .reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 1024}).reproject({crs: 'EPSG:4326', scale: 10})
  .rename('altura');
var slope = ee.Terrain.slope(dem).rename('pendiente');

var stack = seca.addBands(humeda).addBands(s1).addBands(s1tex).addBands(altura)
  .addBands(dem.rename('elev')).addBands(slope).updateMask(sierra);

// Muestras de entrenamiento
// Eucalipto: polígonos IEE que hoy siguen siendo árbol (altura > 8 m)
var eucMask = ee.Image(0).paint(iee, 1).and(altura.gt(8)).selfMask().rename('clase');
// Otras clases desde MapBiomas lejos de los polígonos IEE (buffer 300 m)
var lejos = ee.Image(1).paint(iee.map(function (f) { return f.buffer(300); }), 0);
var otras = mb.remap([9, 3, 4, 13, 81, 82, 12, 21, 24, 25], [2, 3, 3, 3, 3, 3, 3, 4, 5, 5]).updateMask(lejos).rename('clase');
var etiquetas = ee.ImageCollection([eucMask.toInt(), otras.toInt()]).mosaic();

var muestras = stack.addBands(etiquetas).stratifiedSample({
  numPoints: 1500, classBand: 'clase', region: ecuador, scale: 10, seeds: 42,
  geometries: true, tileScale: 8
}).randomColumn('r', 7);

// Validación espacial: bloques de 0.1 grados
muestras = muestras.map(function (f) {
  var c = f.geometry().coordinates();
  var bloque = ee.Number(c.get(0)).multiply(10).floor().add(ee.Number(c.get(1)).multiply(10).floor().multiply(1000));
  return f.set('bloque', bloque, 'test', bloque.mod(5).eq(0));
});
var train = muestras.filter(ee.Filter.eq('test', 0));
var test = muestras.filter(ee.Filter.eq('test', 1));

var rf = ee.Classifier.smileRandomForest(300).train(train, 'clase', stack.bandNames());
var cm = test.classify(rf).errorMatrix('clase', 'classification');
print('Matriz de confusión', cm, 'OA', cm.accuracy(), 'Exactitud productor', cm.producersAccuracy(),
      'Exactitud usuario', cm.consumersAccuracy());

var clasif = stack.classify(rf);
var eucalipto = clasif.eq(1).selfMask().rename('eucalipto');
Map.centerObject(ee.Geometry.Point([-78.5, -0.3]), 10);
Map.addLayer(eucalipto, {palette: ['d7301f']}, 'Eucalipto ' + ANIO);

Export.image.toDrive({
  image: clasif.toByte(), description: 'clasif_sierra_' + ANIO, folder: 'eucalipto',
  region: ecuador, scale: 10, crs: 'EPSG:4326', maxPixels: 1e13
});
Export.table.toDrive({collection: test.classify(rf), description: 'validacion_' + ANIO, folder: 'eucalipto'});
