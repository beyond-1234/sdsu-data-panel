# MicrobialDataSystem Static Data Portal

A pure client-side scientific data portal for global soil microbial and carbon-cycle
datasets. The published site is hosted on GitHub Pages and requires no Flask server,
database, or other backend at runtime.

Live site: **https://beyond-1234.github.io/sdsu-data-panel/**

## Repository layout

```text
docs/                     GitHub Pages site (HTML, CSS, JS, ECharts)
  assets/js/data.js       dataset catalogue and visualization payloads
  tools/build_data.py     rebuilds data.js from the archived source files
data/Microbe Data/        source CSV, NetCDF, and GeoTIFF files used for downloads
```

The portal currently exposes 13 datasets covering microbial biomass carbon, nitrogen and
phosphorus, dissolved and particulate organic carbon, aggregate organic carbon, DOC
turnover, fungal/bacterial biomass, methane-cycle gene density, microbial metabolic
quotient, and microbial nutrient limitation.

## Local preview

```bash
python3 -m http.server 8000 --directory docs
```

Open `http://127.0.0.1:8000/`.

## Rebuilding the catalogue

Install the data-build dependencies:

```bash
pip install -r docs/tools/requirements.txt
```

Regenerate the static bundle after replacing files under `data/Microbe Data`:

```bash
python docs/tools/build_data.py
```

## Downloads

Every dataset exposes one download link per published file. Only CSV, NetCDF, and GeoTIFF
files are distributed; Excel workbooks remain local authoring sources and are excluded by
`.gitignore`. CSV downloads are fetched as Blobs so browsers save the file instead of
opening raw text.

## Deployment

GitHub Pages is configured to publish the `gh-pages` branch from the `/docs` folder. The
`main` branch is kept in sync and contains only the static site, source data, and the data
build tool.
