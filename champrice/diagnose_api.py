#!/usr/bin/env python3
"""Safe schema probe: prints tag counts only, never API keys or URLs."""
from collections import Counter
from pathlib import Path
import json
from verify_api import fetch_xml, items

probes = [
    ("products", "getProductInfoSvc.do", {}),
    ("stores", "getStoreInfoSvc.do", {}),
    ("standards", "getStandardInfoSvc.do", {}),
    ("prices-by-product", "getProductPriceInfoSvc", {"goodId": "821", "goodInspectDay": "20260910"}),
    ("prices-by-store", "getProductPriceInfoSvc", {"entpId": "115", "goodInspectDay": "20260910"}),
    ("prices-by-store-latest", "getProductPriceInfoSvc", {"entpId": "115", "goodInspectDay": "20261008"}),
]
catalog = {}
for label, endpoint, params in probes:
    try:
        root = fetch_xml(endpoint, params)
        counts = Counter(el.tag.rsplit("}", 1)[-1] for el in root.iter())
        msg = next(((el.text or "").strip() for el in root.iter()
                    if el.tag.rsplit("}", 1)[-1] == "resultMsg"), "")
        rows = items(root)
        if label in ("products", "stores"):
            catalog[label] = rows
        print(label, "rows:", len(rows), "tags:", counts.most_common(14),
              "resultMsg:", msg[:80], flush=True)
    except RuntimeError as exc:
        print(label, "ERROR:", str(exc)[:180], flush=True)

if catalog:
    out = Path("champrice/catalog.json")
    out.write_text(json.dumps({"source": "한국소비자원 참가격 GW",
                               "products": catalog.get("products", []),
                               "stores": catalog.get("stores", [])},
                              ensure_ascii=False), encoding="utf-8")
    print("Catalog artifact:", out, "products:", len(catalog.get("products", [])),
          "stores:", len(catalog.get("stores", [])), flush=True)
