// =================================================================================================
// Mapa propio de eucalipto (v2), paso 1: polígonos de entrenamiento por fotointerpretación
// Google Earth Engine, Code Editor. Se corre con la cuenta del proyecto.
//
// Para qué sirve: la v2 no puede esperar a que el MAG o el IGM entreguen sus datos. Con este script se
// dibujan rodales seguros de cada clase sobre imágenes de alta resolución. Esos polígonos entrenan el
// clasificador del paso 2. Si después llegan los polígonos "Eucalipto" del 1:25 000 o el registro del
// MAG, se suman en el paso 2 (variables IEE y MAG), sin rehacer nada.
//
// Cómo dibujar (unas 6 a 8 horas en total):
//  1. En "Geometry Imports" (arriba a la izquierda del mapa) crear 6 capas con "+ new layer" y ponerles
//     estos nombres exactos: eucalipto, pino, bosque, paramo, agro, otros.
//     En el engranaje de cada capa elegir "Import as: FeatureCollection".
//  2. Dibujar polígonos pequeños (0,5 a 5 ha) DENTRO de rodales homogéneos, lejos de los bordes.
//     Meta mínima: 80 de eucalipto, 40 de pino y 40 de cada una de las demás, repartidos de Carchi a Loja
//     (la cuadrícula de 0,5° ayuda a no concentrarse cerca de Quito). Más polígonos chicos y dispersos
//     valen más que pocos grandes.
//  3. Correr el script. Revisa los polígonos y crea la tarea "etiquetas_eucalipto" en la pestaña Tasks.
//     Darle RUN: guarda el asset que lee el paso 2.
//
// Cómo reconocer cada clase en la imagen de Google (capa SATELLITE) y en el falso color de Sentinel-2:
//  - eucalipto (1): copas redondeadas, irregulares, verde grisáceo o azulado; rodales en laderas, hileras y
//    cortinas en linderos; en falso color (SWIR-NIR-rojo) se ve verde más claro que el pino. Casi siempre
//    entre 2 200 y 3 300 m. Si hay duda con el pino, no dibujar.
//  - pino (2): copas cónicas oscuras, plantaciones densas y regulares, sobre todo 3 000 a 3 800 m, a menudo
//    en el páramo (Cotopaxi, Chimborazo, Azuay, Cañar).
//  - bosque (3): bosque nativo montano: dosel heterogéneo, quebradas, sin patrón de siembra.
//  - paramo (4): páramo, herbazal y arbustal nativo.
//  - agro (5): pastos y cultivos, incluido el mosaico con casas dispersas (sin árboles).
//  - otros (6): urbano, vías, suelo desnudo, roca, agua.
//  La capa "Pérdida Hansen 2013-2024" marca dónde hubo tala: no dibujar eucalipto ni pino encima.
// =================================================================================================

var ASSET_SALIDA = 'users/USUARIO/eucalipto_etiquetas';   // CAMBIAR por la carpeta de assets del proyecto

// Sierra: Ecuador continental sobre 800 m (las celdas de la base están sobre 1 000 m; se deja margen)
var demCol = ee.ImageCollection('COPERNICUS/DEM/GLO30').select('DEM');
var dem = demCol.mosaic().setDefaultProjection(demCol.first().projection());
var ecuador = ee.FeatureCollection('FAO/GAUL/2015/level0').filter(ee.Filter.eq('ADM0_NAME', 'Ecuador'));
var caja = ee.Geometry.Rectangle([-80.5, -5.1, -77.2, 1.2], null, false);
var sierra = dem.gte(800).updateMask(ee.Image(0).paint(ecuador, 1));

// Sentinel-2 2023-2024 temporada seca (jun-sep), con Cloud Score+
var cs = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(caja).filterDate('2023-01-01', '2024-12-31')
  .filter(ee.Filter.calendarRange(6, 9, 'month'))
  .linkCollection(cs, ['cs_cdf'])
  .map(function (img) { return img.updateMask(img.select('cs_cdf').gte(0.6)).divide(10000); })
  .median();

var altura = ee.ImageCollection('projects/meta-forest-monitoring-okw37/assets/CanopyHeight').mosaic();
var hansen = ee.Image('UMD/hansen/global_forest_change_2024_v1_12');
var perdida = hansen.select('lossyear').gte(13).selfMask();

// Cuadrícula de 0,5° para repartir el dibujo
var celdas = ee.FeatureCollection(ee.List.sequence(-80.5, -77.5, 0.5).map(function (x) {
  return ee.List.sequence(-5.0, 1.0, 0.5).map(function (y) {
    return ee.Feature(ee.Geometry.Rectangle([x, y, ee.Number(x).add(0.5), ee.Number(y).add(0.5)]));
  });
}).flatten());

Map.setOptions('SATELLITE');
Map.centerObject(ee.Geometry.Point([-78.55, -0.25]), 12);
Map.addLayer(s2, {bands: ['B4', 'B3', 'B2'], min: 0.01, max: 0.15}, 'Sentinel-2 color real 2023-24', false);
Map.addLayer(s2, {bands: ['B11', 'B8', 'B4'], min: 0.01, max: 0.40}, 'Sentinel-2 falso color (SWIR-NIR-rojo)', false);
Map.addLayer(altura.updateMask(altura.gt(3)), {min: 3, max: 30, palette: ['ffffcc', '78c679', '005a32']},
             'Altura del dosel (Meta, m)', false);
Map.addLayer(perdida, {palette: ['ff00ff']}, 'Pérdida Hansen 2013-2024', false);
Map.addLayer(sierra.selfMask(), {palette: ['ffffff'], opacity: 0.15}, 'Sierra (> 800 m)', false);
Map.addLayer(ee.Image().byte().paint(celdas, 1, 1), {palette: ['ffff00']}, 'Cuadrícula 0,5°');

// ---- Unir las capas dibujadas ----------------------------------------------------------------------
function capa(fc, clase, nombre) {
  return ee.FeatureCollection(fc).map(function (f) {
    return ee.Feature(f.geometry(), {clase: clase, nombre: nombre, origen: 'fotointerpretacion'});
  });
}
var partes = [];
if (typeof eucalipto !== 'undefined') partes.push(capa(eucalipto, 1, 'eucalipto'));
if (typeof pino !== 'undefined') partes.push(capa(pino, 2, 'pino'));
if (typeof bosque !== 'undefined') partes.push(capa(bosque, 3, 'bosque'));
if (typeof paramo !== 'undefined') partes.push(capa(paramo, 4, 'paramo'));
if (typeof agro !== 'undefined') partes.push(capa(agro, 5, 'agro'));
if (typeof otros !== 'undefined') partes.push(capa(otros, 6, 'otros'));

if (partes.length === 0) {
  print('Todavía no hay capas dibujadas. Crear las capas eucalipto, pino, bosque, paramo, agro y otros.');
} else {
  var unidas = partes[0];
  for (var i = 1; i < partes.length; i++) unidas = unidas.merge(partes[i]);
  var etiquetas = unidas.map(function (f) {
    return f.set('area_ha', f.geometry().area(1).divide(1e4));
  });
  print('Polígonos por clase (1 eucalipto, 2 pino, 3 bosque, 4 páramo, 5 agro, 6 otros)',
        etiquetas.aggregate_histogram('clase'));
  print('Hectáreas por clase', etiquetas.reduceColumns(ee.Reducer.sum().group(0, 'clase'), ['clase', 'area_ha']));
  // Polígonos de eucalipto o pino que tocan una tala reciente (revisarlos o borrarlos)
  var conTala = etiquetas.filter(ee.Filter.lte('clase', 2)).map(function (f) {
    var p = perdida.unmask(0).reduceRegion({reducer: ee.Reducer.mean(), geometry: f.geometry(), scale: 30});
    return f.set('frac_tala', p.get('lossyear'));
  }).filter(ee.Filter.gt('frac_tala', 0.2));
  print('Polígonos de plantación con más de 20 % talado desde 2013 (revisar):', conTala);
  Export.table.toAsset({collection: etiquetas, description: 'etiquetas_eucalipto', assetId: ASSET_SALIDA});
}
