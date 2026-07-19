#!/usr/bin/env python3
"""
TED Altın İhale Tarayıcısı
Kategoriler: kurumsal tekstil, mobilya/yatak, yol tuzu
Çalışma: GitHub Actions ile her gün; çıktı: docs/data.json (GitHub Pages okur)
"""
import json
import datetime
import pathlib
import sys

import requests

API_URL = "https://api.ted.europa.eu/v3/notices/search"

# Kategori -> CPV kökleri (TED sorgusunda wildcard olarak kullanılır)
CATEGORIES = {
    "Kurumsal Tekstil": ["3951*", "3952*", "1821*", "1831*", "39518*"],
    "Mobilya & Yatak":  ["3910*", "3911*", "3914*", "39143*"],
    "Yol Tuzu":         ["34927*", "349271*"],
}

# İlk sürümde taranan ülkeler (genişletmek için kod ekle)
COUNTRIES = ["POL", "CZE", "SVK", "ROU", "HUN", "BEL", "NLD", "DEU", "FRA", "LTU", "LVA", "EST"]

FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "deadline-receipt-tender-date-lot",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "publication-date",
    "links",
]


def build_query(cpv_patterns, days_back=7):
    since = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%Y%m%d")
    cpv_expr = " OR ".join(f"classification-cpv={p}" for p in cpv_patterns)
    country_expr = " OR ".join(f"buyer-country={c}" for c in COUNTRIES)
    # Sadece aktif ihale ilanları (contract notice), sonuç ilanları değil
    return (
        f"({cpv_expr}) AND ({country_expr}) "
        f"AND publication-date>={since} AND notice-type IN (cn-standard cn-social)"
    )


def search(query, limit=50):
    payload = {
        "query": query,
        "fields": FIELDS,
        "limit": limit,
        "page": 1,
        "scope": "ACTIVE",
    }
    r = requests.post(API_URL, json=payload, timeout=30,
                      headers={"Content-Type": "application/json",
                               "User-Agent": "ted-gold-scanner/0.1"})
    r.raise_for_status()
    return r.json().get("notices", [])


def first(v):
    """TED alanları bazen liste/dict döner; ilk okunur değeri çek."""
    if isinstance(v, list):
        return first(v[0]) if v else None
    if isinstance(v, dict):
        # çok dilli alan: {"eng": [...], "pol": [...]} -> herhangi birini al
        for _, val in v.items():
            return first(val)
        return None
    return v


def normalize(notice, category):
    pub_no = first(notice.get("publication-number"))
    links = notice.get("links") or {}
    html_links = links.get("html") or {}
    url = None
    if isinstance(html_links, dict):
        url = html_links.get("ENG") or next(iter(html_links.values()), None)
    if not url and pub_no:
        url = f"https://ted.europa.eu/en/notice/-/detail/{pub_no}"
    return {
        "category": category,
        "id": pub_no,
        "title": first(notice.get("notice-title")),
        "buyer": first(notice.get("buyer-name")),
        "country": first(notice.get("buyer-country")),
        "cpv": notice.get("classification-cpv"),
        "deadline": first(notice.get("deadline-receipt-tender-date-lot")),
        "value": first(notice.get("estimated-value-lot")),
        "currency": first(notice.get("estimated-value-cur-lot")),
        "published": first(notice.get("publication-date")),
        "url": url,
    }


def main():
    out = {"generated": datetime.datetime.utcnow().isoformat() + "Z",
           "items": [], "errors": []}
    for category, cpvs in CATEGORIES.items():
        try:
            notices = search(build_query(cpvs))
            for n in notices:
                out["items"].append(normalize(n, category))
        except Exception as e:
            # Hata olsa da diğer kategoriler denensin; hata sayfada görünür
            out["errors"].append({"category": category, "error": str(e)[:500]})

    # Son teklif tarihi yaklaşana göre sırala (tarihsizler sona)
    out["items"].sort(key=lambda x: (x["deadline"] is None, x["deadline"] or ""))

    dest = pathlib.Path(__file__).parent / "docs" / "data.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out['items'])} ihale yazıldı, {len(out['errors'])} hata.")
    if out["errors"]:
        print(json.dumps(out["errors"], indent=1)[:1000], file=sys.stderr)


if __name__ == "__main__":
    main()
