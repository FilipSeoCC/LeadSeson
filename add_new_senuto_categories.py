# -*- coding: utf-8 -*-
# Dodaje swiezo zbadane (Senuto get_keywords, real-query) kategorie branz, ktorych nie
# bylo ani w macierzy Senuto, ani w starej tabeli legacy. Kazdy wiersz cytuje dokladna
# fraze i surowe dane trendu, zeby bylo widac podstawe wniosku.
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MATRIX_PATH = BASE_DIR / "output" / "leadseason_macierz_sezonowosci_senuto.xlsx"

NEW_ROWS = [
    {
        "branza_glowna": "Nieruchomości", "podbranza": "Biuro nieruchomości",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "45",
        "senuto_evidence": "Senuto get_keywords (keyword='biuro nieruchomości', narrow). Trend 'biura nieruchomości': 14800->6600 monotonicznie malejacy przez 12 mies. - to raczej trend roczny (spadek popularnosci frazy) niz powtarzalna sezonowosc kalendarzowa. Brak jasnego wzorca szczytu.",
        "liczba_domen": "61",
    },
    {
        "branza_glowna": "B2B / hurt i dystrybucja", "podbranza": "Hurtownia specjalistyczna",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "40",
        "senuto_evidence": "Senuto get_keywords (keyword='hurtownia przemysłowa', narrow). Trend plaski 480-720/mies. bez wyraznego wzorca. Kategoria zbyt ogolna (obejmuje bardzo rozne branze hurtu) - brak spojnego sygnalu sezonowego.",
        "liczba_domen": "48",
    },
    {
        "branza_glowna": "IT / elektronika / automatyka", "podbranza": "Usługi IT i systemy techniczne",
        "sezon_peak_miesiace": "", "sezon_start_miesiac": "", "sezon_end_miesiac": "",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "35",
        "senuto_evidence": "Senuto get_keywords (keyword='informatyk dla firmy', narrow) - wolumen zbyt niski (10-40 wyszukiwan/mies.) i niereprezentatywny dla calej podbranzy (obejmuje tez automatyke przemyslowa, sygnalizacje drogowa itp., nie tylko wsparcie IT). Niska pewnosc wniosku.",
        "liczba_domen": "34",
    },
    {
        "branza_glowna": "BHP / ochrona przeciwpożarowa", "podbranza": "BHP i PPOŻ",
        "sezon_peak_miesiace": "maj, paz", "sezon_start_miesiac": "maj", "sezon_end_miesiac": "paz",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "55",
        "senuto_evidence": "Senuto get_keywords (keyword='odzież robocza bhp', narrow). Trend: szczyty w maju (720) i pazdzierniku (720) vs baza 390-480 w pozostalych miesiacach - zgodne ze zmiana sezonu odziezy ochronnej wiosna/jesien.",
        "liczba_domen": "17",
    },
    {
        "branza_glowna": "Finanse / ubezpieczenia", "podbranza": "Ubezpieczenia i doradztwo finansowe",
        "sezon_peak_miesiace": "sty, lut, mar, kwi, maj", "sezon_start_miesiac": "sty", "sezon_end_miesiac": "maj",
        "czy_sezonowosc_wyrazna": "nie", "confidence_sezonowosci": "40",
        "senuto_evidence": "Senuto get_keywords (keyword='ubezpieczenie samochodu', narrow). Lekko podwyzszony wolumen H1 (33100-40500) vs H2 (27100-33100), ale roznica niewielka - slaba, nie wyrazna sezonowosc.",
        "liczba_domen": "11",
    },
    {
        "branza_glowna": "Rolnictwo / maszyny i zaopatrzenie", "podbranza": "Zaopatrzenie rolnictwa",
        "sezon_peak_miesiace": "paz", "sezon_start_miesiac": "paz", "sezon_end_miesiac": "paz",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "65",
        "senuto_evidence": "Senuto get_keywords (keyword='sklep rolniczy', narrow). Wyrazny szczyt w pazdzierniku (12100) vs baza 5400-8100 w pozostalych miesiacach - zgodne z sezonem zbiorow/przygotowan do zimy w rolnictwie.",
        "liczba_domen": "9",
    },
    {
        "branza_glowna": "Transport / spedycja", "podbranza": "Transport drogowy",
        "sezon_peak_miesiace": "mar, wrz, paz, lis, gru", "sezon_start_miesiac": "mar", "sezon_end_miesiac": "gru",
        "czy_sezonowosc_wyrazna": "tak", "confidence_sezonowosci": "55",
        "senuto_evidence": "Senuto get_keywords (keyword='firma transportowa', narrow). Szczyt w marcu (14800) i wrzesien-grudzien (9900-12100), wyrazny spadek w wakacje czerwiec-sierpien (5400-9900) - typowy wzorzec mniejszej aktywnosci B2B w okresie urlopowym.",
        "liczba_domen": "69",
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
            "senuto_query_type": "keyword",
            "senuto_queries_used": "1-2",
            "sezon_peak_miesiace": item["sezon_peak_miesiace"],
            "sezon_start_miesiac": item["sezon_start_miesiac"],
            "sezon_end_miesiac": item["sezon_end_miesiac"],
            "czy_sezonowosc_wyrazna": item["czy_sezonowosc_wyrazna"],
            "confidence_sezonowosci": item["confidence_sezonowosci"],
            "senuto_evidence": item["senuto_evidence"],
            "status": "NOWA_SENUTO_RESEARCH",
        }
        rows_to_add.append(row)

    print(f"Dodaje {len(rows_to_add)} nowych wierszy")
    updated = pd.concat([matrix, pd.DataFrame(rows_to_add)], ignore_index=True)
    updated.to_excel(MATRIX_PATH, index=False)
    print(f"Zapisano. Macierz ma teraz {len(updated)} wierszy.")


if __name__ == "__main__":
    main()
