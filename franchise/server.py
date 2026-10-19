#!/usr/bin/env python3
"""Small dependency-free server for the franchise sales dashboard.

The public-data key is read from FRANCHISE_SERVICE_KEY.  A key submitted from
the settings tab is kept only in this process, never written to disk, returned
to the browser, or included in logs.  Set FRANCHISE_API_URL to the exact API
operation enabled for your data.go.kr account when the portal gives a
different operation URL.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_API_URL = (
    "https://apis.data.go.kr/1130000/FftcBrandFrcsUnitAvrSalInfo3_Service/"
    "getbrandFrcsBzmnAvrgSls2"
)
SOURCE_NAME = "공정거래위원회 가맹사업거래 공시정보"
SOURCE_URL = "https://www.data.go.kr/"
API_LIMIT = 8 * 1024 * 1024

_runtime_key = ""
_key_lock = threading.Lock()


def configured_key() -> str:
    with _key_lock:
        return _runtime_key or os.getenv("FRANCHISE_SERVICE_KEY", "").strip()


def set_runtime_key(value: str) -> None:
    global _runtime_key
    with _key_lock:
        _runtime_key = value.strip()


def api_url() -> str:
    return os.getenv("FRANCHISE_API_URL", DEFAULT_API_URL).strip()


def public_api_url() -> str:
    """Return the configured endpoint without ever echoing a key in results."""
    parsed = urlparse(api_url())
    if not parsed.query:
        return api_url()
    safe_query = []
    for name, value in parse_qs(parsed.query, keep_blank_values=True).items():
        safe_query.append((name, "[redacted]" if name.lower() in {"servicekey", "apikey", "key"} else value[0]))
    return parsed._replace(query=urlencode(safe_query)).geturl()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _flatten_json(value):
    """Yield dictionaries from common data.go.kr JSON envelopes."""
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        row_markers = {
            "brandname", "brandnm", "brdnm", "franchisename", "frcsnm",
            "annualsales", "annualaveragesales", "avgsales", "avgsalesamt",
            "avrgsalesamt", "avrgslsamt", "unitavrslsamt", "franavgsales", "frcsavgsales", "가맹점연평균매출액",
            "가맹점평균매출액", "storecount", "storecnt", "franchiseCount".lower(),
            "frcscnt", "가맹점수",
        }
        if keys & row_markers:
            yield value
        else:
            for child in value.values():
                yield from _flatten_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_json(child)


def parse_payload(raw: bytes, content_type: str = "") -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        rows = list(_flatten_json(parsed))
        return [row for row in rows if isinstance(row, dict)]
    except json.JSONDecodeError:
        pass
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("공공데이터 응답을 JSON 또는 XML로 읽을 수 없습니다.") from exc
    rows: list[dict] = []
    for node in root.iter():
        children = list(node)
        if children and any(not list(child) for child in children):
            row = {_local_name(child.tag): (child.text or "").strip() for child in children}
            if row:
                rows.append(row)
    return rows


def _value(row: dict, names: tuple[str, ...]) -> str:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _number(value: str | int | float) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace("원", "")
    if not raw:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    number = float(match.group())
    if "억" in raw:
        number *= 100_000_000
    elif "백만" in raw:
        number *= 1_000_000
    elif "천만" in raw:
        number *= 10_000_000
    elif "천" in raw:
        number *= 1_000
    elif "만" in raw:
        number *= 10_000
    return number


def _won(value: str) -> float | None:
    """Amounts in the FTC disclosure API are normally expressed in 천원."""
    number = _number(value)
    if number is None:
        return None
    raw = str(value)
    if not any(unit in raw for unit in ("원", "만", "억", "천", "백만")):
        # The documented FTC disclosure field is 천원. Keep this explicit so
        # a differently configured endpoint can override it by returning a
        # unit in the value.
        number *= 1_000
    return number


def normalize(rows: list[dict], requested_year: str, requested_brand: str) -> dict:
    normalized: list[dict] = []
    for row in rows:
        brand = _value(row, (
            "brandName", "brandNm", "brdNm", "franchiseName", "frcsNm", "brand",
            "브랜드명", "상호", "가맹점명",
        ))
        annual_raw = _value(row, (
            "annualSales", "annualAverageSales", "averageSales", "avgSales", "avgSalesAmt",
            "avrgSalesAmt", "avrgSlsAmt", "unitAvrSlsAmt", "unitAvrgSlsAmt",
            "franAvgSales", "frcsAvgSales", "sales", "salesAmt",
            "salesAmount", "가맹점연평균매출액", "가맹점평균매출액", "연평균매출액",
        ))
        annual = _won(annual_raw)
        store_count_raw = _value(row, (
            "storeCount", "franchiseCount", "storeCnt", "frcsCnt", "branchCnt", "cnt",
            " 가맹점수", "가맹점수", "operatingStoreCount", "opnFrcsCnt", "영업점포수", "가맹점수(개)",
        ))
        store_count = _number(store_count_raw)
        region = _value(row, ("region", "regionName", "sido", "sidoNm", "ctprvnNm", "area", "시도", "지역")) or "전체"
        area_raw = _value(row, ("unitAreaSales", "salesPerArea", "areaSales", "areaSalesAmt", "unitSales", "unitAvrSlsAmt", "unitAvrgSlsAmt", "단위면적당매출액"))
        area_sales = _won(area_raw) if area_raw else None
        area_value = _number(_value(row, ("storeArea", "averageArea", "avgStoreArea", "areaSize", "평균매장면적", "매장면적")))
        if area_sales is None and annual is not None and area_value and area_value > 0:
            area_sales = annual / area_value
            area_source = "계산값: 연평균 매출 ÷ 평균 매장면적"
        else:
            area_source = "원자료" if area_raw else "미제공"
        year = _value(row, ("year", "yr", "businessYear", "baseYear", "공시연도", "기준연도")) or requested_year
        normalized.append({
            "brand": brand or requested_brand or "미확인",
            "year": year,
            "region": region,
            "annual_sales_won": annual,
            "annual_sales_raw": annual_raw,
            "monthly_sales_won": annual / 12 if annual is not None else None,
            "store_count": store_count,
            "area_sales_won": area_sales,
            "area_sales_source": area_source,
            "raw": row,
        })
    if requested_brand:
        needle = requested_brand.casefold()
        matching = [r for r in normalized if needle in r["brand"].casefold()]
        if matching:
            normalized = matching
    if requested_year:
        year_matching = [r for r in normalized if not r["year"] or r["year"] == requested_year]
        if year_matching:
            normalized = year_matching
    region_map: dict[str, list[dict]] = {}
    for row in normalized:
        region_map.setdefault(row["region"], []).append(row)
    regions = []
    for region, group in sorted(region_map.items()):
        sales = [r["annual_sales_won"] for r in group if r["annual_sales_won"] is not None]
        counts = [r["store_count"] for r in group if r["store_count"] is not None]
        regions.append({
            "region": region,
            "store_count": sum(counts) if counts else len(group),
            "average_annual_sales_won": sum(sales) / len(sales) if sales else None,
        })
    return {
        "rows": normalized,
        "regions": regions,
        "requested_brand": requested_brand,
        "year": requested_year,
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "api_endpoint": public_api_url(),
        "calculation_notes": [
            "월평균 매출 = 원자료 연평균 매출 ÷ 12",
            "단위면적당 매출은 원자료가 없고 면적이 있을 때 연평균 매출 ÷ 평균 매장면적으로 계산",
            "매출 원자료의 단위는 공정위 공시 API의 천원을 원으로 환산",
        ],
    }


def fetch(brand: str, year: str) -> dict:
    key = configured_key()
    if not key:
        raise RuntimeError("인증키가 등록되지 않았습니다. 인증키 설정 탭에서 등록하거나 FRANCHISE_SERVICE_KEY를 설정하세요.")
    params = {
        "serviceKey": unquote(key),
        "pageNo": "1",
        "numOfRows": os.getenv("FRANCHISE_PAGE_SIZE", "100"),
        "type": "json",
        "resultType": "json",
        "brandName": brand,
        "brdNm": brand,
        "brand": brand,
        "brandId": brand,
        "brdId": brand,
        "bzmnNo": brand,
        "year": year,
        "yr": year,
        "baseYear": year,
    }
    request_url = api_url() + ("&" if "?" in api_url() else "?") + urlencode(params)
    request = Request(request_url, headers={"Accept": "application/json, application/xml", "User-Agent": "Deulsseok-Franchise/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(API_LIMIT + 1)
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("공공데이터포털 인증키가 유효하지 않거나 API 사용 권한이 없습니다.") from None
        # The old FTC operation URL currently returns a structured 400 rather
        # than a useful HTTP error. Preserve the provider's reason so the UI
        # can distinguish an endpoint/configuration problem from a bad key.
        try:
            provider_body = exc.read(4096).decode("utf-8", errors="replace")
        except Exception:
            provider_body = ""
        if "NO_OPENAPI_SERVICE_ERROR" in provider_body or "서비스가 없거나 폐기" in provider_body:
            raise RuntimeError(
                "공공데이터포털에서 현재 API 주소를 찾지 못했습니다. "
                "데이터포털 문서의 실제 operation URL을 FRANCHISE_API_URL로 설정해야 합니다."
            ) from None
        raise RuntimeError(f"공공데이터 API HTTP 오류({exc.code})") from None
    except (URLError, TimeoutError):
        raise RuntimeError("공공데이터 API에 연결할 수 없습니다. 네트워크와 API 주소를 확인하세요.") from None
    if len(raw) > API_LIMIT:
        raise RuntimeError("API 응답이 너무 큽니다. 조회 범위를 줄여 주세요.")
    try:
        rows = parse_payload(raw, content_type)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None
    if not rows:
        return normalize([], year, brand)
    return normalize(rows, year, brand)


def csv_bytes(result: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["브랜드", "기준연도", "지역", "가맹점수(원자료)", "연평균 매출(원자료, 원)", "월평균 매출(계산값, 원)", "단위면적당 매출(원)", "단위면적당 매출 출처"])
    for row in result["rows"]:
        writer.writerow([
            row["brand"], row["year"], row["region"],
            row["store_count"] if row["store_count"] is not None else "",
            row["annual_sales_won"] if row["annual_sales_won"] is not None else "",
            row["monthly_sales_won"] if row["monthly_sales_won"] is not None else "",
            row["area_sales_won"] if row["area_sales_won"] is not None else "",
            row["area_sales_source"],
        ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "FranchiseDashboard/1.0"

    def log_message(self, fmt, *args):
        # Never log query strings: they can contain a service key.
        print(f"{self.command} {self.path.split('?', 1)[0]} - {fmt % args}")

    def send_json(self, data, status=HTTPStatus.OK):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/config/status":
            self.send_json({"configured": bool(configured_key()), "source": "환경변수 또는 현재 서버 메모리"})
            return
        if parsed.path in ("/api/franchise", "/api/brands"):
            query = parse_qs(parsed.query)
            brand = query.get("brand", [""])[0].strip()
            year = query.get("year", [""])[0].strip()
            if not brand:
                self.send_json({"error": "브랜드명을 입력하세요."}, HTTPStatus.BAD_REQUEST)
                return
            if not re.fullmatch(r"\d{4}", year):
                self.send_json({"error": "조회 기준연도는 4자리 연도로 입력하세요."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json(fetch(brand, year))
            except RuntimeError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        if parsed.path == "/api/franchise.csv":
            query = parse_qs(parsed.query)
            brand, year = query.get("brand", [""])[0].strip(), query.get("year", [""])[0].strip()
            try:
                result = fetch(brand, year)
                payload = csv_bytes(result)
            except RuntimeError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="franchise-{quote(brand)}-{year}.csv"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/config/key":
            self.send_json({"error": "찾을 수 없는 경로입니다."}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16_384:
                raise ValueError
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            key = str(body.get("apiKey", "")).strip()
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"error": "요청 형식이 올바르지 않습니다."}, HTTPStatus.BAD_REQUEST)
            return
        if len(key) < 8:
            self.send_json({"error": "인증키를 입력하세요."}, HTTPStatus.BAD_REQUEST)
            return
        set_runtime_key(key)
        self.send_json({"saved": True, "message": "인증키를 현재 서버 메모리에 등록했습니다. 키 값은 저장하거나 반환하지 않습니다."})

    def serve_static(self, path: str):
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC not in target.parents or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}.get(target.suffix, "application/octet-stream")
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(host: str = "127.0.0.1", port: int = 8000):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Franchise dashboard: http://{host}:{port}")
    print("API key source: FRANCHISE_SERVICE_KEY or the in-memory settings tab")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run(os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000")))
