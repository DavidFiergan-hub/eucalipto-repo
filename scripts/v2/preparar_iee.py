"""Une los polígonos "Eucalipto" y "Pino" del mapa de cobertura y uso 1:25 000 (IEE/MAGAP, SIGTIERRAS)
de varios cantones en un solo shapefile listo para subir como asset a Earth Engine.

Las geodatabases o shapefiles por cantón se bajan del geoportal del IGM (geodescargas) o de SIGTIERRAS.
Los nombres de los campos cambian entre cantones, así que el script busca en todos los campos de texto
el valor que contenga "EUCALIPTO" o "PINO" (sin importar mayúsculas ni tildes).

Uso:  python preparar_iee.py CARPETA_CON_CANTONES SALIDA.zip
      (CARPETA puede tener .shp, .gpkg, .gdb o .zip; se leen todas las capas de polígonos)
Salida: shapefile comprimido con los campos clase (1 eucalipto, 2 pino), canton, area_ha.
Subirlo en Earth Engine: Assets > NEW > Shape files, con el nombre iee_eucalipto.
"""
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


def normal(x):
    return unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().upper()


def capas(carpeta):
    for f in sorted(Path(carpeta).rglob("*")):
        suf = f.suffix.lower()
        if suf in (".shp", ".gpkg") or (suf == ".gdb" and f.is_dir()):
            yield f
        elif suf == ".zip":
            yield Path(f"zip://{f}")


def clase_de(fila, campos):
    texto = " ".join(normal(fila[c]) for c in campos if pd.notna(fila[c]))
    if "EUCALIPTO" in texto:
        return 1
    if re.search(r"\bPINOS?\b", texto):
        return 2
    return 0


def main(carpeta, salida):
    partes = []
    for ruta in capas(carpeta):
        try:
            nombres = [c[0] for c in pyogrio.list_layers(ruta) if "Polygon" in str(c[1])]
        except Exception as e:  # archivos que no son capas geográficas
            print("se omite", ruta, e)
            continue
        for capa in nombres or [None]:
            g = gpd.read_file(ruta, layer=capa)
            campos = [c for c in g.columns if c != "geometry" and g[c].dtype == object]
            if not campos or g.empty:
                continue
            g["clase"] = g.apply(clase_de, axis=1, campos=campos)
            g = g[g.clase > 0]
            if g.empty:
                continue
            g = g.to_crs(32717)
            g["area_ha"] = g.area / 1e4
            g["canton"] = Path(str(ruta)).stem
            partes.append(g[["clase", "canton", "area_ha", "geometry"]].to_crs(4326))
            print(f"{ruta} [{capa}]: {int((g.clase == 1).sum())} polígonos de eucalipto, "
                  f"{int((g.clase == 2).sum())} de pino")
    if not partes:
        sys.exit("No se encontró ningún polígono con 'Eucalipto' o 'Pino'. Revisar la carpeta.")
    todo = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=4326)
    todo["geometry"] = todo.geometry.make_valid()
    print(todo.groupby("clase").area_ha.agg(["count", "sum"]).rename(index={1: "eucalipto", 2: "pino"}))
    tmp = Path(salida).with_suffix("")
    tmp.mkdir(exist_ok=True)
    todo.to_file(tmp / "iee_eucalipto.shp")
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp.glob("iee_eucalipto.*"):
            z.write(f, f.name)
    print("listo:", salida)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
