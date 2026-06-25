# CLAUDE.md

Context for working on this project with Claude Code.

## What this is

A static, single-page data tool ("Climate Poor") about winter indoor comfort and energy hardship across the EU, US and Canada. Plotly charts, Economist data-journalism styling. No framework, no build step. The web root is `public/`.

## Files

- `public/index.html` is the entire app: markup, CSS, all JS, and the embedded tado dataset. Everything is in this one file by design, so the site deploys as plain static assets.
- `scripts/eurostat_pull.py` is the only backend piece. It fetches three Eurostat datasets, decodes JSON-stat, and writes `public/data/thermal_data.json`. Stdlib only. It has an offline `--selftest` for the decoder.
- `public/data/thermal_data.json` is the generated Eurostat data. The app fetches it at runtime and falls back to a small embedded sample if it is missing.

## Data contract

`thermal_data.json` shape, consumed by `applyRealModel()` in index.html:

```
{ "countries": { "<EurostatGeo>": {
    "name": str, "iso3": str,
    "warm": { "<year>": pct, ... },   // ilc_mdes01, unable to keep warm
    "hdd":  { "<year>": number, ... },// nrg_chdd_a, heating degree days
    "gdp":  { "<year>": number, ... } // nama_10_pc, GDP per capita EUR
} } }
```

The app keys countries by ISO-3. Region grouping (Nordic, Baltic, Western, Central & East, Southern) is a presentation lookup in index.html (`REGIONS`), not a Eurostat field.

## The four views

1. Maps: a choropleth with a metric toggle. "Cannot keep warm" (Eurostat, year slider) and "Indoor warmth" (tado, single snapshot).
2. Climate vs comfort: heating degree days vs unable-to-keep-warm, bubble size is GDP.
3. Three countries: EU vs US vs Canada, showing the metrics are not comparable.
4. Warm for whom?: the centerpiece. tado indoor temperature vs Eurostat hardship. The top-right cluster is the inequality story.

## Conventions and caveats

- No em dashes in any copy.
- tado data is smart-thermostat homes, an affluent subset. Never present it as a population average. The divergence between tado warmth and Eurostat hardship is the intended insight.
- The EU, US and Canada hardship numbers use different definitions. Keep them on separate scales and labelled.
- If porting maps off Plotly, use MapLibre with OpenFreeMap, not Mapbox.
- Red (#E3120B) is the single accent, reserved for the corner tab, the active tab underline, the insight rule, and real-world benchmarks like the WHO 18 degree line. Charts use the Economist categorical palette.
