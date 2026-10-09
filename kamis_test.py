"""KAMIS public-data API connectivity test. Requires KAMIS_API_KEY secret."""
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

key = os.environ.get("KAMIS_API_KEY", "").strip()
if not key:
    sys.exit("KAMIS_API_KEY GitHub Actions secret is not set.")
today = datetime.date.today()
start = today - datetime.timedelta(days=30)
params = {
    "serviceKey": urllib.parse.unquote(key),
    "returnType": "JSON",
    "pageNo": "1",
    "numOfRows": "1000",
    "cond[exmn_ymd::GTE]": start.strftime("%Y%m%d"),
    "cond[exmn_ymd::LTE]": today.strftime("%Y%m%d"),
}
params["cond[se_cd::EQ]"] = "01"
url = "https://apis.data.go.kr/B552845/perDay/price?" + urllib.parse.urlencode(params)
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Deulsseok-KAMIS/1.0"}), timeout=30) as response:
        payload = response.read().decode("utf-8-sig")
except urllib.error.HTTPError as exc:
    sys.exit(f"API HTTP error: status={exc.code}, reason={exc.reason}")
except (urllib.error.URLError, TimeoutError) as exc:
    sys.exit(f"API connection error: {type(exc).__name__}, reason={getattr(exc, 'reason', str(exc))}")
try:
    data = json.loads(payload)
except json.JSONDecodeError:
    sys.exit("API returned a non-JSON response. Check the workflow log and API approval.")
header = data.get("response", {}).get("header", {}) if isinstance(data, dict) else {}
if not header or str(header.get("resultCode", "")) not in ("00", "0", "NORMAL_SERVICE"):
    sys.exit("API error: " + str(header.get("resultMsg", "unknown")))
Path("data").mkdir(exist_ok=True)
Path("data/kamis_connection_test.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("KAMIS API response saved. Top-level fields:", list(data) if isinstance(data, dict) else type(data).__name__)
