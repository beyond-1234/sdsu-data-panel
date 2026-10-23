"""Build the static data bundle for the GitHub Pages portal.

Reads the archived source files under ``data/Microbe Data`` and regenerates
``docs/assets/js/data.js`` with dataset metadata, search facets, and real
visualization payloads. Run from the repository root:

    .venv/bin/python docs/tools/build_data.py
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DATA_DIR = ROOT / "data" / "Microbe Data"
DATA_JS = DOCS / "assets" / "js" / "data.js"

RAW_BASE = "https://raw.githubusercontent.com/beyond-1234/sdsu-data-panel/gh-pages/"

VEG_NAMES = {
    101: "Boreal Forest",
    102: "Temperate Coniferous Forest",
    103: "Temperate Broadleaf Forest",
    104: "Tropical Forest",
    105: "Mixed Forest",
    106: "Grassland",
    107: "Shrubland",
    108: "Tundra",
    109: "Desert",
    110: "Wetland",
    111: "Cropland",
    112: "Pasture",
}

NEW_VARIABLES = [
    {
        "id": 17,
        "code": "DON",
        "display_name": "Dissolved Organic Nitrogen",
        "display_name_en": "Dissolved Organic Nitrogen",
        "category": "Soil Physics",
        "unit": "mg g-1",
        "description": "Dissolved organic nitrogen extracted from soil solution",
    },
    {
        "id": 18,
        "code": "POC",
        "display_name": "Particulate Organic Carbon",
        "display_name_en": "Particulate Organic Carbon",
        "category": "Soil Physics",
        "unit": "g kg-1",
        "description": "Soil particulate organic carbon in the 53-2000 um fraction",
    },
    {
        "id": 19,
        "code": "IPOC",
        "display_name": "iPOC Fraction",
        "display_name_en": "iPOC Fraction",
        "category": "Soil Physics",
        "unit": "g kg-1",
        "description": "iPOC fraction of particulate organic carbon (53-2000 um)",
    },
    {
        "id": 20,
        "code": "HPOC",
        "display_name": "hPOC Fraction",
        "display_name_en": "hPOC Fraction",
        "category": "Soil Physics",
        "unit": "g kg-1",
        "description": "hPOC fraction of particulate organic carbon (53-2000 um)",
    },
    {
        "id": 21,
        "code": "TOC",
        "display_name": "Total Organic Carbon",
        "display_name_en": "Total Organic Carbon",
        "category": "Soil Physics",
        "unit": "g kg-1",
        "description": "Total soil organic carbon concentration",
    },
    {
        "id": 22,
        "code": "VEG",
        "display_name": "Vegetation / Biome Class",
        "display_name_en": "Vegetation / Biome Class",
        "category": "Soil Physics",
        "unit": "class",
        "description": "Vegetation or biome class code carried by the gridded files",
    },
]

NEW_PRIMARY_KEYWORDS = [
    "soil_doc",
    "dissolved_organic_carbon",
    "soil_poc",
    "particulate_organic_carbon",
    "soil_carbon_fractions",
    "gridded_simulation",
]

NEW_EXTRA_KEYWORDS = [
    "doc",
    "poc",
    "soil_carbon",
    "depth_profile",
    "global_synthesis",
    "vegetation_class",
    "biome_class",
    "global_grid",
]


# --------------------------------------------------------------------- utils


def read_nc(path: Path, specs: dict[str, tuple[int, int, str]]) -> dict[str, np.ndarray]:
    arrays = {}
    with open(path, "rb") as handle:
        for name, (offset, count, dtype) in specs.items():
            handle.seek(offset)
            raw = handle.read(count * np.dtype(dtype).itemsize)
            arrays[name] = np.frombuffer(raw, dtype=dtype).copy()
    return arrays


def human_size(path: Path) -> str:
    size = os.path.getsize(path)
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.0f} KB"


def raw_url(rel_path: str) -> str:
    return RAW_BASE + quote(rel_path)


def file_entry(rel_path: str, label: str | None = None) -> dict:
    path = ROOT / rel_path
    return {
        "name": path.name,
        "label": label or path.name,
        "path": rel_path,
        "size": human_size(path),
        "url": raw_url(rel_path),
    }


def value_or_none(value, digits: int = 3):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def mean_or_none(series: pd.Series, digits: int = 3):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return value_or_none(clean.mean(), digits)


def normalize_biome(raw) -> str:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return "Unclassified"
    text = re.sub(r"\s+", " ", str(raw).replace("\u00a0", " ")).strip()
    low = text.lower()
    if "broad" in low:
        return "Temperate Broadleaf Forest"
    if "neadle" in low or "needle" in low:
        return "Temperate Needleleaf Forest"
    if "tropical" in low and "forest" in low:
        return "Tropical Forest"
    if "subtropical" in low and "forest" in low:
        return "Subtropical Forest"
    if low in {"savana", "savanna"}:
        return "Savanna"
    if low.startswith("pasture"):
        return "Pasture"
    if low == "paddy":
        return "Paddy"
    if low == "upland":
        return "Upland"
    if low == "peatland":
        return "Peatland"
    if low == "mixed forest":
        return "Mixed Forest"
    if low == "temperate forest":
        return "Temperate Forest"
    return text[:48]


def lat_label(latitude: float) -> str:
    if latitude >= 0:
        return f"{latitude:.1f}\u00b0N"
    return f"{abs(latitude):.1f}\u00b0S"


def zonal_means(lats: np.ndarray, grid: np.ndarray, step: int = 5, positive: bool = False):
    rows = []
    for start in range(0, 360, step):
        block = grid[start:start + step, :]
        mask = np.isfinite(block)
        if positive:
            mask &= block > 0
        else:
            mask &= block > -999
        if not mask.any():
            continue
        latitude = float(np.mean(lats[start:start + step]))
        rows.append((latitude, float(np.mean(block[mask]))))
    rows.sort(key=lambda item: item[0])
    labels = [lat_label(lat) for lat, _ in rows]
    values = [value_or_none(value, 2) for _, value in rows]
    return labels, values


def binned_curve(x: np.ndarray, y: np.ndarray, mask: np.ndarray, upper: float, bins: int):
    edges = np.linspace(0, upper, bins + 1)
    xs, ys = [], []
    for index in range(len(edges) - 1):
        low, high = edges[index], edges[index + 1]
        selected = mask & (x >= low) & (x < high)
        if selected.sum() < 10:
            continue
        xs.append(round(float((low + high) / 2), 1))
        ys.append(value_or_none(np.mean(y[selected]), 2))
    return xs, ys


# --------------------------------------------------------------- DOC observations


def build_doc_observations() -> dict:
    frame = pd.read_csv(DATA_DIR / "DOC" / "Soil_DOC.csv", encoding="utf-8-sig").copy()

    frame["biome"] = frame["F Biome"].map(normalize_biome)
    numeric = {
        "DOC": " F DOC mg/g",
        "TOC": "TOC(g/kg)",
        "TN": "TN g/kg",
        "PH": "pH(H2O)",
        "MAT": "MAT(\u2103)",
        "MAP": "MAP(mm)",
        "Depth": "F Depth cm",
        "Date": "Date ",
        "Lat": "LATITUDE ",
        "Lon": "LONGITUDE",
    }
    for target, source in numeric.items():
        frame[target] = pd.to_numeric(frame.get(source), errors="coerce")

    grouped = (
        frame.groupby("biome")
        .agg(n=("DOC", "size"), DOC=("DOC", "mean"), TOC=("TOC", "mean"), TN=("TN", "mean"))
        .query("n >= 20")
        .sort_values("DOC", ascending=False)
    )

    biomes = grouped.index.tolist()
    depth_bins = [(0, 10), (10, 30), (30, 60), (60, 100), (100, 200), (200, 10_000)]
    depth_labels = ["0-10cm", "10-30cm", "30-60cm", "60-100cm", "100-200cm", ">200cm"]
    depth_doc = []
    for low, high in depth_bins:
        subset = frame[(frame["Depth"] >= low) & (frame["Depth"] < high)]
        depth_doc.append(mean_or_none(subset["DOC"], 3) or 0)

    kin_x, kin_y = [], []
    edges = np.linspace(0, 200, 31)
    for index in range(len(edges) - 1):
        low, high = edges[index], edges[index + 1]
        subset = frame[(frame["TOC"] >= low) & (frame["TOC"] < high)]
        if len(subset) < 5 or subset["DOC"].notna().sum() == 0:
            continue
        kin_x.append(round(float((low + high) / 2), 1))
        kin_y.append(value_or_none(subset["DOC"].mean(), 3))

    sample = frame.dropna(subset=["DOC"])
    preview = sample.sample(n=min(15, len(sample)), random_state=42)
    preview = preview[["Country", "biome", "Lat", "Lon", "Depth", "DOC", "TOC", "TN", "PH"]]
    records = []
    for row in preview.to_dict(orient="records"):
        records.append(
            {
                "Country": str(row["Country"]).strip(),
                "Biome": row["biome"],
                "Latitude": value_or_none(row["Lat"], 2),
                "Longitude": value_or_none(row["Lon"], 2),
                "Depth (cm)": value_or_none(row["Depth"], 1),
                "DOC (mg g-1)": value_or_none(row["DOC"], 4),
                "TOC (g kg-1)": value_or_none(row["TOC"], 2),
                "TN (g kg-1)": value_or_none(row["TN"], 2),
                "pH": value_or_none(row["PH"], 2),
            }
        )

    date_min = int(math.floor(frame["Date"].min()))
    date_max = int(math.floor(frame["Date"].max()))
    country_count = int(frame["Country"].nunique())
    rel_path = "data/Microbe Data/DOC/Soil_DOC.csv"
    entry = file_entry(rel_path, "Observations CSV")

    meta = {
        "id": 3,
        "title": "Global Soil Dissolved Organic Carbon Field Observations (0-825 cm)",
        "author": "Xiaofeng Xu, Ziyu Guo, Yihui Wang, Zhongmei Wang, et al. (SDSU)",
        "year": 2021,
        "doi": "10.5061/dryad.73n5tb2v6",
        "description": (
            "Physical file: Soil_DOC.csv archived in data/Microbe Data/DOC (converted from the "
            "original Soil_DOC.xlsx workbook). Compiles 3,998 "
            f"field observations from {country_count} countries across the 0-825 cm soil profile, "
            "covering dissolved organic carbon (DOC), total organic carbon (TOC), total nitrogen "
            "(TN), pH, MAT and MAP. The workbook also contains the 0-100 cm and >100 cm depth "
            "worksheets used to build the global DOC synthesis. References: Guo et al. (2020 GEB) "
            "and Xu et al. (2021 Dryad)."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Ecosystems (DOC synthesis)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": f"{date_min}-01-01",
        "end_date": f"{date_max}-12-31",
        "temporal_resolution": "Snapshot",
        "data_type": "Field Observation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 8.25,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": rel_path,
        "files": [entry],
        "keywords": [
            "soil_doc",
            "dissolved_organic_carbon",
            "doc",
            "soil_carbon",
            "depth_profile",
            "global_synthesis",
        ],
        "variables": ["DOC", "TOC", "TN", "PH", "MAT", "MAP"],
    }

    vis = {
        "data_type": "csv",
        "chart_title": "Global Biome Dissolved Organic Carbon, TOC & TN Observations",
        "chart_subtitle": (
            f"Mean values aggregated from 3,998 field observations across {country_count} countries "
            "and the 0-825 cm soil profile"
        ),
        "x_labels": biomes,
        "x_axis_name": "Global Biomes",
        "series1_name": "DOC (mg g-1)",
        "series1_data": [value_or_none(grouped.loc[b, "DOC"], 3) for b in biomes],
        "series2_name": "TOC (g kg-1)",
        "series2_data": [value_or_none(grouped.loc[b, "TOC"], 2) for b in biomes],
        "series3_name": "TN (g kg-1)",
        "series3_data": [value_or_none(grouped.loc[b, "TN"], 2) for b in biomes],
        "y_axis_name": "DOC (mg g-1)",
        "y_axis_name2": "TOC / TN (g kg-1)",
        "series1_axis": 0,
        "series2_axis": 1,
        "series3_axis": 1,
        "depth_title": "Soil DOC Depth Gradient (0-825 cm)",
        "depth_subtitle": "Mean dissolved organic carbon across measured depth horizons",
        "depth_labels": depth_labels,
        "depth_series": [
            {"name": "DOC (mg g-1)", "data": depth_doc, "color": "#2e7d32"},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "TOC (g kg-1)",
        "kin_y_label": "DOC (mg g-1)",
        "kin_title": "TOC vs. DOC Empirical Scaling",
        "kin_subtitle": "Binned field observations linking bulk organic carbon to dissolved organic carbon",
        "columns": [
            "Country",
            "Biome",
            "Latitude",
            "Longitude",
            "Depth (cm)",
            "DOC (mg g-1)",
            "TOC (g kg-1)",
            "TN (g kg-1)",
            "pH",
        ],
        "records": records,
        "total_count": "3,998 empirical sampling records across 33 countries",
    }
    meta["vis_data"] = vis
    return meta


# --------------------------------------------------------------- POC observations


def build_poc_observations() -> dict:
    frames = []
    for filename, profile in [("POC_0-30.csv", "0-30cm"), ("POC_0_100.csv", "0-100cm")]:
        frame = pd.read_csv(DATA_DIR / "POC" / filename, encoding="utf-8")
        frame["profile"] = profile
        frames.append(frame)
    frame = pd.concat(frames, ignore_index=True)

    frame["biome"] = frame["Biome S"].map(normalize_biome)
    numeric = {
        "IPOC": "iPOC Total(g/kg_53-2000)",
        "HPOC": "hPOC Total(g/kg_53-2000)",
        "TOC": "TOC g/kg",
        "TN": "TN g/kg F",
        "PH": "pH",
        "MAT": "MAT (deg C)",
        "MAP": "MAP (mm)",
        "Depth": "Depth F",
        "Date": "Date F",
        "Lat": "Lat F",
        "Lon": "Long F",
    }
    for target, source in numeric.items():
        frame[target] = pd.to_numeric(frame.get(source), errors="coerce")

    grouped = (
        frame.groupby("biome")
        .agg(n=("IPOC", "size"), IPOC=("IPOC", "mean"), HPOC=("HPOC", "mean"), TOC=("TOC", "mean"))
        .query("n >= 15")
        .sort_values("IPOC", ascending=False)
    )
    biomes = grouped.index.tolist()

    depth_bins = [(0, 5), (5, 10), (10, 20), (20, 30), (30, 50), (50, 100)]
    depth_labels = ["0-5cm", "5-10cm", "10-20cm", "20-30cm", "30-50cm", "50-100cm"]
    depth_ipoc, depth_hpoc = [], []
    for low, high in depth_bins:
        subset = frame[(frame["Depth"] > low) & (frame["Depth"] <= high)]
        depth_ipoc.append(mean_or_none(subset["IPOC"], 3) or 0)
        depth_hpoc.append(mean_or_none(subset["HPOC"], 3) or 0)

    kin_x, kin_y = [], []
    edges = np.linspace(0, 200, 31)
    for index in range(len(edges) - 1):
        low, high = edges[index], edges[index + 1]
        subset = frame[(frame["TOC"] >= low) & (frame["TOC"] < high)]
        if len(subset) < 5 or subset["IPOC"].notna().sum() == 0:
            continue
        kin_x.append(round(float((low + high) / 2), 1))
        kin_y.append(value_or_none(subset["IPOC"].mean(), 3))

    preview = frame.dropna(subset=["IPOC"]).sample(n=min(15, int(frame["IPOC"].notna().sum())), random_state=11)
    preview = preview[["Country", "biome", "Lat", "Lon", "Depth", "IPOC", "HPOC", "TOC", "PH"]]
    records = []
    for row in preview.to_dict(orient="records"):
        records.append(
            {
                "Country": str(row["Country"]).strip(),
                "Biome": row["biome"],
                "Latitude": value_or_none(row["Lat"], 2),
                "Longitude": value_or_none(row["Lon"], 2),
                "Depth (cm)": value_or_none(row["Depth"], 1),
                "iPOC (g kg-1)": value_or_none(row["IPOC"], 2),
                "hPOC (g kg-1)": value_or_none(row["HPOC"], 2),
                "TOC (g kg-1)": value_or_none(row["TOC"], 2),
                "pH": value_or_none(row["PH"], 2),
            }
        )

    date_min = int(math.floor(frame["Date"].min()))
    date_max = int(math.floor(frame["Date"].max()))
    country_count = int(frame["Country"].nunique())
    files = [
        file_entry("data/Microbe Data/POC/POC_0-30.csv", "0-30 cm CSV"),
        file_entry("data/Microbe Data/POC/POC_0_100.csv", "0-100 cm CSV"),
    ]

    meta = {
        "id": 5,
        "title": "Global Soil Particulate Organic Carbon Field Observations (0-30 cm and 0-100 cm)",
        "author": "Ziyu Guo, Xiaofeng Xu, et al. (SDSU)",
        "year": 2025,
        "doi": "10.1111/gcb.17619",
        "description": (
            "Physical files: POC_0-30.csv and POC_0_100.csv archived in data/Microbe Data/POC. "
            f"Combines 3,510 field observations from {country_count} countries across the 0-30 cm "
            "and 0-100 cm soil layers, covering iPOC, hPOC, TOC, TN, pH, MAT and MAP. Reference: "
            "Guo et al. (2025) Dominant Edaphic Controls on Particulate Organic Carbon in Global "
            "Soils, Global Change Biology."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Ecosystems (POC synthesis)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": f"{date_min}-01-01",
        "end_date": f"{date_max}-12-31",
        "temporal_resolution": "Snapshot",
        "data_type": "Field Observation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 1.0,
        "data_source_type": "github",
        "github_url": files[0]["url"],
        "local_file_path": files[0]["path"],
        "files": files,
        "keywords": [
            "soil_poc",
            "particulate_organic_carbon",
            "poc",
            "soil_carbon_fractions",
            "depth_profile",
            "global_synthesis",
        ],
        "variables": ["POC", "IPOC", "HPOC", "TOC", "TN", "PH", "MAT", "MAP"],
    }

    vis = {
        "data_type": "csv",
        "chart_title": "Global Biome Particulate Organic Carbon Fractions and TOC",
        "chart_subtitle": (
            f"Mean values aggregated from 3,510 field observations across {country_count} countries "
            "and the 0-100 cm soil profile"
        ),
        "x_labels": biomes,
        "x_axis_name": "Global Biomes",
        "series1_name": "iPOC (g kg-1)",
        "series1_data": [value_or_none(grouped.loc[b, "IPOC"], 2) for b in biomes],
        "series2_name": "hPOC (g kg-1)",
        "series2_data": [value_or_none(grouped.loc[b, "HPOC"], 2) for b in biomes],
        "series3_name": "TOC (g kg-1)",
        "series3_data": [value_or_none(grouped.loc[b, "TOC"], 2) for b in biomes],
        "y_axis_name": "iPOC / hPOC (g kg-1)",
        "y_axis_name2": "TOC (g kg-1)",
        "series1_axis": 0,
        "series2_axis": 0,
        "series3_axis": 1,
        "depth_title": "Soil POC Depth Gradient (0-100 cm)",
        "depth_subtitle": "Mean iPOC and hPOC fractions across measured depth horizons",
        "depth_labels": depth_labels,
        "depth_series": [
            {"name": "iPOC (g kg-1)", "data": depth_ipoc, "color": "#2e7d32"},
            {"name": "hPOC (g kg-1)", "data": depth_hpoc, "color": "#1565c0", "dash": True},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "TOC (g kg-1)",
        "kin_y_label": "iPOC (g kg-1)",
        "kin_title": "TOC vs. iPOC Empirical Scaling",
        "kin_subtitle": "Binned field observations linking bulk organic carbon to particulate fractions",
        "columns": [
            "Country",
            "Biome",
            "Latitude",
            "Longitude",
            "Depth (cm)",
            "iPOC (g kg-1)",
            "hPOC (g kg-1)",
            "TOC (g kg-1)",
            "pH",
        ],
        "records": records,
        "total_count": "3,510 empirical sampling records across 36 countries",
    }
    meta["vis_data"] = vis
    return meta


# ---------------------------------------------------------------- DOC gridded


def build_doc_grid() -> dict:
    arrays = read_nc(
        DATA_DIR / "DOC" / "Global_Soil_DOC.nc",
        {
            "lat": (1640, 360, ">f4"),
            "lon": (3080, 720, ">f4"),
            "veg": (5960, 360 * 720, ">i4"),
            "DOC30": (1042760, 360 * 720, ">f4"),
            "DOC100": (2079560, 360 * 720, ">f4"),
        },
    )
    lat = arrays["lat"]
    lon = arrays["lon"]
    doc30 = arrays["DOC30"].reshape(360, 720)
    doc100 = arrays["DOC100"].reshape(360, 720)
    veg = arrays["veg"].reshape(360, 720)

    valid = (doc30 > -999) & np.isfinite(doc30)
    labels, zonal30 = zonal_means(lat, doc30)
    _, zonal100 = zonal_means(lat, doc100)
    mean30 = value_or_none(doc30[valid].mean(), 2)
    mean100 = value_or_none(doc100[valid].mean(), 2)

    kin_x, kin_y = binned_curve(doc30, doc100, valid, 300, 15)

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if valid[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        value30 = float(doc30[row, col])
        value100 = float(doc100[row, col])
        code = int(veg[row, col])
        records.append(
            {
                "Latitude": value_or_none(lat[row], 2),
                "Longitude": value_or_none(lon[col], 2),
                "Vegetation": VEG_NAMES.get(code, f"Class {code}"),
                "DOC 0-30cm (gC m-2)": value_or_none(value30, 2),
                "DOC 0-100cm (gC m-2)": value_or_none(value100, 2),
                "100/30 Ratio": value_or_none(value100 / value30, 2) if value30 > 0 else None,
            }
        )

    rel_path = "data/Microbe Data/DOC/Global_Soil_DOC.nc"
    entry = file_entry(rel_path, "DOC Grid NetCDF")

    meta = {
        "id": 4,
        "title": "Global Soil Dissolved Organic Carbon 0.5-Degree Gridded Dataset",
        "author": "Xiaofeng Xu, Ziyu Guo, Yihui Wang, Zhongmei Wang (SDSU)",
        "year": 2021,
        "doi": "10.1111/geb.13186",
        "description": (
            "Physical file: Global_Soil_DOC.nc archived in data/Microbe Data/DOC. A 0.5-degree "
            f"gridded product (360 x 720) with {int(valid.sum()):,} valid land cells, providing "
            "soil dissolved organic carbon for the top 30 cm and top 100 cm profiles plus 12 "
            "vegetation classes. Reference: Guo et al. (2020) Global budget and distribution of "
            "soil dissolved organic carbon in terrestrial ecosystems, Global Ecology and "
            "Biogeography."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Grid (0.5 degree)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": "2020-01-01",
        "end_date": "2020-12-31",
        "temporal_resolution": "Static Grid",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 1.0,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": rel_path,
        "files": [entry],
        "keywords": [
            "soil_doc",
            "dissolved_organic_carbon",
            "doc",
            "gridded_simulation",
            "global_grid",
            "vegetation_class",
            "soil_carbon",
        ],
        "variables": ["DOC", "VEG"],
    }

    vis = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal Soil Dissolved Organic Carbon Gradient (0.5 Degree Grid)",
        "chart_subtitle": (
            f"Real zonal means across {int(valid.sum()):,} valid land grid cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "DOC 0-30cm (gC m-2)",
        "series1_data": zonal30,
        "series2_name": "DOC 0-100cm (gC m-2)",
        "series2_data": zonal100,
        "series3_name": None,
        "series3_data": None,
        "y_axis_name": "DOC (gC m-2)",
        "depth_title": "Global Mean DOC by Soil Profile Depth",
        "depth_subtitle": "Cumulative DOC storage in the top 30 cm and top 100 cm profiles",
        "depth_labels": ["0-30cm", "0-100cm"],
        "depth_series": [
            {"name": "Mean DOC (gC m-2)", "data": [mean30, mean100], "color": "#2e7d32"},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "DOC 0-30cm (gC m-2)",
        "kin_y_label": "DOC 0-100cm (gC m-2)",
        "kin_title": "Topsoil vs. Deep-Profile DOC Scaling",
        "kin_subtitle": "Binned grid cells linking 0-30 cm DOC to the cumulative 0-100 cm stock",
        "columns": [
            "Latitude",
            "Longitude",
            "Vegetation",
            "DOC 0-30cm (gC m-2)",
            "DOC 0-100cm (gC m-2)",
            "100/30 Ratio",
        ],
        "records": records,
        "total_count": f"{int(valid.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    meta["vis_data"] = vis
    return meta


# ---------------------------------------------------------------- POC gridded


def build_poc_grid() -> dict:
    arrays = read_nc(
        DATA_DIR / "POC" / "POC_Global_Map.nc",
        {
            "lon": (896, 720, ">f8"),
            "lat": (6656, 360, ">f8"),
            "POC30": (9536, 360 * 720, ">f4"),
            "POC100": (1046336, 360 * 720, ">f4"),
            "Biome": (2083136, 360 * 720, ">f4"),
        },
    )
    lat = arrays["lat"]
    lon = arrays["lon"]
    poc30 = arrays["POC30"].reshape(360, 720)
    poc100 = arrays["POC100"].reshape(360, 720)
    biome = arrays["Biome"].reshape(360, 720)

    valid = np.isfinite(poc30) & (poc30 > 0)
    labels, zonal30 = zonal_means(lat, poc30, positive=True)
    _, zonal100 = zonal_means(lat, poc100, positive=True)
    mean30 = value_or_none(poc30[valid].mean(), 2)
    mean100 = value_or_none(poc100[valid].mean(), 2)

    kin_x, kin_y = binned_curve(poc30, poc100, valid, 5000, 20)

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if valid[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        value30 = float(poc30[row, col])
        value100 = float(poc100[row, col])
        code = int(biome[row, col]) if np.isfinite(biome[row, col]) else 0
        records.append(
            {
                "Latitude": value_or_none(lat[row], 2),
                "Longitude": value_or_none(lon[col], 2),
                "Biome": VEG_NAMES.get(code, f"Class {code}"),
                "POC 0-30cm (g m-2)": value_or_none(value30, 1),
                "POC 0-100cm (g m-2)": value_or_none(value100, 1),
                "100/30 Ratio": value_or_none(value100 / value30, 2) if value30 > 0 else None,
            }
        )

    rel_path = "data/Microbe Data/POC/POC_Global_Map.nc"
    entry = file_entry(rel_path, "POC Grid NetCDF")

    meta = {
        "id": 6,
        "title": "Global Soil Particulate Organic Carbon 0.5-Degree Gridded Dataset",
        "author": "Ziyu Guo, Xiaofeng Xu, et al. (SDSU)",
        "year": 2025,
        "doi": "10.1111/gcb.17619",
        "description": (
            "Physical file: POC_Global_Map.nc archived in data/Microbe Data/POC. A 0.5-degree "
            f"gridded product (360 x 720) with {int(valid.sum()):,} valid land cells, providing "
            "particulate organic carbon for the top 30 cm and top 100 cm profiles plus 12 biome "
            "classes. Reference: Guo et al. (2025) Dominant Edaphic Controls on Particulate "
            "Organic Carbon in Global Soils, Global Change Biology."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Grid (0.5 degree)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "temporal_resolution": "Static Grid",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 1.0,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": rel_path,
        "files": [entry],
        "keywords": [
            "soil_poc",
            "particulate_organic_carbon",
            "poc",
            "gridded_simulation",
            "global_grid",
            "biome_class",
            "soil_carbon_fractions",
        ],
        "variables": ["POC", "VEG"],
    }

    vis = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal Soil Particulate Organic Carbon Gradient (0.5 Degree Grid)",
        "chart_subtitle": (
            f"Real zonal means across {int(valid.sum()):,} valid land grid cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "POC 0-30cm (g m-2)",
        "series1_data": zonal30,
        "series2_name": "POC 0-100cm (g m-2)",
        "series2_data": zonal100,
        "series3_name": None,
        "series3_data": None,
        "y_axis_name": "POC (g m-2)",
        "depth_title": "Global Mean POC by Soil Profile Depth",
        "depth_subtitle": "Cumulative POC storage in the top 30 cm and top 100 cm profiles",
        "depth_labels": ["0-30cm", "0-100cm"],
        "depth_series": [
            {"name": "Mean POC (g m-2)", "data": [mean30, mean100], "color": "#2e7d32"},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "POC 0-30cm (g m-2)",
        "kin_y_label": "POC 0-100cm (g m-2)",
        "kin_title": "Topsoil vs. Deep-Profile POC Scaling",
        "kin_subtitle": "Binned grid cells linking 0-30 cm POC to the cumulative 0-100 cm stock",
        "columns": [
            "Latitude",
            "Longitude",
            "Biome",
            "POC 0-30cm (g m-2)",
            "POC 0-100cm (g m-2)",
            "100/30 Ratio",
        ],
        "records": records,
        "total_count": f"{int(valid.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    meta["vis_data"] = vis
    return meta


# ----------------------------------------------------------------------- main


def main() -> None:
    raw = DATA_JS.read_text(encoding="utf-8")
    prefix = "window.PORTAL_DATA = "
    bundle = json.loads(raw[len(prefix):].rstrip().rstrip(";"))

    existing_datasets = [item for item in bundle["datasets"] if item["id"] <= 2]
    existing_keywords = [item for item in bundle["keywords"] if item not in NEW_PRIMARY_KEYWORDS + NEW_EXTRA_KEYWORDS]
    existing_variables = [item for item in bundle["variables"] if item["code"] not in {v["code"] for v in NEW_VARIABLES}]

    new_datasets = [
        build_doc_observations(),
        build_doc_grid(),
        build_poc_observations(),
        build_poc_grid(),
    ]

    bundle["datasets"] = existing_datasets + new_datasets
    bundle["keywords"] = NEW_PRIMARY_KEYWORDS + existing_keywords + NEW_EXTRA_KEYWORDS
    bundle["variables"] = existing_variables + NEW_VARIABLES

    variable_lookup = {variable["code"]: variable for variable in bundle["variables"]}
    for dataset in new_datasets:
        dataset["variables"] = [variable_lookup[code] for code in dataset["variables"]]

    # Keep a single generic global site entry first, then preserve the registry.
    known_sites = {site["site_code"] for site in bundle["sites"]}
    for site_code in ["Global-Terrestrial"]:
        if site_code not in known_sites:
            bundle["sites"].append(
                {
                    "site_code": site_code,
                    "site_name": "Global Terrestrial Ecosystems",
                    "biome": "Global / Multi-Biome",
                }
            )

    output = prefix + json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + ";"
    DATA_JS.write_text(output, encoding="utf-8")

    print(f"Wrote {DATA_JS}")
    print(f"Datasets: {len(bundle['datasets'])} (added {len(new_datasets)})")
    print(f"Keywords: {len(bundle['keywords'])}")
    print(f"Variables: {len(bundle['variables'])}")


if __name__ == "__main__":
    main()
