"""Build the static data bundle for the GitHub Pages portal.

Reads the archived source files under ``data/Microbe Data`` and regenerates
``docs/assets/js/data.js`` with dataset metadata, search facets, and real
visualization payloads. First-party file URLs are stored as repository-relative
paths so a fork resolves them against its own GitHub Pages origin. Run from the
repository root:

    .venv/bin/python docs/tools/build_data.py
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import tifffile

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DATA_DIR = ROOT / "data" / "Microbe Data"
DATA_JS = DOCS / "assets" / "js" / "data.js"
LEGACY_RAW_BASE = "https://raw.githubusercontent.com/beyond-1234/sdsu-data-panel/gh-pages/"

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


def file_entry(rel_path: str, label: str | None = None) -> dict:
    """Return a repository-relative file record.

    The browser resolves the path against the current GitHub Pages fork, so the
    generated bundle does not need to know the owner or repository name.
    """
    path = ROOT / rel_path
    return {
        "name": path.name,
        "label": label or path.name,
        "path": rel_path,
        "size": human_size(path),
        "url": rel_path,
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
    if "confir" in low or "conif" in low:
        return "Temperate Coniferous Forest"
    if "wetland" in low:
        return "Wetland"
    if "bare" in low:
        return "Bare Soil"
    if "urban" in low:
        return "Urban"
    if "glacier" in low:
        return "Glacier"
    if "crop" in low or "paddy" in low:
        return "Cropland"
    if "shrub" in low:
        return "Shrubland"
    if "grass" in low:
        return "Grassland"
    if "desert" in low:
        return "Desert"
    if "boreal" in low:
        return "Boreal Forest"
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
            "Physical file: Soil_DOC.csv archived in data/Microbe Data/DOC. Compiles 3,998 "
            f"field observations from {country_count} countries across the 0-825 cm soil profile, "
            "covering dissolved organic carbon (DOC), total organic carbon (TOC), total nitrogen "
            "(TN), pH, MAT and MAP. The source synthesis also includes 0-100 cm and >100 cm depth "
            "records used to build the global DOC product. References: Guo et al. (2020 GEB) "
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


LATEST_VARIABLES = [
    {
        "id": 23,
        "code": "AOC",
        "display_name": "Aggregate Organic Carbon",
        "display_name_en": "Aggregate Organic Carbon",
        "category": "Soil Physics",
        "unit": "g C m-2",
        "description": "Organic carbon stored in soil aggregates",
    },
    {
        "id": 24,
        "code": "AD",
        "display_name": "Aggregate Distribution",
        "display_name_en": "Aggregate Distribution",
        "category": "Soil Physics",
        "unit": "%",
        "description": "Mass proportion of a soil aggregate size class",
    },
    {
        "id": 25,
        "code": "DOC_TURN",
        "display_name": "DOC Turnover Rate",
        "display_name_en": "DOC Turnover Rate",
        "category": "Soil Physics",
        "unit": "day-1",
        "description": "Predicted turnover rate of dissolved organic carbon",
    },
    {
        "id": 26,
        "code": "FB_RATIO",
        "display_name": "Fungal:Bacterial Ratio",
        "display_name_en": "Fungal:Bacterial Ratio",
        "category": "Microbial Pool",
        "unit": "unitless",
        "description": "Ratio of fungal to bacterial biomass carbon",
    },
    {
        "id": 27,
        "code": "MCR_A",
        "display_name": "mcrA Gene Density",
        "display_name_en": "mcrA Gene Density",
        "category": "Microbial Pool",
        "unit": "copies m-2",
        "description": "Predicted soil mcrA gene density (methanogenesis marker)",
    },
    {
        "id": 28,
        "code": "PMO_A",
        "display_name": "pmoA Gene Density",
        "display_name_en": "pmoA Gene Density",
        "category": "Microbial Pool",
        "unit": "copies m-2",
        "description": "Predicted soil pmoA gene density (methane oxidation marker)",
    },
    {
        "id": 29,
        "code": "MQ",
        "display_name": "Microbial Quotient",
        "display_name_en": "Microbial Quotient",
        "category": "Microbial Pool",
        "unit": "%",
        "description": "Microbial biomass carbon as a percentage of soil organic carbon",
    },
    {
        "id": 30,
        "code": "BR",
        "display_name": "Basal Respiration",
        "display_name_en": "Basal Respiration",
        "category": "Gas Flux",
        "unit": "ug C g-1 h-1",
        "description": "Measured basal soil respiration rate",
    },
    {
        "id": 31,
        "code": "MNL",
        "display_name": "Microbial N Limitation Index",
        "display_name_en": "Microbial N Limitation Index",
        "category": "Microbial Pool",
        "unit": "index",
        "description": "Predicted microbial nitrogen limitation index",
    },
    {
        "id": 32,
        "code": "MPL",
        "display_name": "Microbial P Limitation Index",
        "display_name_en": "Microbial P Limitation Index",
        "category": "Microbial Pool",
        "unit": "index",
        "description": "Predicted microbial phosphorus limitation index",
    },
]

LATEST_KEYWORDS = [
    "soil_aoc",
    "aggregate_organic_carbon",
    "doc_turnover",
    "mcra",
    "pmoa",
    "microbial_n_limitation",
    "microbial_p_limitation",
    "basal_respiration",
    "aggregate_stability",
    "methanogenesis",
    "methane_oxidation",
    "gene_density",
    "nutrient_limitation",
    "carbon_cycling",
]

REBUILD_DATASET_IDS = {7, 8, 9, 10, 11, 12, 13}


def read_h5_grid(path: Path, names: list[str]):
    with h5py.File(path, "r") as handle:
        latitude = handle["latitude"][...]
        longitude = handle["longitude"][...]
        arrays = {name: handle[name][...] for name in names}
    return latitude, longitude, arrays


def zonal_by_latitude(latitude, grid, mask, step: int = 5):
    latitude = np.asarray(latitude)
    bins = np.floor((latitude + 90.0) / step).astype(int)
    rows = []
    for bin_id in np.unique(bins):
        selected = bins == bin_id
        values = np.asarray(grid)[selected, :][mask[selected, :]]
        if values.size == 0:
            continue
        rows.append((float(np.mean(latitude[selected])), float(np.mean(values))))
    rows.sort(key=lambda item: item[0])
    labels = [lat_label(lat) for lat, _ in rows]
    values = [value_or_none(value, 3) for _, value in rows]
    return labels, values


def histogram_share(values, bins, fmt: str = ".3f"):
    counts, edges = np.histogram(values, bins=bins)
    total = int(counts.sum())
    labels = [
        f"{edges[index]:{fmt}}-{edges[index + 1]:{fmt}}"
        for index in range(len(edges) - 1)
    ]
    shares = [round(float(count) / total * 100, 2) if total else 0 for count in counts]
    return labels, shares


def cdf1_variables(path: Path):
    def read_name(handle):
        length = struct.unpack(">I", handle.read(4))[0]
        text = handle.read(length).decode("latin1")
        handle.read((4 - (length % 4)) % 4)
        return text

    def read_values(handle, value_type):
        count = struct.unpack(">I", handle.read(4))[0]
        if value_type == 2:
            text = handle.read(count).decode("latin1")
            handle.read((4 - (count % 4)) % 4)
            return text
        format_code = {1: "b", 3: "h", 4: "i", 5: "f", 6: "d"}[value_type]
        size = {1: 1, 3: 2, 4: 4, 5: 4, 6: 8}[value_type]
        return np.frombuffer(handle.read(size * count), dtype=">" + format_code).copy()

    layout = {}
    with open(path, "rb") as handle:
        handle.read(4)
        struct.unpack(">I", handle.read(4))
        _, dim_count = struct.unpack(">II", handle.read(8))
        dims = []
        for _ in range(dim_count):
            dims.append((read_name(handle), struct.unpack(">I", handle.read(4))[0]))
        _, attr_count = struct.unpack(">II", handle.read(8))
        for _ in range(attr_count):
            read_name(handle)
            read_values(handle, struct.unpack(">I", handle.read(4))[0])
        _, var_count = struct.unpack(">II", handle.read(8))
        for _ in range(var_count):
            name = read_name(handle)
            dim_ids_count = struct.unpack(">I", handle.read(4))[0]
            dim_ids = [struct.unpack(">I", handle.read(4))[0] for _ in range(dim_ids_count)]
            _, var_attr_count = struct.unpack(">II", handle.read(8))
            for _ in range(var_attr_count):
                read_name(handle)
                read_values(handle, struct.unpack(">I", handle.read(4))[0])
            value_type, _, begin = struct.unpack(">III", handle.read(12))
            shape = tuple(dims[index][1] for index in dim_ids)
            dtype = {4: ">i4", 5: ">f4", 6: ">f8"}.get(value_type)
            if dtype:
                layout[name] = (begin, shape, dtype)

    arrays = {}
    with open(path, "rb") as handle:
        for name, (begin, shape, dtype) in layout.items():
            count = int(np.prod(shape))
            handle.seek(begin)
            arrays[name] = np.frombuffer(
                handle.read(count * np.dtype(dtype).itemsize), dtype=dtype
            ).copy().reshape(shape)
    return arrays


def read_geotiff(path: Path):
    with tifffile.TiffFile(path) as tiff:
        page = tiff.pages[0]
        array = page.asarray()
        scale = page.tags["ModelPixelScaleTag"].value
        tiepoint = page.tags["ModelTiepointTag"].value
    x_res, y_res = float(scale[0]), float(scale[1])
    lon_top_left, lat_top_left = float(tiepoint[3]), float(tiepoint[4])
    latitudes = lat_top_left - (np.arange(array.shape[0]) + 0.5) * y_res
    longitudes = lon_top_left + (np.arange(array.shape[1]) + 0.5) * x_res
    return array, latitudes, longitudes


def build_aoc_grid() -> dict:
    path = DATA_DIR / "AOC" / "Global_AOC.nc"
    latitude, longitude, arrays = read_h5_grid(
        path,
        ["AOC_total", "AOCS_H_2_pred", "AOCS_H_25p_pred", "AOCS_H_25m_pred", "AOCS_H_53"],
    )
    total = arrays["AOC_total"]
    macro = arrays["AOCS_H_2_pred"]
    micro = arrays["AOCS_H_25p_pred"]
    fine_mid = arrays["AOCS_H_25m_pred"]
    fine = arrays["AOCS_H_53"]
    mask = np.isfinite(total) & (total > -9998)

    labels, zonal_total = zonal_by_latitude(latitude, total, mask)
    _, zonal_macro = zonal_by_latitude(latitude, macro, mask)
    _, zonal_micro = zonal_by_latitude(latitude, micro, mask)

    mean_total = value_or_none(total[mask].mean(), 1)
    mean_macro = value_or_none(macro[mask].mean(), 1)
    mean_micro = value_or_none(micro[mask].mean(), 1)
    mean_fine_mid = value_or_none(fine_mid[mask].mean(), 1)
    mean_fine = value_or_none(fine[mask].mean(), 1)

    kin_x, kin_y = [], []
    edges = np.linspace(float(total[mask].min()), float(np.percentile(total[mask], 99.5)), 12)
    for index in range(len(edges) - 1):
        selected = mask & (total >= edges[index]) & (total < edges[index + 1])
        if selected.sum() > 10:
            kin_x.append(round(float((edges[index] + edges[index + 1]) / 2), 0))
            kin_y.append(round(float(macro[selected].mean()), 1))

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if mask[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        records.append(
            {
                "Latitude": value_or_none(latitude[row], 2),
                "Longitude": value_or_none(longitude[col], 2),
                "AOC total (g C m-2)": value_or_none(total[row, col], 1),
                ">2 mm (g C m-2)": value_or_none(macro[row, col], 1),
                "0.25-2 mm (g C m-2)": value_or_none(micro[row, col], 1),
                "<0.053 mm (g C m-2)": value_or_none(fine[row, col], 1),
            }
        )

    entry = file_entry("data/Microbe Data/AOC/Global_AOC.nc", "AOC Grid NetCDF")
    meta = {
        "id": 7,
        "title": "Global Soil Aggregate Organic Carbon Components (0.5-Degree Grid)",
        "author": "Ziyu Guo, Xiaofeng Xu, et al. (SDSU)",
        "year": 2026,
        "doi": "",
        "description": (
            "Physical file: Global_AOC.nc archived in data/Microbe Data/AOC. A 0.5-degree "
            f"gridded product (360 x 720) with {int(mask.sum()):,} valid land cells, providing "
            "total aggregate organic carbon and four aggregate-size fractions (>2 mm, "
            "0.25-2 mm, 0.053-0.25 mm and <0.053 mm), together with aggregate distribution "
            "percentages."
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
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "temporal_resolution": "Static Grid",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 0.3,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": entry["path"],
        "files": [entry],
        "keywords": [
            "soil_aoc",
            "aggregate_organic_carbon",
            "aggregate_stability",
            "soil_carbon_fractions",
            "gridded_simulation",
            "global_grid",
        ],
        "variables": ["AOC", "AD"],
    }
    meta["vis_data"] = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal Aggregate Organic Carbon Components",
        "chart_subtitle": (
            f"Zonal means across {int(mask.sum()):,} valid 0.5-degree land cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "Total AOC (g C m-2)",
        "series1_data": zonal_total,
        "series2_name": ">2 mm aggregate (g C m-2)",
        "series2_data": zonal_macro,
        "series3_name": "0.25-2 mm aggregate (g C m-2)",
        "series3_data": zonal_micro,
        "y_axis_name": "AOC (g C m-2)",
        "depth_title": "Mean Carbon by Aggregate Size Class",
        "depth_subtitle": "Aggregate organic carbon across four measured size fractions",
        "depth_x_axis_name": "Mean AOC (g C m-2)",
        "depth_labels": [">2 mm", "0.25-2 mm", "0.053-0.25 mm", "<0.053 mm"],
        "depth_series": [
            {
                "name": "Mean AOC (g C m-2)",
                "data": [mean_macro, mean_micro, mean_fine_mid, mean_fine],
                "color": "#2e7d32",
            }
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "Total AOC (g C m-2)",
        "kin_y_label": ">2 mm aggregate C (g C m-2)",
        "kin_title": "Total AOC vs. Macroaggregate Carbon",
        "kin_subtitle": "Binned grid cells linking bulk aggregate carbon to the >2 mm fraction",
        "columns": [
            "Latitude",
            "Longitude",
            "AOC total (g C m-2)",
            ">2 mm (g C m-2)",
            "0.25-2 mm (g C m-2)",
            "<0.053 mm (g C m-2)",
        ],
        "records": records,
        "total_count": f"{int(mask.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    return meta


def build_doc_turnover_grid() -> dict:
    path = DATA_DIR / "DOC Turnover" / "global_DOC_turnover.nc"
    latitude, longitude, arrays = read_h5_grid(path, ["DOC turnover rate"])
    turnover = arrays["DOC turnover rate"]
    mask = np.isfinite(turnover) & (turnover > -9998)

    labels, zonal = zonal_by_latitude(latitude, turnover, mask)
    values = turnover[mask]
    edges = np.linspace(float(values.min()), float(values.max()), 13)
    hist_labels, hist_share = histogram_share(values, edges, fmt=".4f")

    sorted_values = np.sort(values)
    cumulative = np.arange(1, len(sorted_values) + 1) / len(sorted_values) * 100
    sample_index = np.linspace(0, len(sorted_values) - 1, 12).astype(int)
    kin_x = [round(float(sorted_values[index]), 4) for index in sample_index]
    kin_y = [round(float(cumulative[index]), 1) for index in sample_index]

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if mask[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        records.append(
            {
                "Latitude": value_or_none(latitude[row], 2),
                "Longitude": value_or_none(longitude[col], 2),
                "DOC turnover rate (day-1)": value_or_none(turnover[row, col], 5),
            }
        )

    nc_entry = file_entry("data/Microbe Data/DOC Turnover/global_DOC_turnover.nc", "Turnover Grid NetCDF")
    csv_entry = file_entry("data/Microbe Data/DOC Turnover/DOC_turnover.csv", "Turnover CSV")
    meta = {
        "id": 8,
        "title": "Global Soil Dissolved Organic Carbon Turnover Rate (0.5-Degree Grid)",
        "author": "MicrobialDataSystem archive (SDSU)",
        "year": 2026,
        "doi": "",
        "description": (
            "Physical files: global_DOC_turnover.nc and DOC_turnover.csv archived in "
            "data/Microbe Data/DOC Turnover. The NetCDF grid (360 x 720) and its flattened "
            f"CSV representation contain {int(mask.sum()):,} valid land cells with predicted "
            "soil dissolved organic carbon turnover rates (day-1)."
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
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "temporal_resolution": "Static Grid",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 1.0,
        "data_source_type": "github",
        "github_url": nc_entry["url"],
        "local_file_path": nc_entry["path"],
        "files": [nc_entry, csv_entry],
        "keywords": [
            "soil_doc",
            "doc_turnover",
            "dissolved_organic_carbon",
            "carbon_cycling",
            "gridded_simulation",
            "global_grid",
        ],
        "variables": ["DOC_TURN", "DOC"],
    }
    meta["vis_data"] = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal DOC Turnover Rate",
        "chart_subtitle": (
            f"Zonal means across {int(mask.sum()):,} valid 0.5-degree land cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "DOC turnover rate (day-1)",
        "series1_data": zonal,
        "series2_name": None,
        "series2_data": None,
        "series3_name": None,
        "series3_data": None,
        "y_axis_name": "Turnover rate (day-1)",
        "depth_title": "Turnover Rate Distribution",
        "depth_subtitle": "Share of valid land area across turnover-rate classes",
        "depth_x_axis_name": "Share of land area (%)",
        "depth_labels": hist_labels,
        "depth_series": [
            {"name": "Land area share (%)", "data": hist_share, "color": "#2e7d32"}
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "Turnover rate (day-1)",
        "kin_y_label": "Cumulative land area (%)",
        "kin_title": "Cumulative Distribution of DOC Turnover",
        "kin_subtitle": "Cumulative share of valid land area sorted by predicted turnover rate",
        "columns": ["Latitude", "Longitude", "DOC turnover rate (day-1)"],
        "records": records,
        "total_count": f"{int(mask.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    return meta


def build_fbc_bbc_grid() -> dict:
    path = DATA_DIR / "FBC_BBC" / "FBC_BBC.nc"
    arrays = cdf1_variables(path)
    latitude = arrays["latitude"]
    longitude = arrays["longitude"]
    fbc = arrays["FBC"]
    bbc = arrays["BBC"]
    ratio = arrays["FBratio"]
    biome = arrays["Biome"]
    mask = (fbc > -9998) & (bbc > -9998) & np.isfinite(fbc) & np.isfinite(bbc)

    labels, zonal_fbc = zonal_by_latitude(latitude, fbc, mask)
    _, zonal_bbc = zonal_by_latitude(latitude, bbc, mask)
    _, zonal_ratio = zonal_by_latitude(latitude, ratio, mask)

    biome_labels, biome_fbc, biome_bbc = [], [], []
    for code in sorted(np.unique(biome[mask])):
        selected = mask & (biome == code)
        if selected.sum() < 20:
            continue
        biome_labels.append(VEG_NAMES.get(int(code), f"Class {int(code)}"))
        biome_fbc.append(value_or_none(fbc[selected].mean(), 1))
        biome_bbc.append(value_or_none(bbc[selected].mean(), 1))

    kin_x, kin_y = [], []
    edges = np.linspace(
        float(np.percentile(fbc[mask], 1)),
        float(np.percentile(fbc[mask], 99)),
        12,
    )
    for index in range(len(edges) - 1):
        selected = mask & (fbc >= edges[index]) & (fbc < edges[index + 1])
        if selected.sum() > 10:
            kin_x.append(round(float((edges[index] + edges[index + 1]) / 2), 1))
            kin_y.append(round(float(bbc[selected].mean()), 1))

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if mask[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        code = int(biome[row, col])
        records.append(
            {
                "Latitude": value_or_none(latitude[row], 2),
                "Longitude": value_or_none(longitude[col], 2),
                "Biome": VEG_NAMES.get(code, f"Class {code}"),
                "FBC (g C m-2)": value_or_none(fbc[row, col], 1),
                "BBC (g C m-2)": value_or_none(bbc[row, col], 1),
                "F:B ratio": value_or_none(ratio[row, col], 2),
            }
        )

    entry = file_entry("data/Microbe Data/FBC_BBC/FBC_BBC.nc", "FBC/BBC Grid NetCDF")
    meta = {
        "id": 9,
        "title": "Global Soil Fungal and Bacterial Biomass Carbon (0.5-Degree Grid)",
        "author": "Liyuan He, Xiaofeng Xu, et al. (SDSU)",
        "year": 2020,
        "doi": "",
        "description": (
            "Physical file: FBC_BBC.nc archived in data/Microbe Data/FBC_BBC. A 0.5-degree "
            f"gridded product (360 x 720) with {int(mask.sum()):,} valid land cells, providing "
            "fungal biomass carbon (FBC), bacterial biomass carbon (BBC), the fungal:bacterial "
            "ratio, and 12 biome classes. Reference: He et al. (2020) Global biogeography of "
            "fungal and bacterial biomass carbon in topsoil, Soil Biology and Biochemistry."
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
        "max_depth": 0.3,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": entry["path"],
        "files": [entry],
        "keywords": [
            "fungal_biomass",
            "bacterial_biomass",
            "fungal_bacterial_ratio",
            "soil_microbial_biomass",
            "gridded_simulation",
            "global_grid",
        ],
        "variables": ["FBC", "BBC", "FB_RATIO"],
    }
    meta["vis_data"] = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal Fungal and Bacterial Biomass Carbon",
        "chart_subtitle": (
            f"Zonal means across {int(mask.sum()):,} valid 0.5-degree land cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "Fungal biomass C (g C m-2)",
        "series1_data": zonal_fbc,
        "series2_name": "Bacterial biomass C (g C m-2)",
        "series2_data": zonal_bbc,
        "series3_name": "F:B ratio",
        "series3_data": zonal_ratio,
        "series3_axis": 1,
        "y_axis_name": "Biomass C (g C m-2)",
        "y_axis_name2": "F:B ratio",
        "depth_title": "Fungal and Bacterial Biomass by Biome",
        "depth_subtitle": "Mean biomass carbon across the 12 archived biome classes",
        "depth_x_axis_name": "Biomass C (g C m-2)",
        "depth_labels": biome_labels,
        "depth_series": [
            {"name": "FBC (g C m-2)", "data": biome_fbc, "color": "#2e7d32"},
            {"name": "BBC (g C m-2)", "data": biome_bbc, "color": "#1565c0"},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "Fungal biomass C (g C m-2)",
        "kin_y_label": "Bacterial biomass C (g C m-2)",
        "kin_title": "Fungal vs. Bacterial Biomass Scaling",
        "kin_subtitle": "Binned grid cells linking fungal to bacterial biomass carbon",
        "columns": [
            "Latitude",
            "Longitude",
            "Biome",
            "FBC (g C m-2)",
            "BBC (g C m-2)",
            "F:B ratio",
        ],
        "records": records,
        "total_count": f"{int(mask.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    return meta


def build_gene_grid(dataset_id: int, gene: str) -> dict:
    folder, filename = ("MCRA", "global_mcrA.nc") if gene == "mcra" else ("PMOA", "global_pmoA.nc")
    path = DATA_DIR / folder / filename
    latitude, longitude, arrays = read_h5_grid(path, ["mcrA density", "pmoA density"])
    target = arrays["mcrA density"] if gene == "mcra" else arrays["pmoA density"]
    other = arrays["pmoA density"] if gene == "mcra" else arrays["mcrA density"]
    mask = np.isfinite(target) & (target > -9998)

    labels, zonal = zonal_by_latitude(latitude, target, mask)
    values = target[mask]
    edges = np.linspace(float(values.min()), float(values.max()), 11)
    hist_labels, hist_share = histogram_share(values, edges, fmt=".2f")

    kin_x, kin_y = [], []
    edges = np.linspace(
        float(np.percentile(target[mask], 1)),
        float(np.percentile(target[mask], 99)),
        12,
    )
    for index in range(len(edges) - 1):
        selected = mask & (target >= edges[index]) & (target < edges[index + 1])
        if selected.sum() > 10:
            kin_x.append(round(float((edges[index] + edges[index + 1]) / 2), 2))
            kin_y.append(round(float(other[selected].mean()), 2))

    records = []
    candidates = [
        (row, col)
        for row in range(10, 360, 20)
        for col in range(10, 720, 30)
        if mask[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        records.append(
            {
                "Latitude": value_or_none(latitude[row], 2),
                "Longitude": value_or_none(longitude[col], 2),
                "mcrA density (copies m-2)": value_or_none(arrays["mcrA density"][row, col], 2),
                "pmoA density (copies m-2)": value_or_none(arrays["pmoA density"][row, col], 2),
            }
        )

    is_mcra = gene == "mcra"
    title = (
        "Global Soil mcrA Gene Density (0.5-Degree Grid)"
        if is_mcra
        else "Global Soil pmoA Gene Density (0.5-Degree Grid)"
    )
    entry = file_entry(
        f"data/Microbe Data/{folder}/{filename}",
        "mcrA Grid NetCDF" if is_mcra else "pmoA Grid NetCDF",
    )
    meta = {
        "id": dataset_id,
        "title": title,
        "author": (
            "Ziyu Guo, Xiaofeng Xu, et al. (SDSU)"
            if is_mcra
            else "Xinhao Zhu, Xiaofeng Xu, et al. (SDSU)"
        ),
        "year": 2026,
        "doi": "",
        "description": (
            f"Physical file: {filename} archived in data/Microbe Data/{folder}. A 0.5-degree "
            f"random-forest prediction grid (360 x 720) with {int(mask.sum()):,} valid land "
            f"cells. The file stores predicted {'mcrA' if is_mcra else 'pmoA'} gene density "
            "and the companion methane-cycle gene density, both in copies m-2."
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
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "temporal_resolution": "Static Grid",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 0.3,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": entry["path"],
        "files": [entry],
        "keywords": (
            ["mcra", "methanogenesis", "gene_density", "soil_microbial_community",
             "gridded_simulation", "global_grid"]
            if is_mcra
            else ["pmoa", "methane_oxidation", "gene_density", "soil_microbial_community",
                  "gridded_simulation", "global_grid"]
        ),
        "variables": ["MCR_A", "PMO_A"] if is_mcra else ["PMO_A", "MCR_A"],
    }

    target_name = "mcrA" if is_mcra else "pmoA"
    other_name = "pmoA" if is_mcra else "mcrA"
    meta["vis_data"] = {
        "data_type": "netcdf",
        "chart_title": f"Global Zonal Soil {target_name} Gene Density",
        "chart_subtitle": (
            f"Zonal means across {int(mask.sum()):,} valid 0.5-degree land cells "
            "(360 x 720 matrix; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": f"{target_name} density (copies m-2)",
        "series1_data": zonal,
        "series2_name": None,
        "series2_data": None,
        "series3_name": None,
        "series3_data": None,
        "y_axis_name": "Gene density (copies m-2)",
        "depth_title": f"{target_name} Density Distribution",
        "depth_subtitle": "Share of valid land area across predicted gene-density classes",
        "depth_x_axis_name": "Share of land area (%)",
        "depth_labels": hist_labels,
        "depth_series": [
            {"name": "Land area share (%)", "data": hist_share, "color": "#2e7d32"}
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": f"{target_name} density (copies m-2)",
        "kin_y_label": f"{other_name} density (copies m-2)",
        "kin_title": f"{target_name} vs. {other_name} Gene Density",
        "kin_subtitle": "Binned grid cells linking the two methane-cycle gene markers",
        "columns": [
            "Latitude",
            "Longitude",
            "mcrA density (copies m-2)",
            "pmoA density (copies m-2)",
        ],
        "records": records,
        "total_count": f"{int(mask.sum()):,} valid 0.5-degree land grid cells (360 x 720 matrix)",
    }
    return meta


def build_mmq_observations() -> dict:
    path = DATA_DIR / "MMQ" / "MMQ.csv"
    frame = pd.read_csv(
        path,
        encoding="utf-8-sig",
        skiprows=[1],
        lineterminator="\r",
    )
    frame["biome"] = frame["vegetation"].map(normalize_biome)
    numeric = {
        "MQ": "Microbial quotient (MicrobialC/Organic C)",
        "MBC": "Biomass C",
        "MBN": "Biomass N",
        "MBP": "Biomass P",
        "BR": "Basal respiration (ug C g-1 h-1)",
        "PH": "pH",
        "MAT": "MAT",
        "MAP": "MAP",
    }
    for target, source in numeric.items():
        frame[target] = pd.to_numeric(frame.get(source), errors="coerce")

    def depth_midpoint(raw):
        match = re.search(r"(\d+(?:\.\d+)?)\s*[~\-]\s*(\d+(?:\.\d+)?)", str(raw))
        if not match:
            return np.nan
        return (float(match.group(1)) + float(match.group(2))) / 2

    frame["depth"] = frame["Soil Depth (cm)"].map(depth_midpoint)

    grouped = (
        frame.groupby("biome")
        .agg(n=("MBC", "size"), MQ=("MQ", "mean"), BR=("BR", "mean"), MBC=("MBC", "mean"))
        .query("n >= 20")
        .sort_values("MQ", ascending=False)
    )

    depth_bins = [(0, 10), (10, 20), (20, 30), (30, 50), (50, 100)]
    depth_labels = ["0-10cm", "10-20cm", "20-30cm", "30-50cm", "50-100cm"]
    depth_mq = []
    for low, high in depth_bins:
        subset = frame[(frame["depth"] > low) & (frame["depth"] <= high)]
        depth_mq.append(mean_or_none(subset["MQ"], 2) or 0)

    kin_x, kin_y = [], []
    edges = np.logspace(
        np.log10(max(0.1, float(frame["MBC"].min()))),
        np.log10(float(frame["MBC"].max())),
        10,
    )
    for index in range(len(edges) - 1):
        subset = frame[(frame["MBC"] >= edges[index]) & (frame["MBC"] < edges[index + 1])]
        if len(subset) >= 5 and subset["BR"].notna().any():
            kin_x.append(round(float((edges[index] + edges[index + 1]) / 2), 2))
            kin_y.append(round(float(subset["BR"].mean()), 3))

    sample = frame.dropna(subset=["MBC"]).sample(
        n=min(15, int(frame["MBC"].notna().sum())), random_state=21
    )
    records = []
    for row in sample.to_dict(orient="records"):
        records.append(
            {
                "Country": str(row["Country"]).strip(),
                "Biome": row["biome"],
                "Depth (cm)": value_or_none(row["depth"], 1),
                "Biomass C (mmol kg-1)": value_or_none(row["MBC"], 2),
                "Basal respiration (ug C g-1 h-1)": value_or_none(row["BR"], 3),
                "Microbial quotient (%)": value_or_none(row["MQ"], 2),
                "pH": value_or_none(row["PH"], 2),
            }
        )

    entry = file_entry("data/Microbe Data/MMQ/MMQ.csv", "MMQ Observations CSV")
    meta = {
        "id": 11,
        "title": "Global Soil Microbial Metabolic Quotient Observations",
        "author": "MicrobialDataSystem archive (SDSU)",
        "year": 2026,
        "doi": "",
        "description": (
            "Physical file: MMQ.csv archived in data/Microbe Data/MMQ. Compiles 2,444 field "
            "and incubation observations from 48 countries with microbial biomass C, N and P, "
            "basal respiration, microbial quotient (microbial C / organic C), soil C/N/P, pH, "
            "MAT, MAP and sampling depth."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Ecosystems (MMQ synthesis)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "temporal_resolution": "Snapshot",
        "data_type": "Field Observation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 1.0,
        "data_source_type": "github",
        "github_url": entry["url"],
        "local_file_path": entry["path"],
        "files": [entry],
        "keywords": [
            "metabolic_quotient",
            "basal_respiration",
            "soil_respiration",
            "soil_microbial_biomass",
            "global_synthesis",
            "soil_chemistry",
        ],
        "variables": ["MQ", "MBC", "MBN", "MBP", "BR", "PH"],
    }
    meta["vis_data"] = {
        "data_type": "csv",
        "chart_title": "Global Biome Microbial Quotient, Respiration and Biomass Carbon",
        "chart_subtitle": "Mean values aggregated from 2,444 observations across 48 countries",
        "x_labels": grouped.index.tolist(),
        "x_axis_name": "Global Biomes",
        "series1_name": "Microbial quotient (%)",
        "series1_data": [value_or_none(grouped.loc[b, "MQ"], 2) for b in grouped.index],
        "series2_name": "Basal respiration (ug C g-1 h-1)",
        "series2_data": [value_or_none(grouped.loc[b, "BR"], 3) for b in grouped.index],
        "series3_name": "Biomass C (mmol kg-1)",
        "series3_data": [value_or_none(grouped.loc[b, "MBC"], 2) for b in grouped.index],
        "series3_axis": 1,
        "y_axis_name": "MQ (%) / Respiration (ug C g-1 h-1)",
        "y_axis_name2": "Biomass C (mmol kg-1)",
        "depth_title": "Microbial Quotient Depth Profile",
        "depth_subtitle": "Mean microbial quotient across reported soil depth horizons",
        "depth_x_axis_name": "Microbial quotient (%)",
        "depth_labels": depth_labels,
        "depth_series": [
            {"name": "Microbial quotient (%)", "data": depth_mq, "color": "#2e7d32"}
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "Biomass C (mmol kg-1)",
        "kin_y_label": "Basal respiration (ug C g-1 h-1)",
        "kin_title": "Biomass Carbon vs. Basal Respiration",
        "kin_subtitle": "Log-binned observations linking microbial biomass to respiration",
        "columns": [
            "Country",
            "Biome",
            "Depth (cm)",
            "Biomass C (mmol kg-1)",
            "Basal respiration (ug C g-1 h-1)",
            "Microbial quotient (%)",
            "pH",
        ],
        "records": records,
        "total_count": "2,444 observations across 48 countries",
    }
    return meta


def build_mnl_mpl_rasters() -> dict:
    mnl, latitude, longitude = read_geotiff(DATA_DIR / "MNL_MPL" / "Global_MNL.tif")
    mpl, _, _ = read_geotiff(DATA_DIR / "MNL_MPL" / "Global_MPL.tif")
    mask = np.isfinite(mnl) & np.isfinite(mpl)

    labels, zonal_mnl = zonal_by_latitude(latitude, mnl, mask)
    _, zonal_mpl = zonal_by_latitude(latitude, mpl, mask)

    edges = np.linspace(-8, 8, 17)
    hist_labels, hist_mnl = histogram_share(mnl[mask], edges, fmt=".1f")
    _, hist_mpl = histogram_share(mpl[mask], edges, fmt=".1f")

    kin_x, kin_y = [], []
    edges = np.linspace(
        float(np.percentile(mnl[mask], 1)),
        float(np.percentile(mnl[mask], 99)),
        12,
    )
    for index in range(len(edges) - 1):
        selected = mask & (mnl >= edges[index]) & (mnl < edges[index + 1])
        if selected.sum() > 100:
            kin_x.append(round(float((edges[index] + edges[index + 1]) / 2), 2))
            kin_y.append(round(float(mpl[selected].mean()), 2))

    records = []
    candidates = [
        (row, col)
        for row in range(20, mnl.shape[0], 70)
        for col in range(20, mnl.shape[1], 180)
        if mask[row, col]
    ]
    picks = np.linspace(0, len(candidates) - 1, 15).astype(int) if candidates else []
    for index in picks:
        row, col = candidates[int(index)]
        records.append(
            {
                "Latitude": value_or_none(latitude[row], 2),
                "Longitude": value_or_none(longitude[col], 2),
                "MNL index": value_or_none(mnl[row, col], 3),
                "MPL index": value_or_none(mpl[row, col], 3),
            }
        )

    mnl_entry = file_entry("data/Microbe Data/MNL_MPL/Global_MNL.tif", "MNL GeoTIFF")
    mpl_entry = file_entry("data/Microbe Data/MNL_MPL/Global_MPL.tif", "MPL GeoTIFF")
    meta = {
        "id": 12,
        "title": "Global Microbial Nitrogen and Phosphorus Limitation Predictions (0.1-Degree Rasters)",
        "author": "MicrobialDataSystem archive (SDSU)",
        "year": 2026,
        "doi": "10.5061/dryad.jm63xsjnw",
        "description": (
            "Physical files: Global_MNL.tif and Global_MPL.tif archived in "
            "data/Microbe Data/MNL_MPL. Two 0.1-degree GeoTIFF rasters (3599 x 1367) of "
            f"predicted microbial nitrogen (MNL) and phosphorus (MPL) limitation indices, "
            f"with {int(mask.sum()):,} valid land pixels. Dataset DOI: "
            "10.5061/dryad.jm63xsjnw."
        ),
        "spatial_scale": "Global",
        "site_code": "Global-Terrestrial",
        "site": {
            "site_code": "Global-Terrestrial",
            "site_name": "Global Terrestrial Raster (0.1 degree)",
            "biome": "Global / Multi-Biome",
            "latitude": 20,
            "longitude": 0,
        },
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "temporal_resolution": "Static Raster",
        "data_type": "Model Simulation",
        "scenario": "Control",
        "min_depth": 0,
        "max_depth": 0.3,
        "data_source_type": "github",
        "github_url": mnl_entry["url"],
        "local_file_path": mnl_entry["path"],
        "files": [mnl_entry, mpl_entry],
        "keywords": [
            "microbial_n_limitation",
            "microbial_p_limitation",
            "nutrient_limitation",
            "global_grid",
        ],
        "variables": ["MNL", "MPL"],
    }
    meta["vis_data"] = {
        "data_type": "netcdf",
        "chart_title": "Global Zonal Microbial N and P Limitation Indices",
        "chart_subtitle": (
            f"Zonal means across {int(mask.sum()):,} valid 0.1-degree land pixels "
            "(3599 x 1367 rasters; 5-degree latitude bands)"
        ),
        "x_labels": labels,
        "x_axis_name": "Latitude",
        "series1_name": "MNL index",
        "series1_data": zonal_mnl,
        "series2_name": "MPL index",
        "series2_data": zonal_mpl,
        "series3_name": None,
        "series3_data": None,
        "y_axis_name": "Limitation index",
        "depth_title": "Distribution of Limitation Index Values",
        "depth_subtitle": "Share of valid land area across index classes",
        "depth_x_axis_name": "Share of land area (%)",
        "depth_labels": hist_labels,
        "depth_series": [
            {"name": "MNL share (%)", "data": hist_mnl, "color": "#2e7d32"},
            {"name": "MPL share (%)", "data": hist_mpl, "color": "#1565c0"},
        ],
        "kin_x": kin_x,
        "kin_y": kin_y,
        "kin_x_label": "MNL index",
        "kin_y_label": "MPL index",
        "kin_title": "Microbial N vs. P Limitation",
        "kin_subtitle": "Binned land pixels linking the nitrogen and phosphorus indices",
        "columns": ["Latitude", "Longitude", "MNL index", "MPL index"],
        "records": records,
        "total_count": f"{int(mask.sum()):,} valid 0.1-degree land pixels (3599 x 1367 rasters)",
    }
    return meta


def main() -> None:
    raw = DATA_JS.read_text(encoding="utf-8")
    prefix = "window.PORTAL_DATA = "
    bundle = json.loads(raw[len(prefix):].rstrip().rstrip(";"))

    existing_datasets = []
    seen_ids = set()
    for item in bundle["datasets"]:
        if item["id"] in REBUILD_DATASET_IDS or item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        existing_datasets.append(item)
    existing_keywords = [item for item in bundle["keywords"] if item not in LATEST_KEYWORDS]
    existing_variables = [
        item for item in bundle["variables"]
        if item["code"] not in {variable["code"] for variable in LATEST_VARIABLES}
    ]

    new_datasets = [
        build_aoc_grid(),
        build_doc_turnover_grid(),
        build_fbc_bbc_grid(),
        build_gene_grid(10, "mcra"),
        build_mmq_observations(),
        build_mnl_mpl_rasters(),
        build_gene_grid(13, "pmoa"),
    ]

    bundle["datasets"] = existing_datasets + new_datasets
    bundle["keywords"] = LATEST_KEYWORDS + existing_keywords
    bundle["variables"] = existing_variables + LATEST_VARIABLES

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

    # Store first-party files as repository-relative paths so forks resolve them
    # against their own owner/repository at runtime.
    for dataset in bundle["datasets"]:
        if str(dataset.get("github_url", "")).startswith(LEGACY_RAW_BASE):
            dataset["github_url"] = dataset.get("local_file_path") or dataset["github_url"]
        for file_info in dataset.get("files", []):
            if str(file_info.get("url", "")).startswith(LEGACY_RAW_BASE):
                file_info["url"] = file_info.get("path") or file_info["url"]

    output = prefix + json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + ";"
    DATA_JS.write_text(output, encoding="utf-8")

    print(f"Wrote {DATA_JS}")
    print(f"Datasets: {len(bundle['datasets'])} (added {len(new_datasets)})")
    print(f"Keywords: {len(bundle['keywords'])}")
    print(f"Variables: {len(bundle['variables'])}")


if __name__ == "__main__":
    main()
