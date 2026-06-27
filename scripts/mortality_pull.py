#!/usr/bin/env python3
"""
Temperature-attributable mortality -> public/data/mortality.json

Builds the data behind the "What the cold costs" tab: the share of deaths
attributable to cold and to heat, as a percent, for two regions kept on
SEPARATE scales because they come from different studies.

  Europe        Masselot et al. 2023, Lancet Planetary Health (corrected
                series, Zenodo 10.5281/zenodo.10288665), urban pop 20+,
                2000-2019. Read from scripts/masselot2023_country_cold_heat.csv
                (af_cold_pct, af_heat_pct, joined on iso3).
  North America Gasparrini et al. 2015, national, % of all deaths. Pulled live
                from Our World in Data (slug: deaths-temperature-gasparrini),
                where cold = extreme_cold + moderate_cold and
                heat = moderate_heat + extreme_heat.

    python3 scripts/mortality_pull.py            # build -> public/data/mortality.json
    python3 scripts/mortality_pull.py --selftest # offline test of the OWID summation

Stdlib only (urllib + csv + json). Run from anywhere: paths resolve to this file.

If the pulled US or Canada numbers drift materially from the known cross-checks
(Canada cold ~4.46 / heat ~0.54, US heat ~0.4) the build log flags it instead of
silently shipping.
"""

import csv
import io
import json
import os
import sys
import datetime
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MASSELOT = os.path.join(HERE, "masselot2023_country_cold_heat.csv")
OUT = os.path.join(HERE, "..", "public", "data", "mortality.json")

OWID = ("https://ourworldindata.org/grapher/deaths-temperature-gasparrini.csv"
        "?csvType=full&useColumnShortNames=true")

# (iso3, label) -> expected (cold, heat) for the cross-check, with a tolerance
# in percentage points. None means "no published cross-check, do not flag".
CHECKS = {
    "CAN": {"cold": 4.46, "heat": 0.54},
    "USA": {"cold": None, "heat": 0.4},
}
TOL = 0.5


def split_cold_heat(row):
    """OWID splits the fraction into extreme/moderate cold and heat. The tab
    shows the totals, so cold = extreme_cold + moderate_cold and likewise heat."""
    cold = float(row["extreme_cold_fraction"]) + float(row["moderate_cold_fraction"])
    heat = float(row["moderate_heat_fraction"]) + float(row["extreme_heat_fraction"])
    return round(cold, 2), round(heat, 2)


def read_europe():
    out = {}
    with open(MASSELOT, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iso = (row.get("iso3") or "").strip()
            if not iso or iso == "EU30" or row.get("region") == "Total":
                continue  # drop the EU30 aggregate row
            out[iso] = {"name": row["country"].strip(),
                        "cold": round(float(row["af_cold_pct"]), 2),
                        "heat": round(float(row["af_heat_pct"]), 2),
                        # age-standardised rate per 100,000 (Masselot only; the
                        # Gasparrini/OWID North America source has no comparable rate)
                        "srCold": round(float(row["stdrate_cold"])),
                        "srHeat": round(float(row["stdrate_heat"]))}
    return out


def fetch_north_america(log):
    req = urllib.request.Request(OWID, headers={"User-Agent": "climate-poor/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = (row.get("code") or "").strip()
        if code not in ("USA", "CAN"):
            continue
        cold, heat = split_cold_heat(row)
        name = row["entity"].strip()
        out[code] = {"name": name, "cold": cold, "heat": heat}
        chk = CHECKS.get(code, {})
        for key in ("cold", "heat"):
            exp = chk.get(key)
            got = out[code][key]
            if exp is not None and abs(got - exp) > TOL:
                log.append("FLAG: %s %s pulled %.2f but cross-check expects ~%.2f"
                           % (name, key, got, exp))
            elif exp is not None:
                log.append("ok: %s %s %.2f (cross-check ~%.2f)" % (name, key, got, exp))
    for code in ("USA", "CAN"):
        if code not in out:
            log.append("FLAG: %s missing from the OWID pull" % code)
    return out


def selftest():
    sample = {"extreme_cold_fraction": "0.25", "moderate_cold_fraction": "4.21",
              "moderate_heat_fraction": "0.27", "extreme_heat_fraction": "0.26"}
    cold, heat = split_cold_heat(sample)
    assert cold == 4.46 and heat == 0.53, (cold, heat)
    print("selftest OK: cold/heat totals sum the extreme and moderate OWID fractions")


def main():
    log = []
    europe = read_europe()
    log.append("europe: %d countries from Masselot CSV (cold max %.2f)"
               % (len(europe), max(c["cold"] for c in europe.values())))
    na = fetch_north_america(log)

    payload = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "indicator": "share of deaths attributable to temperature (%)",
               "europe": europe, "northAmerica": na}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    sys.stderr.write("---- build log ----\n")
    for line in log:
        sys.stderr.write(line + "\n")
    for code in ("USA", "CAN"):
        if code in na:
            sys.stderr.write("  %s cold %.2f  heat %.2f\n"
                             % (na[code]["name"], na[code]["cold"], na[code]["heat"]))
    sys.stderr.write("wrote %s\n" % os.path.relpath(OUT))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
