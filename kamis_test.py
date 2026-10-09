"""Collect last 30 days of KAMIS daily wholesale and retail prices.
Enumerates category/item codes because the API returns zero for unfiltered items.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

key = os.environ.get("KAMIS_API_KEY", "").strip()
if not key:
    sys.exit("KAMIS_API_KEY is not configured")
today = datetime.date.today()
start = today - datetime.timedelta(days=30)
base = "https://apis.data.go.kr/B552845/perDay/price"
outdir = Path("data")
outdir.mkdir(exist_ok=True)
records = []
summary = []
errors = []
calls = 0
# Enumerate all three-digit item codes for each published category.
# Category is required: category-only and no-item queries returned zero.
for category in (100, 200, 300, 400, 500, 600):
    for item in range(category + 1, category + 100):
        for sale_type in ("01", "02"):
            page = 1
            while True:
                params = {
                    "serviceKey": urllib.parse.unquote(key),
                    "returnType": "JSON",
                    "pageNo": str(page),
                    "numOfRows": "1000",
                    "cond[exmn_ymd::GTE]": start.strftime("%Y%m%d"),
                    "cond[exmn_ymd::LTE]": today.strftime("%Y%m%d"),
                    "cond[se_cd::EQ]": sale_type,
                    "cond[ctgry_cd::EQ]": str(category),
                    "cond[item_cd::EQ]": str(item),
                }
                url = base + "?" + urllib.parse.urlencode(params)
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(url, headers={"User-Agent": "Deulsseok-KAMIS/1.0"}),
                        timeout=30,
                    ) as response:
                        payload = json.loads(response.read().decode("utf-8-sig"))
                    header = payload.get("response", {}).get("header", {})
                    if str(header.get("resultCode", "")) not in ("0", "00", "NORMAL_SERVICE"):
                        raise ValueError(str(header.get("resultMsg", "API error")))
                    body = payload.get("response", {}).get("body", {})
                    total = int(body.get("totalCount") or 0)
                    raw = (body.get("items") or {}).get("item") or []
                    batch = raw if isinstance(raw, list) else [raw]
                    records.extend(batch)
                    calls += 1
                    if page == 1 and total:
                        summary.append({"category": category, "item": item, "sale_type": sale_type, "total": total})
                    if page * 1000 >= total or not batch:
                        break
                    page += 1
                except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                    errors.append({"category": category, "item": item, "sale_type": sale_type, "page": page, "error": str(exc)[:160]})
                    break
            if len(summary) and len(summary) % 20 == 0:
                print("Collected matches:", len(summary), "records:", len(records), flush=True)
    print("Category completed:", category, "records:", len(records), "calls:", calls, flush=True)
    (outdir / "kamis_all_prices_30d.json").write_text(
        json.dumps({"from": str(start), "to": str(today), "records": records, "summary": summary, "errors": errors}, ensure_ascii=False),
        encoding="utf-8",
    )
print("DONE:", len(records), "records;", len(summary), "item/type matches;", len(errors), "errors")
if not records:
    sys.exit("No KAMIS prices collected")
if errors:
    sys.exit("Some KAMIS requests failed; partial results saved, check errors")
