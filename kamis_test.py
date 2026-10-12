"""KAMIS incremental 30-day price collector (actual observed prices only).
Refresh every observed item/type, preserve prior observations, validate all pages,
and report partial data explicitly. A full code-catalogue audit is separate.
"""
import collections
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

key = os.environ.get("KAMIS_API_KEY", "").strip()
if not key:
    raise SystemExit("KAMIS_API_KEY secret missing")
today = datetime.date.today()
cutoff = today - datetime.timedelta(days=30)
data_path = Path("data/kamis_all_prices_30d.json")
data_path.parent.mkdir(exist_ok=True)
old = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
old_records = [r for r in old.get("records", []) if r.get("exmn_ymd", "") >= cutoff.strftime("%Y%m%d")]
if old_records:
    newest = max(datetime.datetime.strptime(r["exmn_ymd"], "%Y%m%d").date() for r in old_records)
    fetch_from = max(cutoff, newest - datetime.timedelta(days=1))
    # Both sale types must be probed even if only one was present previously.
    combos = sorted({(r["ctgry_cd"], r["item_cd"], s) for r in old_records for s in ("01", "02")})
else:
    fetch_from = cutoff
    combos = [(str(cat), str(code), sale)
              for cat in (100, 200, 300, 400, 500, 600)
              for code in range(cat + 1, cat + 100)
              for sale in ("01", "02")]

url_base = "https://apis.data.go.kr/B552845/perDay/price"
record_index = collections.defaultdict(list)
for row in old_records:
    record_index[(row["ctgry_cd"], row["item_cd"], row["se_cd"])].append(row)
errors = []
attempted = 0
completed = 0

def fetch_page(cat, item, sale, page):
    params = {
        "serviceKey": urllib.parse.unquote(key),
        "returnType": "JSON",
        "pageNo": str(page),
        "numOfRows": "1000",
        "cond[exmn_ymd::GTE]": fetch_from.strftime("%Y%m%d"),
        "cond[exmn_ymd::LTE]": today.strftime("%Y%m%d"),
        "cond[se_cd::EQ]": sale,
        "cond[ctgry_cd::EQ]": cat,
        "cond[item_cd::EQ]": item,
    }
    req = urllib.request.Request(
        url_base + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "Deulsseok-KAMIS/2.0"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as res:
                payload = json.loads(res.read().decode("utf-8-sig"))
            hdr = payload.get("response", {}).get("header", {})
            if str(hdr.get("resultCode", "")) not in ("0", "00", "NORMAL_SERVICE"):
                raise ValueError(str(hdr.get("resultMsg", "KAMIS API response error")))
            body = payload["response"]["body"]
            total = int(body.get("totalCount") or 0)
            part = (body.get("items") or {}).get("item") or []
            rows = part if isinstance(part, list) else [part]
            if any(str(r.get("item_cd")) != item or str(r.get("ctgry_cd")) != cat
                   or str(r.get("se_cd")) != sale for r in rows):
                raise ValueError("API returned unexpected category/item/sale code")
            return total, rows
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, KeyError) as exc:
            error = str(exc)[:140]
            if attempt < 2:
                time.sleep(1 + attempt * 2)
    raise RuntimeError(error)

for cat, item, sale in combos:
    attempted += 1
    page = 1
    received = []
    try:
        while True:
            total, part = fetch_page(cat, item, sale, page)
            received.extend(part)
            if len(received) >= total:
                if len(received) != total:
                    raise ValueError("Total count mismatch")
                break
            if not part:
                raise ValueError("Missing API pagination page")
            page += 1
        # Apply replacement only after ALL pages for this combination were validated.
        prev = record_index.get((cat, item, sale), [])
        record_index[(cat, item, sale)] = [
            r for r in prev if r["exmn_ymd"] < fetch_from.strftime("%Y%m%d")
        ] + received
        completed += 1
    except (RuntimeError, ValueError) as exc:
        errors.append({"category": cat, "item": item, "sale_type": sale, "error": str(exc)[:160]})
    if attempted % 30 == 0:
        print("Refresh progress:", attempted, "/", len(combos),
              "errors:", len(errors), flush=True)

records = [r for group in record_index.values() for r in group]
records.sort(key=lambda r: (r["exmn_ymd"], r["ctgry_cd"], r["item_cd"],
                            r["se_cd"], r["vrty_cd"], r["grd_cd"], r["mrkt_cd"]))
natural = [(r["exmn_ymd"], r["se_cd"], r["ctgry_cd"], r["item_cd"],
            r["vrty_cd"], r["grd_cd"], r["mrkt_cd"], r["sgg_cd"],
            r["unit"], r["unit_sz"]) for r in records]
if len(set(natural)) != len(records):
    raise SystemExit("Duplicate natural keys; refusing to overwrite stored data")
if not records:
    raise SystemExit("No real prices available")
totals = collections.Counter((r["ctgry_cd"], r["item_cd"], r["se_cd"]) for r in records)
summary = [{"category": int(cat), "item": int(item), "sale_type": sale, "total": count}
           for (cat, item, sale), count in sorted(totals.items())]
output = {
    "from": str(cutoff), "to": str(today), "records": records,
    "summary": summary, "errors": errors,
    "quality_status": "complete_refresh" if not errors else "partial_refresh",
    "refresh_from": str(fetch_from), "requested_combinations": len(combos),
    "completed_combinations": completed,
    "scope_note": "Known item codes refreshed; official catalogue and processed foods require independent coverage audit"
}
data_path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("SAVED:", len(records), "records;", completed, "/", len(combos),
      "combos; errors:", len(errors), "; status:", output["quality_status"], flush=True)
