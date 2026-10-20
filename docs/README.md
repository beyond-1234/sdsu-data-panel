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
    js/data.js          data snapshot exported from the Flask database
    js/app.js           hash router, slicer, detail charts, catalogue telemetry
    js/echarts.min.js   charting library
```

## Routes

| URL | View |
| --- | --- |
| `#/` | Data discovery, multi-dimensional slicer, dataset cards |
| `#/dataset/1` | CSV observation dataset detail page with real charts |
| `#/dataset/2` | NetCDF gridded dataset detail page with real charts |

## Scope of the static build

This build intentionally omits download counters, user authentication, registration, and
dataset submission. Download buttons link straight to the archived source files, and the
sidebar exposes a single page: Data Discovery & Slicer. Dataset detail pages open from the
catalogue cards.

All future updates to the static site should be made inside this `docs/` folder.

## Publish with GitHub Pages

1. Push this branch (`gh-pages`) to GitHub.
2. Open **Settings → Pages** in the repository.
3. Set **Source** to *Deploy from a branch*, branch `gh-pages`, folder `/docs`.
4. Save. The site becomes available at `https://<user>.github.io/<repository>/`.

All asset paths are relative, so the build works from a project sub-path as well as a
custom domain. Hash routing avoids any server-side rewrite rules.

## Updating the data snapshot

`assets/js/data.js` is exported from the Flask database and contains the dataset metadata,
managed variables, taxonomy tags, and the pre-computed visualization payloads for both
physical files (`Soil_Microbial_Biomass_C_N_P_spatial.csv` and
`Global_Soil_Microbial_BiomassCN.nc`).

After changing the database or the parser in the backend branch, re-export the bundle and
replace `assets/js/data.js` before publishing.
