"""Base de datos de plantaciones forestales (proxy de eucalipto) por celda MODIS 500 m.

Grilla: la misma de MCD64A1 (sinusoidal, 463.3127 m), para unir directo con las cicatrices.
Insumos (todos abiertos):
  - MapBiomas Ecuador Colección 3, cobertura anual 30 m (2001-2024)
  - Hansen Global Forest Change v1.12 (lossyear, treecover2000)
  - Copernicus DEM GLO-90
Uso: python build_eucalipto.py DATA_DIR OUT_DIR
"""
import glob
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds
from scipy import ndimage

DATA, OUT = sys.argv[1], sys.argv[2]
YEARS = list(range(2001, 2025))

# Grilla sinusoidal MODIS
R = 6371007.181
CELL = 463.31271653
X0, Y0 = -20015109.354, 10007554.677
NTILE = 2400

# Ventana continental en la grilla MapBiomas (excluye Galápagos)
LON0, LON1, LAT0, LAT1 = -81.2, -75.1, 1.8, -5.26
mb_ref = rasterio.open(f"{DATA}/mb/mb_2024.tif")
RES = mb_ref.res[0]
MB_LEFT, MB_TOP = mb_ref.transform.c, mb_ref.transform.f
C0 = int((LON0 - MB_LEFT) / RES)
C1 = min(int((LON1 - MB_LEFT) / RES), mb_ref.width)
ROWS = mb_ref.height
COLS = C1 - C0
BLOCK = 999  # múltiplo de 3 para la reducción a ~90 m

# Clases MapBiomas Ecuador Col. 3
PLANT = [9]                                   # Silvicultura
FOREST = [3, 4, 5, 6]                         # bosque natural
NONFOREST = [11, 12, 13, 81, 82]              # páramo, herbazal, arbustal, humedal
NATIVE = FOREST + NONFOREST
AGRI = [21, 74]                               # mosaico agropecuario, banano
URBAN = [24]
NODATA = [0, 27]

lon_px = MB_LEFT + (C0 + np.arange(COLS) + 0.5) * RES
lat_all = MB_TOP - (np.arange(ROWS) + 0.5) * RES


def sin_rc(lat, lon):
    latr, lonr = np.radians(lat), np.radians(lon)
    x = R * lonr * np.cos(latr)
    y = R * latr
    return np.floor((Y0 - y) / CELL).astype(np.int64), np.floor((x - X0) / CELL).astype(np.int64)


# Extensión de la grilla de celdas que cubre la ventana
_r, _c = sin_rc(np.array([LAT0, LAT0, LAT1, LAT1, 0.0, 0.0]), np.array([LON0, LON1, LON0, LON1, LON0, LON1]))
GR0, GR1 = _r.min() - 1, _r.max() + 2
GC0, GC1 = _c.min() - 1, _c.max() + 2
NR, NC = GR1 - GR0, GC1 - GC0
NCELL = NR * NC

# Lado compartido entre píxeles vecinos (m)
DY = RES * 110574.0


def dx_at(lat):
    return RES * 111320.0 * np.cos(np.radians(lat))


def load_hansen():
    out = {}
    for layer in ["lossyear", "treecover2000"]:
        srcs = [rasterio.open(f) for f in sorted(glob.glob(f"{DATA}/hansen/{layer}_*.tif"))]
        arr, tr = merge(srcs, bounds=(LON0 - 0.01, LAT1 - 0.01, LON1 + 0.01, LAT0 + 0.01))
        out[layer] = (arr[0], tr)
    return out


HANSEN = load_hansen()
H_TR = HANSEN["lossyear"][1]
H_COL = np.clip(np.floor((lon_px - H_TR.c) / H_TR.a).astype(np.int64), 0, HANSEN["lossyear"][0].shape[1] - 1)


def read_mb(year, r0, r1):
    with rasterio.open(f"{DATA}/mb/mb_{year}.tif") as src:
        return src.read(1, window=((r0, r1), (C0, C1)))


def year_stats(year):
    acc = {k: np.zeros(NCELL, np.float64) for k in
           ["valid", "plant", "forest", "nonforest", "agri", "urban",
            "edge_nat_m", "edge_agri_m", "loss_plant", "tc_mosaic_sum", "mosaic_n", "area_km2"]}
    small = np.zeros(((ROWS + 2) // 3, (COLS + 2) // 3), bool)
    prev_year = max(year - 1, YEARS[0])
    for r0 in range(0, ROWS, BLOCK):
        r1 = min(r0 + BLOCK, ROWS)
        ext = min(r1 + 1, ROWS)
        a_ext = read_mb(year, r0, ext)
        a = a_ext[: r1 - r0]
        if not (a > 0).any():
            continue
        lat = lat_all[r0:r1]
        grow, gcol = sin_rc(lat[:, None], lon_px[None, :])
        ids = ((grow - GR0) * NC + (gcol - GC0)).ravel()

        valid = ~np.isin(a, NODATA)
        P = np.isin(a, PLANT)
        N = np.isin(a, NATIVE)
        A = np.isin(a, AGRI)
        px_km2 = (dx_at(lat) * DY / 1e6)[:, None] * np.ones((1, COLS))

        def add(key, mask, w=None):
            m = mask.ravel()
            acc[key] += np.bincount(ids[m], weights=None if w is None else w.ravel()[m], minlength=NCELL)

        add("valid", valid)
        add("area_km2", valid, px_km2)
        add("plant", P)
        add("forest", np.isin(a, FOREST))
        add("nonforest", np.isin(a, NONFOREST))
        add("agri", A)
        add("urban", np.isin(a, URBAN))

        # Bordes: lados compartidos plantación-nativo y plantación-agrícola (4-vecindad).
        # Cada lado se asigna al píxel de la izquierda o de arriba (error máximo de un píxel).
        Pe = np.isin(a_ext, PLANT)
        n_own = r1 - r0
        n_v = min(n_own, a_ext.shape[0] - 1)
        dxl = dx_at(lat[:n_v])[:, None]
        for classes, key in [(NATIVE, "edge_nat_m"), (AGRI, "edge_agri_m")]:
            Oe = np.isin(a_ext, classes)
            O = Oe[:n_own]
            e = np.zeros(a.shape, np.float64)
            e[:, :-1] += ((P[:, :-1] & O[:, 1:]) | (O[:, :-1] & P[:, 1:])) * DY
            e[:n_v] += ((Pe[:n_v] & Oe[1:n_v + 1]) | (Oe[:n_v] & Pe[1:n_v + 1])) * dxl
            add(key, e > 0, e)

        # Pérdida Hansen dentro de la plantación del año anterior
        hrow = np.clip(np.floor((H_TR.f - lat) / H_TR.e * -1).astype(np.int64), 0, HANSEN["lossyear"][0].shape[0] - 1)
        ly = HANSEN["lossyear"][0][hrow[:, None], H_COL[None, :]]
        Pprev = np.isin(read_mb(prev_year, r0, r1), PLANT)
        add("loss_plant", Pprev & (ly == year - 2000), px_km2 * 100.0)  # ha

        if year == YEARS[0]:
            tc = HANSEN["treecover2000"][0][hrow[:, None], H_COL[None, :]].astype(np.float64)
            add("tc_mosaic_sum", A, tc)
            add("mosaic_n", A)

        # Máscara de plantación reducida a ~90 m para la distancia
        pad = np.zeros((((r1 - r0) + 2) // 3 * 3, (COLS + 2) // 3 * 3), bool)
        pad[: r1 - r0, :COLS] = P
        small[r0 // 3: r0 // 3 + pad.shape[0] // 3] |= pad.reshape(pad.shape[0] // 3, 3, -1, 3).any(axis=(1, 3))

    # Distancia (m) desde cada píxel de 90 m a la plantación más cercana
    lat_mid = (LAT0 + LAT1) / 2
    dist = ndimage.distance_transform_edt(~small, sampling=(3 * DY, 3 * dx_at(lat_mid))).astype(np.float32)
    np.save(f"{OUT}/_tmp_dist_{year}.npy", dist)
    np.savez_compressed(f"{OUT}/_tmp_acc_{year}.npz", **{k: v.astype(np.float32) for k, v in acc.items()})
    print("listo", year, flush=True)
    return year


def cell_centroids():
    gr, gc = np.meshgrid(np.arange(GR0, GR1), np.arange(GC0, GC1), indexing="ij")
    y = Y0 - (gr + 0.5) * CELL
    x = X0 + (gc + 0.5) * CELL
    lat = np.degrees(y / R)
    lon = np.degrees(x / (R * np.cos(np.radians(lat))))
    return gr.ravel(), gc.ravel(), lat.ravel(), lon.ravel()


def sample_dem(lat, lon):
    srcs = [rasterio.open(f) for f in glob.glob(f"{DATA}/dem/*.tif")]
    arr, tr = merge(srcs, bounds=(LON0 - 0.05, LAT1 - 0.05, LON1 + 0.05, LAT0 + 0.05), nodata=-9999)
    arr = arr[0]
    r = np.clip(((tr.f - lat) / -tr.e).astype(int), 0, arr.shape[0] - 1)
    c = np.clip(((lon - tr.c) / tr.a).astype(int), 0, arr.shape[1] - 1)
    z = arr[r, c].astype(np.float32)
    z[z <= -9999] = np.nan
    return z


def main():
    os.makedirs(OUT, exist_ok=True)
    todo = [y for y in YEARS if not os.path.exists(f"{OUT}/_tmp_acc_{y}.npz")]
    with Pool(int(os.environ.get("NPROC", 3))) as pool:
        pool.map(year_stats, todo)

    gr, gc, lat, lon = cell_centroids()
    acc0 = np.load(f"{OUT}/_tmp_acc_{YEARS[-1]}.npz")
    keep = acc0["valid"] >= 50  # celdas con al menos ~20 % de datos válidos dentro de Ecuador
    elev = sample_dem(lat, lon)

    # Región: Sierra = centroide >= 1000 m; Costa / Amazonía según el lado de la cordillera
    region = np.full(NCELL, "", object)
    grid_keep = keep.reshape(NR, NC)
    andes = (elev >= 1000).reshape(NR, NC) & grid_keep
    lon2 = lon.reshape(NR, NC)
    reg2 = np.where(andes, "Sierra", "").astype(object)
    for i in range(NR):
        if andes[i].any():
            mid = np.median(lon2[i][andes[i]])
        else:
            mid = -78.5
        row_low = grid_keep[i] & ~andes[i]
        reg2[i][row_low & (lon2[i] < mid)] = "Costa"
        reg2[i][row_low & (lon2[i] >= mid)] = "Amazonia"
    region = reg2.ravel()

    # Distancia y vecindario por año
    dlat, dlon = lat, lon
    srow = np.clip(((MB_TOP - dlat) / RES / 3).astype(int), 0, None)
    scol = ((dlon - (MB_LEFT + C0 * RES)) / RES / 3).astype(int)

    h, v = gc // NTILE, gr // NTILE
    static = pd.DataFrame({
        "cell_id": (gr * 86400 + gc).astype(np.int64),
        "modis_h": h.astype(np.int16), "modis_v": v.astype(np.int16),
        "modis_line": (gr % NTILE).astype(np.int16), "modis_sample": (gc % NTILE).astype(np.int16),
        "lon": lon.astype(np.float32), "lat": lat.astype(np.float32),
        "elev_m": elev, "region": region,
    })
    a01 = np.load(f"{OUT}/_tmp_acc_{YEARS[0]}.npz")
    with np.errstate(invalid="ignore", divide="ignore"):
        static["arbol_mosaico_pct2000"] = (a01["tc_mosaic_sum"] / a01["mosaic_n"]).astype(np.float32)
    static["area_valida_km2"] = acc0["area_km2"]

    panels = []
    for y in YEARS:
        a = np.load(f"{OUT}/_tmp_acc_{y}.npz")
        dist = np.load(f"{OUT}/_tmp_dist_{y}.npy")
        rr = np.clip(srow, 0, dist.shape[0] - 1)
        cc = np.clip(scol, 0, dist.shape[1] - 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            V = a["valid"]
            area = a["area_km2"]
            plant_ha = a["plant"] / V * CELL ** 2 / 1e4
            # % de plantación en ventana de 7 x 7 celdas (~3.2 km), ponderado por área válida
            frac = np.nan_to_num(a["plant"] / V)
            num = ndimage.uniform_filter((frac * area).reshape(NR, NC).astype(np.float64), 7, mode="constant")
            den = ndimage.uniform_filter(area.reshape(NR, NC).astype(np.float64), 7, mode="constant")
            df = pd.DataFrame({
                "cell_id": static["cell_id"].values,
                "year": np.int16(y),
                "plant_pct": (100 * a["plant"] / V).astype(np.float32),
                "plant_ha": plant_ha.astype(np.float32),
                "native_pct": (100 * (a["forest"] + a["nonforest"]) / V).astype(np.float32),
                "forest_nat_pct": (100 * a["forest"] / V).astype(np.float32),
                "nonforest_nat_pct": (100 * a["nonforest"] / V).astype(np.float32),
                "agri_pct": (100 * a["agri"] / V).astype(np.float32),
                "urban_pct": (100 * a["urban"] / V).astype(np.float32),
                "edge_plant_native_m_km2": (a["edge_nat_m"] / area).astype(np.float32),
                "edge_plant_agri_m_km2": (a["edge_agri_m"] / area).astype(np.float32),
                "dist_plant_m": dist[rr, cc],
                "plant_pct_vec3km": (100 * num / den).ravel().astype(np.float32),
                "plant_loss_ha": a["loss_plant"].astype(np.float32),
            })
        panels.append(df[keep])
    panel = pd.concat(panels, ignore_index=True)
    panel = panel.sort_values(["cell_id", "year"])
    # Años desde la última pérdida (cosecha o disturbio) dentro de la plantación; NaN si no hubo desde 2001
    lossy = panel["year"].where(panel["plant_loss_ha"] > 0.09)
    last = lossy.groupby(panel["cell_id"]).ffill()
    panel["yrs_since_plant_loss"] = (panel["year"] - last).astype(np.float32)

    static = static[keep].reset_index(drop=True)
    static.to_parquet(f"{OUT}/celdas_estatico.parquet", index=False)
    panel.to_parquet(f"{OUT}/panel_anual.parquet", index=False, compression="zstd")
    print(static.shape, panel.shape)


if __name__ == "__main__":
    main()
