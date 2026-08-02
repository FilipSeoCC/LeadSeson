# -*- coding: utf-8 -*-
# Dodaje do macierzy Senuto pary (branza, podbranza) wprowadzone przez fale 2
# klasyfikacji (keyword_wave2/llm_wave2), ktore maja istotny wolumen (>=5 domen)
# ale nie maja jeszcze zadnego wiersza w macierzy. W przeciwienstwie do
# add_new_senuto_categories.py (ktore cytuje realne zapytania Senuto), te wiersze
# sa best-effort wnioskowaniem branzowym - nie wywolano tu MCP Senuto. Kazdy wiersz
# ma to jawnie zapisane w senuto_evidence i nizszy confidence_sezonowosci niz wiersze
# oparte o realne dane wyszukiwan.
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MATRIX_PATH = BASE_DIR / "output" / "leadseason_macierz_sezonowosci_senuto.xlsx"

EVIDENCE_PREFIX = "Niezweryfikowane w Senuto (brak dostepu do MCP Senuto w tej sesji) - wnioskowanie branzowe: "

NEW_ROWS = [
    {
        "branza_glowna": "Medycyna / zdrowie", "podbranza": "Psychologia i badania psychologiczne",
        "sezon_peak_miesiace": "sty, wrz", "sezon_start_miesiac": "sty", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "40",
        "evidence": "popyt na wsparcie psychologiczne wzrasta lekko po nowym roku ('postanowienia') i we wrzesniu (powrot do rutyny), ale potrzeba jest w duzej mierze caloroczna.",
        "liczba_domen": "19",
    },
    {
        "branza_glowna": "Budownictwo / remonty", "podbranza": "Usługi geodezyjne",
        "sezon_peak_miesiace": "kwi, maj, cze, wrz", "sezon_start_miesiac": "kwi", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "50",
        "evidence": "geodezja towarzyszy sezonowi budowlanemu (wiosna-jesien), ale wiele zlecen (podzialy, inwentaryzacje) jest niezalezne od pogody.",
        "liczba_domen": "15",
    },
    {
        "branza_glowna": "Optyka", "podbranza": "Salon optyczny",
        "sezon_peak_miesiace": "wrz, gru", "sezon_start_miesiac": "wrz", "sezon_end_miesiac": "gru",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "40",
        "evidence": "lekki wzrost przed rokiem szkolnym (badania wzroku dzieci) i przed swietami (okulary jako prezent), popyt bazowy staly przez caly rok.",
        "liczba_domen": "13",
    },
    {
        "branza_glowna": "Edukacja / kursy / szkoły językowe", "podbranza": "Placówki edukacyjne",
        "sezon_peak_miesiace": "sie, wrz", "sezon_start_miesiac": "sie", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "60",
        "evidence": "zapisy do placowek edukacyjnych (zlobki, przedszkola, szkoly) koncentruja sie przed startem roku szkolnego.",
        "liczba_domen": "12",
    },
    {
        "branza_glowna": "Medycyna / stomatologia / beauty", "podbranza": "Sprzęt rehabilitacyjny i ortopedyczny",
        "sezon_peak_miesiace": "sty", "sezon_start_miesiac": "sty", "sezon_end_miesiac": "sty",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "35",
        "evidence": "popyt raczej caloroczny (potrzeby zdrowotne), lekki wzrost na poczatku roku przy odnawianiu limitow NFZ/refundacji.",
        "liczba_domen": "11",
    },
    {
        "branza_glowna": "Usługi porządkowe / DDD", "podbranza": "Zwalczanie szkodników",
        "sezon_peak_miesiace": "kwi, maj, cze, lip, sie, wrz", "sezon_start_miesiac": "kwi", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "65",
        "evidence": "owady i gryzonie sa najbardziej aktywne w ciepłych miesiacach - to najbardziej oczywisty sezonowy wzorzec w tej puli.",
        "liczba_domen": "9",
    },
    {
        "branza_glowna": "B2B / produkcja przemysłowa", "podbranza": "Kamieniarstwo",
        "sezon_peak_miesiace": "wrz, paz, lis", "sezon_start_miesiac": "wrz", "sezon_end_miesiac": "lis",
        "czy_sezonowosc_wyrazna": "srednio", "confidence_sezonowosci": "50",
        "evidence": "zamowienia na nagrobki i pomniki rosna przed Wszystkich Swietych (1 listopada).",
        "liczba_domen": "9",
    },
    {
        "branza_glowna": "Budownictwo / stolarka otworowa", "podbranza": "Osłony okienne (rolety, żaluzje)",
        "sezon_peak_miesiace": "kwi, maj, cze", "sezon_start_miesiac": "kwi", "sezon_end_miesiac": "cze",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "45",
        "evidence": "wzrost zainteresowania oslonami przeciwslonecznymi przed latem, ale popyt bazowy caloroczny (remonty, nowe budowy).",
        "liczba_domen": "8",
    },
    {
        "branza_glowna": "Budownictwo / stolarka otworowa", "podbranza": "Sprzedaż okien i drzwi",
        "sezon_peak_miesiace": "kwi, maj, cze, lip, sie, wrz", "sezon_start_miesiac": "kwi", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "50",
        "evidence": "montaz okien/drzwi podazza za sezonem budowlanym (wiosna-jesien), rzadziej wykonywany zima.",
        "liczba_domen": "8",
    },
    {
        "branza_glowna": "Usługi profesjonalne / tłumaczenia", "podbranza": "Tłumaczenia przysięgłe",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "25",
        "evidence": "popyt caloroczny, uzalezniony od indywidualnych spraw urzedowych/sadowych klientow, bez wyraznego wzorca kalendarzowego.",
        "liczba_domen": "7",
    },
    {
        "branza_glowna": "B2B / produkcja przemysłowa", "podbranza": "Cięcie / grawerowanie laserowe",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "25",
        "evidence": "uslugi produkcyjne na zamowienie, popyt B2B raczej caloroczny bez wyraznego wzorca sezonowego.",
        "liczba_domen": "7",
    },
    {
        "branza_glowna": "Nieruchomości", "podbranza": "Zarządzanie nieruchomościami",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "25",
        "evidence": "usluga abonamentowa/ciagla, brak podstaw do zalozenia sezonowosci kalendarzowej.",
        "liczba_domen": "6",
    },
    {
        "branza_glowna": "Motoryzacja / opony / wulkanizacja", "podbranza": "Myjnie i detailing",
        "sezon_peak_miesiace": "mar, kwi, wrz", "sezon_start_miesiac": "mar", "sezon_end_miesiac": "wrz",
        "czy_sezonowosc_wyrazna": "srednio", "confidence_sezonowosci": "50",
        "evidence": "wzrost popytu wiosna (po zimowym brudzie/soli drogowej) i jesienia (przed zima).",
        "liczba_domen": "6",
    },
    {
        "branza_glowna": "Finanse / ubezpieczenia", "podbranza": "Kantor wymiany walut",
        "sezon_peak_miesiace": "cze, lip, sie, gru", "sezon_start_miesiac": "cze", "sezon_end_miesiac": "sie",
        "czy_sezonowosc_wyrazna": "srednio", "confidence_sezonowosci": "50",
        "evidence": "sezon urlopowy (wakacje letnie) i wyjazdy swiateczne zwiekszaja popyt na wymiane walut.",
        "liczba_domen": "6",
    },
    {
        "branza_glowna": "B2B / produkcja przemysłowa", "podbranza": "Przetwórstwo mięsne",
        "sezon_peak_miesiace": "gru, kwi", "sezon_start_miesiac": "gru", "sezon_end_miesiac": "kwi",
        "czy_sezonowosc_wyrazna": "srednio", "confidence_sezonowosci": "45",
        "evidence": "wzrost popytu na wyroby miesne przed swietami Bozego Narodzenia i Wielkanoca.",
        "liczba_domen": "5",
    },
    {
        "branza_glowna": "Budownictwo / remonty", "podbranza": "Usługi dekarskie",
        "sezon_peak_miesiace": "kwi, maj, cze, lip, sie, wrz, paz", "sezon_start_miesiac": "kwi", "sezon_end_miesiac": "paz",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "60",
        "evidence": "prace dekarskie wymagaja dobrej pogody i zwykle musza sie zakonczyc przed zima - silny nacisk na wrzesien-pazdziernik.",
        "liczba_domen": "5",
    },
]


def main():
    matrix = pd.read_excel(MATRIX_PATH, dtype=str, keep_default_na=False)
    existing_pairs = set(zip(matrix["branza_glowna"], matrix["podbranza"]))

    rows_to_add = []
    for item in NEW_ROWS:
        key = (item["branza_glowna"], item["podbranza"])
        if key in existing_pairs:
            print(f"Pomijam (juz istnieje): {key}")
            continue
        row = {
            "branza_glowna": item["branza_glowna"],
            "podbranza": item["podbranza"],
            "usluga_glowna": "",
            "model_b2b_b2c": "",
            "liczba_rekordow": item["liczba_domen"],
            "liczba_domen": item["liczba_domen"],
            "domen_z_danymi_senuto": "0",
            "reprezentatywne_domeny": "",
            "reprezentatywne_frazy": "",
            "senuto_query_type": "",
            "senuto_queries_used": "0",
            "sezon_peak_miesiace": item["sezon_peak_miesiace"],
            "sezon_start_miesiac": item["sezon_start_miesiac"],
            "sezon_end_miesiac": item["sezon_end_miesiac"],
            "czy_sezonowosc_wyrazna": item["czy_sezonowosc_wyrazna"],
            "confidence_sezonowosci": item["confidence_sezonowosci"],
            "senuto_evidence": EVIDENCE_PREFIX + item["evidence"],
            "status": "OK",
        }
        rows_to_add.append(row)

    print(f"Dodaje {len(rows_to_add)} nowych wierszy")
    updated = pd.concat([matrix, pd.DataFrame(rows_to_add)], ignore_index=True)
    updated.to_excel(MATRIX_PATH, index=False)
    updated.to_csv(MATRIX_PATH.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"Zapisano. Macierz ma teraz {len(updated)} wierszy.")


if __name__ == "__main__":
    main()
