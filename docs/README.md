# MicrobialDataSystem - Static GitHub Pages Build

This folder is a **pure client-side** build of the MicrobialDataSystem portal. It needs no
Python, Flask, or database at runtime: every page is rendered in the browser from a data
snapshot plus an ECharts bundle.

## Contents

```
docs/
  index.html            single-page shell (home / detail views)
  .nojekyll             disables Jekyll processing on GitHub Pages
  assets/
    css/style.css       portal styles
    js/data.js          catalogue snapshot and visualization payloads
    js/app.js           hash router, slicer, detail charts
    js/echarts.min.js   charting library
  tools/
    build_data.py       rebuilds data.js from the archived source files
```

## Routes

| URL | View |
| --- | --- |
| `#/` | Data discovery, multi-dimensional slicer, dataset cards |
| `#/dataset/1` | Microbial biomass C/N/P observations |
| `#/dataset/2` | Microbial biomass C/N gridded simulation |
| `#/dataset/3` | Soil DOC field observations (Excel workbook) |
| `#/dataset/4` | Soil DOC 0.5-degree gridded dataset |
| `#/dataset/5` | Soil POC field observations (0-30 cm and 0-100 cm) |
| `#/dataset/6` | Soil POC 0.5-degree gridded dataset |

## Scope of the static build

This build intentionally omits download counters, user authentication, registration, and
dataset submission. Download buttons link straight to the archived source files, and the
sidebar exposes a single page: Data Discovery & Slicer. Dataset detail pages open from the
catalogue cards. CSV files are fetched and saved as Blobs so Chrome and other browsers
download them instead of opening raw text in a tab.

All future updates to the static site should be made inside this `docs/` folder.

## Publish with GitHub Pages

1. Push this branch (`gh-pages`) to GitHub.
2. Open **Settings → Pages** in the repository.
3. Set **Source** to *Deploy from a branch*, branch `gh-pages`, folder `/docs`.
4. Save. The site becomes available at `https://<user>.github.io/<repository>/`.

All asset paths are relative, so the build works from a project sub-path as well as a
custom domain. Hash routing avoids any server-side rewrite rules.

## Cache busting

Each page load creates an access timestamp (`window.__ACCESS_TS__`). The stylesheet,
`data.js`, and `app.js` are requested as `...?t=<timestamp>`, so browsers and the GitHub
Pages CDN always fetch the current build instead of a stale cached copy. `echarts.min.js`
is version-pinned and intentionally left cacheable. To refresh the HTML document itself,
open the site with an extra query parameter, for example `?t=202610202200`.

## Updating the data snapshot

`assets/js/data.js` is generated from two sources:

1. the original metadata for datasets 1-2 in the existing bundle;
2. the archived source files under `data/Microbe Data`:
   - `DOC/Soil_DOC.csv`
   - `DOC/Global_Soil_DOC.nc`
   - `POC/POC_0-30.csv`
   - `POC/POC_0_100.csv`
   - `POC/POC_Global_Map.nc`

After changing the source files, regenerate the bundle from the repository root:

```bash
.venv/bin/python docs/tools/build_data.py
```

The script requires `pandas` and `numpy`. Only CSV and NetCDF files are published for
download; the original Excel workbook is kept as a local authoring source and is not part
of the public download set. Every file in a dataset is exposed as its own download link.
