# -*- coding: utf-8 -*-
# Portuje sezonowosc z config/leadseason_seasonality_matrix.csv (39 wierszy, generyczny
# keyword research z cytowanymi zrodlami publicznymi) do nowego schematu macierzy Senuto
# (branza_glowna/podbranza, wynik realnych zapytan domenowych Senuto dla istniejacych 25
# wierszy). Porty sa oznaczone senuto_query_type="legacy_estimate", zeby odroznic je od
# rygorystycznych domenowych zapytan - to nizsza (ale wciaz uzasadniona zrodlem) pewnosc.
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MATRIX_PATH = BASE_DIR / "output" / "leadseason_macierz_sezonowosci_senuto.xlsx"

# (branza_glowna, podbranza, sezon_peak_miesiace, sezon_start, sezon_end, confidence, evidence, liczba_domen)
PORTED_ROWS = [
    ("Gastronomia / restauracje / eventy", "Restauracje",
     "maj, cze, lip, sie, wrz, gru", "maj", "gru", 80,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=restaurant, zrodlo: poradnikrestauratora.pl, confidence=80).", 269),
    ("Gastronomia / restauracje / eventy", "Catering i eventy",
     "lis, gru", "lis", "gru", 75,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=catering/event_venue, zrodlo: horecatrends.pl, confidence=75-80, usredniono).", 26),
    ("Budownictwo / remonty", "Remonty ogólnobudowlane",
     "mar, kwi, maj, cze, lip, sie, wrz, paz", "mar", "paz", 65,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=general_contractor, confidence=65).", 221),
    ("Budownictwo / remonty", "Dachy i elewacje",
     "mar, kwi, maj, cze, lip, sie, wrz, paz", "mar", "paz", 60,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=roofing_contractor, confidence=60).", 90),
    ("Budownictwo / instalacje", "Instalacje grzewcze i klimatyzacyjne",
     "maj, cze, lip, sie, wrz", "maj", "wrz", 70,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=air_conditioning_contractor/hvac_contractor, zrodlo: usredniono confidence 70-85).", 122),
    ("Budownictwo / instalacje", "Instalacje elektryczne",
     "mar, kwi, maj, cze, lip, sie, wrz, paz", "mar", "paz", 60,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=electrician, confidence=60).", 19),
    ("Medycyna / stomatologia / beauty", "Stomatologia",
     "sty, lut, mar, kwi, maj, cze, wrz, paz, lis", "sty", "lis", 55,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=dentist, caly rok z pikami przed wakacjami/koncem roku, confidence=55).", 63),
    ("Medycyna / stomatologia / beauty", "Gabinety lekarskie",
     "sty, lut, mar, kwi, maj, cze, wrz, paz, lis", "sty", "lis", 50,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=doctor, confidence=50).", 96),
    ("Medycyna / stomatologia / beauty", "Salony urody",
     "mar, kwi, maj, wrz, paz, lis, gru", "mar", "gru", 70,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=beauty_salon/hair_care/spa, usredniono confidence 65-70).", 35),
    ("Ogrody / usługi ogrodnicze", "Pielęgnacja ogrodów",
     "sty, lut, mar, kwi, maj, cze, wrz", "sty", "wrz", 70,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=landscaper, confidence=70).", 72),
    ("Ogrody / usługi ogrodnicze", "Sklep i centrum ogrodnicze",
     "sty, lut, mar, kwi, maj, cze, lip, sie", "sty", "sie", 80,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=garden_center, confidence=80).", 30),
    ("Edukacja / kursy / szkoły językowe", "Szkoły językowe",
     "sty, lut, cze, lip, sie, wrz, paz", "cze", "paz", 80,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=language_school/school, confidence=80).", 54),
    ("Edukacja / kursy", "Szkoły i kursy",
     "sty, lut, cze, lip, sie, wrz, paz", "cze", "paz", 65,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=school/university, usredniono confidence 65-80).", 39),
    ("Motoryzacja / opony / wulkanizacja", "Serwis samochodowy",
     "mar, kwi, paz, lis", "mar", "lis", 90,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=car_repair, confidence=90).", 57),
    ("Motoryzacja / opony / wulkanizacja", "Sprzedaż opon i części",
     "mar, kwi, paz, lis", "mar", "lis", 85,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=auto_parts_store, confidence=85).", 21),
    ("Motoryzacja", "Serwis samochodowy",
     "mar, kwi, paz, lis", "mar", "lis", 90,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=car_repair, confidence=90) - wariant nazwy branzy bez podkategorii opony/wulkanizacja.", 20),
    ("Motoryzacja", "Sprzedaż pojazdów i części",
     "mar, kwi, paz, lis", "mar", "lis", 85,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=auto_parts_store, confidence=85) - wariant nazwy branzy.", 11),
    ("E-commerce / wyposażenie domu", "Sklep z wyposażeniem domu",
     "wrz, paz, lis, gru", "wrz", "gru", 70,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=home_goods_store/furniture_store/store, usredniono confidence 55-85).", 66),
    ("Hotel / noclegi / turystyka", "Baza noclegowa",
     "lut, mar, kwi, lip, sie, wrz, paz, lis, gru", "lut", "gru", 75,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=hotel/lodging/guest_house, confidence=75).", 52),
    ("Przeprowadzki / transport lokalny", "Przeprowadzki",
     "mar, kwi, maj, cze, lip, sie, wrz, lis, gru", "mar", "gru", 55,
     "Portowane z config/leadseason_seasonality_matrix.csv (google_type=moving_company/storage, confidence=55).", 8),
]


def main():
    matrix = pd.read_excel(MATRIX_PATH, dtype=str, keep_default_na=False)
    existing_pairs = set(zip(matrix["branza_glowna"], matrix["podbranza"]))

    new_rows = []
    skipped = []
    for branza, podbranza, peak, start, end, confidence, evidence, liczba_domen in PORTED_ROWS:
        if (branza, podbranza) in existing_pairs:
            skipped.append((branza, podbranza))
            continue
        new_rows.append({
            "branza_glowna": branza,
            "podbranza": podbranza,
            "usluga_glowna": "",
            "model_b2b_b2c": "",
            "liczba_rekordow": str(liczba_domen),
            "liczba_domen": str(liczba_domen),
            "domen_z_danymi_senuto": "0",
            "reprezentatywne_domeny": "",
            "reprezentatywne_frazy": "",
            "senuto_query_type": "legacy_estimate",
            "senuto_queries_used": "0",
            "sezon_peak_miesiace": peak,
            "sezon_start_miesiac": start,
            "sezon_end_miesiac": end,
            "czy_sezonowosc_wyrazna": "tak",
            "confidence_sezonowosci": str(confidence),
            "senuto_evidence": evidence,
            "status": "PORTED_LEGACY",
        })

    print(f"Nowych wierszy do dodania: {len(new_rows)}")
    if skipped:
        print(f"Pominieto (juz istnieja w macierzy): {skipped}")

    updated = pd.concat([matrix, pd.DataFrame(new_rows)], ignore_index=True)
    updated.to_excel(MATRIX_PATH, index=False)
    print(f"Zapisano. Macierz Senuto ma teraz {len(updated)} wierszy (bylo {len(matrix)}).")


if __name__ == "__main__":
    main()
