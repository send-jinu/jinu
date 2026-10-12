#!/usr/bin/env python3
"""Read-only live verification of Korea Consumer Agency Champrice GW API.
Requires CHAMPRICE_SERVICE_KEY. Never logs the secret or authenticated URL.
"""
import json
import os
import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BASE = "https://apis.data.go.kr/B551919/ProductPriceInfoService"
OUTPUT = Path("champrice/verification-result.json")
LIMIT = 8 * 1024 * 1024


def fetch_xml(endpoint, params):
    key = os.getenv("CHAMPRICE_SERVICE_KEY", "").strip()
    if not key:
        raise RuntimeError("GitHub Actions secret CHAMPRICE_SERVICE_KEY is missing")
    url = BASE + "/" + endpoint + "?" + urlencode({"ServiceKey": unquote(key), **params})
    req = Request(url, headers={"Accept": "application/xml,text/xml,*/*",
                                "User-Agent": "Deulsseok-Champrice-Verify/1.0"})
    try:
        with urlopen(req, timeout=30) as res:
            data = res.read(LIMIT + 1)
    except HTTPError as exc:
        raise RuntimeError(f"API HTTP {exc.code} on {endpoint}") from None
    except (URLError, TimeoutError):
        raise RuntimeError(f"API network error on {endpoint}") from None
    if len(data) > LIMIT:
        raise RuntimeError("Response exceeds 8 MB; pagination may be required")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise RuntimeError(f"Non-XML response from {endpoint}") from None
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        value = (el.text or "").strip()
        if tag in {"returnauthmsg", "errormsg", "errormessage"} and value:
            raise RuntimeError(f"Gateway error on {endpoint}: {value[:120]}")
        if tag in {"resultcode", "returnreasoncode"} and value not in {"00", "0", "000", "SUCCESS", "success"}:
            message = next(((x.text or "").strip() for x in root.iter() if x.tag.rsplit("}", 1)[-1].lower() in {"resultmsg", "returnauthmsg", "errormsg"}), "")
            raise RuntimeError(f"API result code on {endpoint}: {value[:40]}; message: {message[:140]}")
    return root


def items(root):
    return [{c.tag.rsplit("}", 1)[-1]: (c.text or "").strip()
             for c in el if len(c) == 0}
            for el in root.iter() if el.tag.rsplit("}", 1)[-1].lower() == "item"]


def main():
    products = items(fetch_xml("getProductInfoSvc.do", {}))
    if not products:
        raise RuntimeError("No product <item> rows; inspect the actual response schema")
    named = [r for r in products if r.get("goodId") and any(
        word in r.get("goodName", "") for word in ("소면", "골뱅이", "고추장", "간장")
    )]
    selected = []
    seen = set()
    for product in named[:4] + products[-5:] + products[:2]:
        pid = product.get("goodId")
        if pid and pid not in seen:
            seen.add(pid)
            selected.append(product)
        if len(selected) >= 5:
            break
    if not selected:
        raise RuntimeError("Product response lacks goodId; field mapping must be confirmed")
    print("Product listing OK; count:", len(products), flush=True)

    today = datetime.date.today()
    recent = [today - datetime.timedelta(days=i) for i in range(28)
              if (today - datetime.timedelta(days=i)).weekday() in (2, 3)]
    date_options = [d.strftime("%Y%m%d") for d in recent[:5]]
    # The API rejects requests without a valid survey date. Probe recent survey days.
    # Try the alternate date formatting once in case the gateway expects ISO format.
    date_options.insert(1, recent[0].isoformat())
    failures = []
    prices = []
    good_id = ""
    survey_date = ""
    for product in selected:
        pid = product["goodId"]
        for day in date_options:
            try:
                prices = items(fetch_xml("getProductPriceInfoSvc", {
                    "goodId": pid, "goodInspectDay": day
                }))
            except RuntimeError as exc:
                failures.append({"goodId": pid, "date": day, "error": str(exc)[:160]})
                continue
            good_id = pid
            survey_date = day
            print("Price endpoint responded OK; goodId:", pid, "date:", day,
                  "price rows:", len(prices), flush=True)
            if prices:
                break
        if prices:
            break
    if not prices:
        print("Recent survey dates tried:", ", ".join(date_options), flush=True)
        for failure in failures[:8]:
            print("Rejected date:", failure["date"], "goodId:", failure["goodId"],
                  failure["error"], flush=True)
        raise RuntimeError("No nonempty price response for sampled products and dates")
    result = {
        "source": "한국소비자원_생필품 가격 정보_GW",
        "verified_live": True,
        "products": {
            "count_in_response": len(products),
            "field_names": sorted({k for r in products for k in r}),
            "sample": [{k: r[k] for k in ("goodId", "goodName", "goodMaker") if k in r}
                       for r in products[:3]],
        },
        "prices": {
            "sample_good_id": good_id,
            "survey_date": survey_date,
            "count_in_response": len(prices),
            "field_names": sorted({k for r in prices for k in r}),
            "sample": [{k: r[k] for k in ("goodId", "goodPrice", "goodInspectDay", "entpId") if k in r}
                       for r in prices[:3]],
        },
        "warnings": [] if prices else ["Selected product has no price records; try another goodId"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE API CHECK: OK")
    print("Products returned:", len(products), "Price records:", len(prices))
    print("Result saved:", OUTPUT)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(f"LIVE API CHECK FAILED: {exc}") from None
