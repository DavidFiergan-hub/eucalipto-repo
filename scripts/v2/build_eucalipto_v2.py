"""Base de eucalipto v2 por celda MODIS 500 m, a partir del mapa propio (02_clasificacion_eucalipto_v2.js).

Entrada (carpeta de Google Drive "eucalipto_v2", bajada completa):
  euc_clase_AAAA*.tif          clases 1 eucalipto, 2 pino, 3 bosque nativo, 4 páramo/arbustal, 5 agro, 6 otros,
                               0 sin dato. Earth Engine puede partir cada año en varios archivos: se leen todos.
  hansen_lossyear_sierra*.tif  año de pérdida de dosel de Hansen (1 = 2001 ... 24 = 2024), misma malla.
Salida (misma estructura que la v1, columnas euc_* en vez de plant_*):
  panel_anual_v2.parquet       una fila por celda y año
Uso:
  python build_eucalipto_v2.py CARPETA_TIF CELDAS_ESTATICO.parquet CARPETA_SALIDA
  (CELDAS_ESTATICO.parquet es el de la v1: data/celdas_estatico.parquet; fija las celdas y su cell_id)
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from scipy import ndimage

# Grilla sinusoidal MODIS (la misma de la v1 y de MCD64A1)
R = 6371007.181
CELL = 463.31271653
X0, Y0 = -20015109.354, 10007554.677

EUC, PINO, BOSQUE, PARAMO, AGRO, OTROS = 1, 2, 3, 4, 5, 6
NATIVA = [BOSQUE, PARAMO]
BLOQUE = 1500          # filas por bloque (múltiplo de 3 para la máscara de distancia)
FACTOR_DIST = 3        # la distancia se calcula a ~83 m (3 píxeles)
MIN_VALIDO = 0.2       # fracción mínima de la celda con dato para conservarla


def sin_rc(lat, lon):
    latr, lonr = np.radians(lat), np.radians(lon)
    x = R * lonr * np.cos(latr)
    y = R * latr
    return np.floor((Y0 - y) / CELL).astype(np.int64), np.floor((x - X0) / CELL).astype(np.int64)


class Mosaico:
    """Lee una ventana cualquiera de un ráster partido en varios archivos de la misma malla."""

    def __init__(self, archivos):
        if not archivos:
            raise FileNotFoundError("no hay archivos")
        self.src = [rasterio.open(f) for f in archivos]
        t = self.src[0].transform
        self.res = t.a
        self.left = min(s.transform.c for s in self.src)
        self.top = max(s.transform.f for s in self.src)
        right = max(s.transform.c + s.width * s.transform.a for s in self.src)
        bottom = min(s.transform.f + s.height * s.transform.e for s in self.src)
        self.width = int(round((right - self.left) / self.res))
        self.height = int(round((self.top - bottom) / self.res))
        self.off = [(int(round((self.top - s.transform.f) / self.res)), int(round((s.transform.c - self.left) / self.res)))
                    for s in self.src]

    def leer(self, r0, r1):
        out = np.zeros((r1 - r0, self.width), np.uint8)
        for s, (ro, co) in zip(self.src, self.off):
            a, b = max(r0, ro), min(r1, ro + s.height)
            if a >= b:
                continue
            out[a - r0:b - r0, co:co + s.width] = s.read(1, window=Window(0, a - ro, s.width, b - a))
        return out

    def misma_malla(self, otro):
        return (abs(self.res - otro.res) < 1e-12 and abs(self.left - otro.left) < self.res / 2
                and abs(self.top - otro.top) < self.res / 2 and self.width == otro.width and self.height == otro.height)


def archivos_por_anio(carpeta):
    out = {}
    for f in sorted(glob.glob(os.path.join(carpeta, "euc_clase_*.tif"))):
        m = re.search(r"euc_clase_(\d{4})", os.path.basename(f))
        out.setdefault(int(m.group(1)), []).append(f)
    return dict(sorted(out.items()))


def main(carpeta, celdas_path, salida):
    os.makedirs(salida, exist_ok=True)
    por_anio = archivos_por_anio(carpeta)
    anios = list(por_anio)
    print("años:", anios, flush=True)
    mos = {a: Mosaico(f) for a, f in por_anio.items()}
    ref = mos[anios[0]]
    for a in anios:
        if not mos[a].misma_malla(ref):
            sys.exit(f"El año {a} no está en la misma malla que {anios[0]}")
    hansen = Mosaico(sorted(glob.glob(os.path.join(carpeta, "hansen_lossyear_sierra*.tif"))))
    if not hansen.misma_malla(ref):
        sys.exit("hansen_lossyear_sierra no está en la misma malla que las clases")

    res, H, W = ref.res, ref.height, ref.width
    lon_px = ref.left + (np.arange(W) + 0.5) * res
    lat_px = ref.top - (np.arange(H) + 0.5) * res
    dy = res * 110574.0

    # Grilla local de celdas MODIS que cubre la malla
    lats = [lat_px[0], lat_px[-1]] + ([0.0] if lat_px[-1] < 0 < lat_px[0] else [])
    la, lo = np.meshgrid(lats, [lon_px[0], lon_px[-1]])
    rr, cc = sin_rc(la.ravel(), lo.ravel())
    GR0, GR1, GC0, GC1 = rr.min() - 1, rr.max() + 2, cc.min() - 1, cc.max() + 2
    NR, NC = GR1 - GR0, GC1 - GC0
    NCELL = NR * NC

    claves = ["valido", "area_km2", "euc", "pino", "bosque", "paramo", "agro", "otros",
              "borde_nat_m", "borde_agri_m", "tala_euc_ha"]
    acum, distancias = {}, {}
    for i, a in enumerate(anios):
        acc = {k: np.zeros(NCELL) for k in claves}
        chico = np.zeros(((H + FACTOR_DIST - 1) // FACTOR_DIST, (W + FACTOR_DIST - 1) // FACTOR_DIST), bool)
        previo = mos[anios[i - 1]] if i > 0 else mos[a]
        for r0 in range(0, H, BLOQUE):
            r1 = min(r0 + BLOQUE, H)
            ext = min(r1 + 1, H)
            c_ext = mos[a].leer(r0, ext)
            c = c_ext[: r1 - r0]
            if not c.any():
                continue
            lat = lat_px[r0:r1]
            grow, gcol = sin_rc(lat[:, None], lon_px[None, :])
            ids = ((grow - GR0) * NC + (gcol - GC0)).ravel()
            px_km2 = np.repeat((res * 111320.0 * np.cos(np.radians(lat)) * dy / 1e6)[:, None], W, axis=1)

            def suma(clave, mascara, peso=None):
                m = mascara.ravel()
                acc[clave] += np.bincount(ids[m], weights=None if peso is None else peso.ravel()[m], minlength=NCELL)

            valido = c > 0
            suma("valido", valido)
            suma("area_km2", valido, px_km2)
            for k, v in [("euc", EUC), ("pino", PINO), ("bosque", BOSQUE), ("paramo", PARAMO), ("agro", AGRO),
                         ("otros", OTROS)]:
                suma(k, c == v)

            # Bordes eucalipto-nativa y eucalipto-agro: lados compartidos en 4-vecindad (m)
            E, Ee = c == EUC, c_ext == EUC
            n_v = min(r1 - r0, c_ext.shape[0] - 1)
            dx = (res * 111320.0 * np.cos(np.radians(lat[:n_v])))[:, None]
            for clases, clave in [(NATIVA, "borde_nat_m"), ([AGRO], "borde_agri_m")]:
                Oe = np.isin(c_ext, clases)
                O = Oe[: r1 - r0]
                e = np.zeros(c.shape)
                e[:, :-1] += ((E[:, :-1] & O[:, 1:]) | (O[:, :-1] & E[:, 1:])) * dy
                e[:n_v] += ((Ee[:n_v] & Oe[1:n_v + 1]) | (Oe[:n_v] & Ee[1:n_v + 1])) * dx
                suma(clave, e > 0, e)

            # Tala o cosecha: pérdida Hansen del año dentro del eucalipto del año anterior
            if 2001 <= a <= 2000 + 24:
                h = hansen.leer(r0, r1)
                suma("tala_euc_ha", (previo.leer(r0, r1) == EUC) & (h == a - 2000), px_km2 * 100.0)

            # Máscara de eucalipto reducida para la distancia
            f = FACTOR_DIST
            pad = np.zeros(((r1 - r0 + f - 1) // f * f, chico.shape[1] * f), bool)
            pad[: r1 - r0, :W] = E
            chico[r0 // f: r0 // f + pad.shape[0] // f] |= pad.reshape(pad.shape[0] // f, f, -1, f).any(axis=(1, 3))

        lat_mid = (lat_px[0] + lat_px[-1]) / 2
        sampling = (FACTOR_DIST * dy, FACTOR_DIST * res * 111320.0 * np.cos(np.radians(lat_mid)))
        distancias[a] = ndimage.distance_transform_edt(~chico, sampling=sampling).astype(np.float32) if chico.any() \
            else np.full(chico.shape, np.inf, np.float32)
        acum[a] = acc
        print("listo", a, flush=True)

    # Celdas de la v1 dentro de la malla
    cel = pd.read_parquet(celdas_path, columns=["cell_id", "lon", "lat", "region"])
    g_r, g_c = cel.cell_id.values // 86400, cel.cell_id.values % 86400
    dentro = (g_r >= GR0) & (g_r < GR1) & (g_c >= GC0) & (g_c < GC1)
    cel = cel[dentro].reset_index(drop=True)
    idx = (g_r[dentro] - GR0) * NC + (g_c[dentro] - GC0)
    srow = np.clip(((ref.top - cel.lat.values) / res / FACTOR_DIST).astype(int), 0, None)
    scol = np.clip(((cel.lon.values - ref.left) / res / FACTOR_DIST).astype(int), 0, None)
    px_celda = (CELL ** 2) / (dy * res * 111320.0 * np.cos(np.radians(cel.lat.values)))

    paneles = []
    for a in anios:
        x, d = acum[a], distancias[a]
        V = x["valido"]
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.nan_to_num(x["euc"] / V)
            area = x["area_km2"]
            num = ndimage.uniform_filter((frac * area).reshape(NR, NC), 7, mode="constant").ravel()
            den = ndimage.uniform_filter(area.reshape(NR, NC), 7, mode="constant").ravel()
            pct = lambda k: (100 * x[k][idx] / V[idx]).astype(np.float32)
            df = pd.DataFrame({
                "cell_id": cel.cell_id.values,
                "year": np.int16(a),
                "euc_pct": pct("euc"),
                "euc_ha": (x["euc"][idx] / V[idx] * CELL ** 2 / 1e4).astype(np.float32),
                "pino_pct": pct("pino"),
                "plant_pct_v2": ((x["euc"][idx] + x["pino"][idx]) * 100 / V[idx]).astype(np.float32),
                "forest_nat_pct": pct("bosque"),
                "nonforest_nat_pct": pct("paramo"),
                "native_pct": ((x["bosque"][idx] + x["paramo"][idx]) * 100 / V[idx]).astype(np.float32),
                "agri_pct": pct("agro"),
                "otros_pct": pct("otros"),
                "edge_euc_native_m_km2": (x["borde_nat_m"][idx] / area[idx]).astype(np.float32),
                "edge_euc_agri_m_km2": (x["borde_agri_m"][idx] / area[idx]).astype(np.float32),
                "dist_euc_m": d[np.clip(srow, 0, d.shape[0] - 1), np.clip(scol, 0, d.shape[1] - 1)],
                "euc_pct_vec3km": np.clip(100 * num / den, 0, 100)[idx].astype(np.float32),
                "euc_loss_ha": x["tala_euc_ha"][idx].astype(np.float32),
                "frac_valida": (V[idx] / px_celda).astype(np.float32),
            })
        paneles.append(df[df.frac_valida >= MIN_VALIDO])
    panel = pd.concat(paneles, ignore_index=True).sort_values(["cell_id", "year"])
    tala = panel["year"].where(panel["euc_loss_ha"] > 0.09)
    panel["yrs_since_euc_loss"] = (panel["year"] - tala.groupby(panel["cell_id"]).ffill()).astype(np.float32)
    panel["dist_euc_m"] = panel["dist_euc_m"].replace(np.inf, np.nan)
    panel.to_parquet(os.path.join(salida, "panel_anual_v2.parquet"), index=False, compression="zstd")

    # Resumen para control de calidad (Sierra)
    sierra = panel.merge(cel[["cell_id", "region"]], on="cell_id")
    sierra = sierra[sierra.region == "Sierra"]
    res_ = sierra.groupby("year").agg(celdas=("cell_id", "size"), euc_ha=("euc_ha", "sum"),
                                      pino_pct_medio=("pino_pct", "mean"), frac_valida_media=("frac_valida", "mean"))
    res_.to_csv(os.path.join(salida, "resumen_sierra_v2.csv"))
    print(res_)
    print(panel.shape)


if __name__ == "__main__":
    main(*sys.argv[1:4])
