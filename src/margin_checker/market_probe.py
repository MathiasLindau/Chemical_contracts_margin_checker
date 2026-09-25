"""Call candidate market sources and print what actually comes back.

No files are written. Missing keys are reported, not invented.

    python -m src.margin_checker.market_probe
"""

from __future__ import annotations

import csv
import io
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openpyxl import load_workbook

USER_AGENT = "margin-checker-market-probe"
TIMEOUT = 45


def http_get(url, headers=None):
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        return 0, str(exc.reason).encode()


def ecb_last(flow_key):
    url = (
        "https://data-api.ecb.europa.eu/service/data/"
        + flow_key
        + "?lastNObservations=1"
    )
    status, body = http_get(url, {"Accept": "text/csv"})
    if status != 200:
        return status, None, None, body[:80].decode("utf-8", "replace")
    row = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))[-1]
    return status, row["TIME_PERIOD"], row["OBS_VALUE"], row.get("TITLE", "")


def line(category, name, status, when, value, unit, cadence, note):
    print(
        f"{category:<12} {name:<22} HTTP {status:<3} "
        f"{when or '-':<12} {value or '-':<10} {unit:<12} {cadence:<14} {note}"
    )


def probe():
    print(
        f"{'category':<12} {'series':<22} {'http':<8} "
        f"{'as_of':<12} {'value':<10} {'unit':<12} {'cadence':<14} note"
    )

    status, when, value, title = ecb_last("EXR/D.USD.EUR.SP00.A")
    line("fx", "EURUSD", status, when, value, "USD/EUR", "business day", "ECB, no key")

    status, when, value, title = ecb_last("FM/D.U2.EUR.4F.KR.DFR.LEV")
    line("interest", "ECB_DEPOSIT", status, when, value, "percent", "when changed", "ECB policy rate, no key")

    status, when, value, title = ecb_last("FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA")
    line("interest", "EURIBOR_3M", status, when, value, "percent", "monthly avg", "ECB republication, not live EMMI")

    status, body = http_get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")
    if status == 200:
        row = json.loads(body)["refRates"][0]
        line("interest", "SOFR", status, row["effectiveDate"], str(row["percentRate"]), "percent", "business day", "NY Fed, no key")
    else:
        line("interest", "SOFR", status, "", "", "percent", "business day", "NY Fed failed")

    status, body = http_get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
        "v2/accounting/od/avg_interest_rates?sort=-record_date"
        "&filter=security_desc:eq:Treasury%20Bills&page[size]=1"
    )
    if status == 200:
        row = json.loads(body)["data"][0]
        line(
            "interest",
            "US_TBILL_AVG",
            status,
            row["record_date"],
            row["avg_interest_rate_amt"],
            "percent",
            "monthly",
            "average on outstanding bills, not a market yield",
        )
    else:
        line("interest", "US_TBILL_AVG", status, "", "", "percent", "monthly", "Treasury Fiscal Data failed")

    status, body = http_get(
        "https://api.imf.org/external/sdmx/3.0/data/dataflow/"
        "IMF.RES/PCPS/9.0.0/G001.POILBRE.USD.M?startPeriod=2026-06",
        {"Accept": "application/json"},
    )
    if status == 200:
        payload = json.loads(body)
        times = payload["data"]["structures"][0]["dimensions"]["observation"][0]["values"]
        obs = list(payload["data"]["dataSets"][0]["series"].values())[0]["observations"]
        last_index = str(len(times) - 1)
        # startPeriod can be ignored; take the newest timestamp in 2026.
        newest = max(range(len(times)), key=lambda i: times[i]["value"])
        value = obs[str(newest)][0]
        line("raw", "BRENT_IMF", status, times[newest]["value"], value, "USD/bbl", "monthly", "IMF PCPS, no key")
    else:
        line("raw", "BRENT_IMF", status, "", "", "USD/bbl", "monthly", "IMF failed")

    page_status, page = http_get("https://www.worldbank.org/en/research/commodity-markets")
    match = None
    if page_status == 200:
        match = re.search(
            r"https://thedocs\.worldbank\.org/[^\"']+CMO-Historical-Data-Monthly\.xlsx",
            page.decode("utf-8", "replace"),
        )
    if not match:
        line("raw", "WORLD_BANK", page_status, "", "", "", "monthly", "workbook link missing")
    else:
        file_status, blob = http_get(match.group(0))
        if file_status != 200:
            line("raw", "WORLD_BANK", file_status, "", "", "", "monthly", "workbook download failed")
        else:
            book = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
            sheet = book["Monthly Prices"]
            rows = list(sheet.iter_rows(values_only=True))
            names = list(rows[4])
            updated = str(rows[3][0])
            wanted = {
                "BRENT_WB": "Crude oil, Brent",
                "GAS_EU_WB": "Natural gas, Europe",
                "MAIZE_WB": "Maize",
            }
            units = {"Crude oil, Brent": "USD/bbl", "Natural gas, Europe": "USD/mmbtu", "Maize": "USD/t"}
            last = rows[-1]
            for code, label in wanted.items():
                line(
                    "energy" if code.startswith("GAS") else "raw",
                    code,
                    file_status,
                    str(last[0]),
                    str(last[names.index(label)]),
                    units[label],
                    "monthly",
                    updated,
                )

    status, body = http_get(
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
        "nrg_pc_205?format=JSON&lang=EN&geo=DE&lastTimePeriod=1"
    )
    if status == 200:
        payload = json.loads(body)
        period = next(iter(payload["dimension"]["time"]["category"]["label"].values()))
        line("energy", "POWER_DE_EUROSTAT", status, period, "many bands", "EUR/kWh", "half-year", payload.get("updated", ""))
    else:
        line("energy", "POWER_DE_EUROSTAT", status, "", "", "EUR/kWh", "half-year", "Eurostat failed")

    status, body = http_get("https://api.eia.gov/v2/petroleum/pri/spt/")
    note = "API_KEY_MISSING" if b"API_KEY_MISSING" in body else "no price without EIA_API_KEY"
    line("energy", "BRENT_EIA", status, "", "", "USD/bbl", "daily", note)

    status, body = http_get("https://web-api.tp.entsoe.eu/api?documentType=A44")
    line("energy", "POWER_ENTSOE", status, "", "", "EUR/MWh", "hourly", "needs ENTSOE_SECURITY_TOKEN")

    status, body = http_get("https://search.shaq-logistics.com/api/freight-index")
    if status == 200:
        payload = json.loads(body)
        route = payload["routes"][0]
        rate = route["rates"].get("fcl_40hq") or route["rates"].get("fcl_20gp") or {}
        line(
            "transport",
            "SHAQ_FREIGHT",
            status,
            payload.get("updated", ""),
            str(rate.get("rate_usd", "")),
            "USD/box",
            "claims weekly",
            "unofficial, not a benchmark, do not use",
        )
    else:
        line("transport", "SHAQ_FREIGHT", status, "", "", "USD/box", "unknown", "failed")

    status, body = http_get("https://api.freightos.com/fd_external_apis/fbx/tickers/?tickers=FBX")
    line("transport", "FBX", status, "", "", "USD/FEU", "daily/weekly", "official API needs Freightos secret")

    line("lease", "CONTAINER_PER_DAY", 0, "", "", "USD/day", "none found", "no free robust API answered")


if __name__ == "__main__":
    probe()
