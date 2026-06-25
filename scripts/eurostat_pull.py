#!/usr/bin/env python3
"""
Eurostat -> public/data/thermal_data.json

Pulls the three indicators behind the "warmth gap" map straight from the
Eurostat dissemination API (JSON-stat 2.0), decodes them, and writes one
keyed dataset with full yearly series (so the map gets a working year
slider) plus a convenience "latest" value per country.

    python3 scripts/eurostat_pull.py            # live pull -> public/data/thermal_data.json
    python3 scripts/eurostat_pull.py --selftest # offline test of the JSON-stat decoder

Stdlib only (urllib + json). Run it from the repo root, or from anywhere:
the output path is resolved relative to this file.

If a live call returns HTTP 400, a dimension code below does not match that
dataset. Open  {BASE}/{code}?format=JSON  in a browser to see the real
dimension codes, then adjust INDICATORS.
"""

import json
import os
import sys
import datetime
import urllib.request
import urllib.parse

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "public", "data", "thermal_data.json")

# indicator key -> (dataset code, filters that pick the single slice we want)
INDICATORS = {
    "warm": ("ilc_mdes01", {"freq": "A", "hhcomp": "TOTAL", "rskpovth": "TOTAL",
                            "unit": "PC", "sinceTimePeriod": "2010"}),
    "hdd":  ("nrg_chdd_a", {"freq": "A", "indic_nrg": "HDD",
                            "unit": "NR", "sinceTimePeriod": "2010"}),
    # GDP per capita, current prices, euro per head.
    # For purchasing-power comparability swap unit -> "PPS_EU27_2020_HAB".
    "gdp":  ("nama_10_pc", {"freq": "A", "unit": "CP_EUR_HAB",
                            "na_item": "B1GQ", "sinceTimePeriod": "2010"}),
}

# Eurostat 2-letter geo -> (display name, ISO-3 for the choropleth).
# Note: Greece is "EL" and the UK is "UK" in Eurostat.
GEO = {
    "AT": ("Austria", "AUT"), "BE": ("Belgium", "BEL"), "BG": ("Bulgaria", "BGR"),
    "HR": ("Croatia", "HRV"), "CY": ("Cyprus", "CYP"), "CZ": ("Czechia", "CZE"),
    "DK": ("Denmark", "DNK"), "EE": ("Estonia", "EST"), "FI": ("Finland", "FIN"),
    "FR": ("France", "FRA"), "DE": ("Germany", "DEU"), "EL": ("Greece", "GRC"),
    "HU": ("Hungary", "HUN"), "IE": ("Ireland", "IRL"), "IT": ("Italy", "ITA"),
    "LV": ("Latvia", "LVA"), "LT": ("Lithuania", "LTU"), "LU": ("Luxembourg", "LUX"),
    "MT": ("Malta", "MLT"), "NL": ("Netherlands", "NLD"), "PL": ("Poland", "POL"),
    "PT": ("Portugal", "PRT"), "RO": ("Romania", "ROU"), "SK": ("Slovakia", "SVK"),
    "SI": ("Slovenia", "SVN"), "ES": ("Spain", "ESP"), "SE": ("Sweden", "SWE"),
    "IS": ("Iceland", "ISL"), "NO": ("Norway", "NOR"), "CH": ("Switzerland", "CHE"),
    "UK": ("United Kingdom", "GBR"), "RS": ("Serbia", "SRB"), "TR": ("Turkiye", "TUR"),
    "ME": ("Montenegro", "MNE"), "MK": ("North Macedonia", "MKD"), "AL": ("Albania", "ALB"),
}
SKIP_PREFIX = ("EU", "EA")  # drop aggregates such as EU27_2020, EA19


def build_url(code, filters):
    q = {"format": "JSON", "lang": "EN"}
    q.update(filters)
    return BASE + "/" + code + "?" + urllib.parse.urlencode(q)


def fetch(code, filters):
    url = build_url(code, filters)
    req = urllib.request.Request(url, headers={"User-Agent": "thermal-gap/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def decode_jsonstat(obj):
    """Yield {dim_id: category_code, ..., 'value': v} per observation.

    JSON-stat 'value' is keyed by 0-indexed, row-major linear position over
    the cube whose axes and sizes are obj['id'] / obj['size']. Rebuilding the
    per-dimension index from the linear key with row-major strides makes this
    robust to any dimension ordering.
    """
    ids, sizes, dims = obj["id"], obj["size"], obj["dimension"]
    inv = {d: {pos: code for code, pos in dims[d]["category"]["index"].items()} for d in ids}
    strides = [1] * len(sizes)
    for k in range(len(sizes) - 2, -1, -1):
        strides[k] = strides[k + 1] * sizes[k + 1]
    for lin, v in obj["value"].items():
        L = int(lin)
        row = {d: inv[d][(L // strides[k]) % sizes[k]] for k, d in enumerate(ids)}
        row["value"] = v
        yield row


def extract_geo_time(obj):
    out = {}
    for row in decode_jsonstat(obj):
        out.setdefault(row["geo"], {})[row["time"]] = row["value"]
    return out


def selftest():
    s1 = {"id": ["unit", "geo", "time"], "size": [1, 2, 3],
          "dimension": {"unit": {"category": {"index": {"PC": 0}}},
                        "geo": {"category": {"index": {"DE": 0, "FR": 1}}},
                        "time": {"category": {"index": {"2022": 0, "2023": 1, "2024": 2}}}},
          "value": {"0": 10, "2": 12, "3": 20, "5": 22}}
    assert extract_geo_time(s1) == {"DE": {"2022": 10, "2024": 12}, "FR": {"2022": 20, "2024": 22}}
    s2 = {"id": ["time", "unit", "geo"], "size": [3, 1, 2],
          "dimension": {"time": {"category": {"index": {"2022": 0, "2023": 1, "2024": 2}}},
                        "unit": {"category": {"index": {"PC": 0}}},
                        "geo": {"category": {"index": {"DE": 0, "FR": 1}}}},
          "value": {"0": 10, "4": 12, "1": 20, "5": 22}}
    assert extract_geo_time(s2) == {"DE": {"2022": 10, "2024": 12}, "FR": {"2022": 20, "2024": 22}}
    print("selftest OK: JSON-stat decoder handles sparse values and any axis order")


def main():
    countries, meta = {}, {}
    for key, (code, filters) in INDICATORS.items():
        sys.stderr.write("fetching %s (%s)...\n" % (key, code))
        obj = fetch(code, filters)
        meta[key] = {"code": code, "label": obj.get("label", ""), "updated": obj.get("updated", "")}
        for geo, byyear in extract_geo_time(obj).items():
            if geo.startswith(SKIP_PREFIX) or geo not in GEO:
                continue
            rec = countries.setdefault(geo, {"name": GEO[geo][0], "iso3": GEO[geo][1]})
            rec[key] = {y: byyear[y] for y in sorted(byyear)}

    for rec in countries.values():
        for key in INDICATORS:
            s = rec.get(key) or {}
            rec[key + "_latest"] = s[max(s)] if s else None
            rec[key + "_year"] = max(s) if s else None

    payload = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "indicators": meta, "countries": countries}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    rows = sorted(countries.values(),
                  key=lambda r: r.get("warm_latest") if r.get("warm_latest") is not None else -1,
                  reverse=True)
    print("%-16s%8s%8s%12s" % ("Country", "warm%", "HDD", "GDP/cap"))
    for r in rows:
        w, h, g = r.get("warm_latest"), r.get("hdd_latest"), r.get("gdp_latest")
        print("%-16s%8s%8s%12s" % (r["name"], "" if w is None else w,
                                   "" if h is None else int(h), "" if g is None else int(g)))
    sys.stderr.write("wrote %s (%d countries)\n" % (os.path.relpath(OUT), len(countries)))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
