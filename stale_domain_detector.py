# -*- coding: utf-8 -*-
STALE_PATTERNS = [
    "domena jest zaparkowana", "domain is parked", "buy this domain", "domena na sprzedaż",
    "oferta sprzedaży domeny", "cena domeny", "kup domenę", "domena do kupienia",
    "aftermarket.pl", "this domain may be for sale", "sedo domain parking",
    "strona nieaktywna", "strona w trakcie zmian", "under construction", "coming soon",
    "w budowie", "domain suspended", "account suspended", "temporarily unavailable",
]


def detect_stale(row):
    text = " ".join(
        str(row.get(field, "") or "") for field in ["title", "meta_description", "body_text_sample"]
    ).lower()
    for pattern in STALE_PATTERNS:
        if pattern in text:
            return pattern
    return ""
