# -*- coding: utf-8 -*-
from stale_domain_detector import detect_stale


def test_detect_stale_finds_domain_for_sale_pattern():
    row = {"title": "Domena na sprzedaż", "meta_description": "", "body_text_sample": ""}
    assert detect_stale(row) == "domena na sprzedaż"


def test_detect_stale_returns_empty_for_normal_site():
    row = {"title": "Restauracja Pod Lipą", "meta_description": "Menu i rezerwacje", "body_text_sample": "Zapraszamy"}
    assert detect_stale(row) == ""
