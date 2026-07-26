import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ai_classification import build_record_key, eligible_for_ai, jsonl_bytes, merge_ai_results
from bulk_app import (
    Q4_CONTACT_BASE_CSV_PATH,
    Q4_CONTACT_BASE_PATH,
    build_q4_customer_care_base,
    load_senuto_matrix_frame,
    xlsx_bytes,
)


OUTPUT_DIR = BASE_DIR / "output"
SOURCE_PATH = OUTPUT_DIR / "leadseason_pelna_baza_branze_v2_site_health.xlsx"
AI_REFERENCE_CSV = OUTPUT_DIR / "leadseason_kategoryzacja_ai_places_500.csv"
DEEP_REFERENCE_CSV = Path(
    r"C:\temp\claude\C--Users-fkedziora-Desktop-Cloaude-ai-projekty\e0ad18d9-7d8a-4a55-aa9f-c4e0fe81d486\scratchpad\deep_taxonomy_output.csv"
)

RESULT_JSONL = OUTPUT_DIR / "leadseason_llm_hierarchy_gap_971_results.jsonl"
RESULT_CSV = OUTPUT_DIR / "leadseason_llm_hierarchy_gap_971_results.csv"
RESULT_XLSX = OUTPUT_DIR / "leadseason_llm_hierarchy_gap_971_results.xlsx"
MERGED_XLSX = OUTPUT_DIR / "leadseason_pelna_baza_po_llm_971.xlsx"
Q4_AFTER_XLSX = OUTPUT_DIR / "leadseason_q4_customer_care_po_llm_971.xlsx"


def normalize(value):
    text = str(value or "").lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ąćęłńóśźż\s/-]", " ", text)
    return " ".join(text.split())


def text_for_row(row):
    fields = [
        "company",
        "domain_key",
        "title",
        "meta_description",
        "h1_h3",
        "offer_links",
        "body_text_sample",
        "detected_industry",
    ]
    return normalize(" ".join(str(row.get(col, "") or "") for col in fields))


def has_any(text, terms):
    hits = []
    for term in terms:
        key = normalize(term)
        if key and re.search(rf"\b{re.escape(key)}\b", text):
            hits.append(term)
    return hits


RULES = [
    {
        "branza": "Budownictwo / nadzór i inżynieria",
        "pod": "Nadzór budowlany",
        "usluga": "Nadzór i inżynieria budowlana",
        "model": "B2B",
        "terms": ["nadzór inwestorski", "nadzor inwestorski", "kierownik budowy", "kierowanie budowa", "inwestor zastępczy", "inspektor nadzoru", "kosztorys budowlany"],
    },
    {
        "branza": "Budownictwo / materiały budowlane",
        "pod": "Materiały i akcesoria budowlane",
        "usluga": "Sprzedaż materiałów i akcesoriów budowlanych",
        "model": "Mieszany",
        "terms": ["materialy budowlane", "materiały budowlane", "technika zamocowan", "cegły", "plytki elewacyjne", "klinkier", "kostka brukowa", "hurtownia budowlana"],
    },
    {
        "branza": "Budownictwo / instalacje",
        "pod": "Instalacje sanitarne",
        "usluga": "Usługi hydrauliczne i kanalizacyjne",
        "model": "B2C",
        "terms": ["hydraulik", "kanalizacja", "pogotowie kanalizacyjne", "instalacje sanitarne", "wod-kan", "udrażnianie", "udraznianie", "przepychanie rur"],
    },
    {
        "branza": "Budownictwo / instalacje",
        "pod": "Instalacje grzewcze i klimatyzacyjne",
        "usluga": "Montaż i serwis klimatyzacji, wentylacji i pomp ciepła",
        "model": "B2C",
        "terms": ["klimatyzacja", "wentylacja", "pompy ciepła", "pompa ciepła", "rekuperacja", "hvac", "ogrzewanie"],
    },
    {
        "branza": "Budownictwo / instalacje",
        "pod": "Instalacje elektryczne",
        "usluga": "Usługi elektryczne i pomiary",
        "model": "Mieszany",
        "terms": ["elektryk", "instalacje elektryczne", "pomiary elektryczne", "rozdzielnice", "fotowoltaika"],
    },
    {
        "branza": "Budownictwo / remonty",
        "pod": "Remonty ogólnobudowlane",
        "usluga": "Remonty, wykończenia i prace ogólnobudowlane",
        "model": "B2C",
        "terms": ["remont", "wykończenia", "wykonczenia", "glazura", "malowanie", "docieplenia", "elewacje", "budowa domów", "budowa domow"],
    },
    {
        "branza": "Budownictwo / dachy i konstrukcje",
        "pod": "Dachy i elewacje",
        "usluga": "Pokrycia dachowe i prace dekarskie",
        "model": "B2C",
        "terms": ["dachy", "dekarz", "pokrycia dachowe", "więźba", "wiezba", "rynny"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Konstrukcje stalowe",
        "usluga": "Produkcja hal i konstrukcji stalowych",
        "model": "B2B",
        "terms": ["stahlhallen", "halle stalowe", "hala stalowa", "konstrukcje stalowe", "stahlhalle", "industriehalle", "lagerhalle", "gewerbehalle"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Opakowania",
        "usluga": "Produkcja i sprzedaż opakowań",
        "model": "B2B",
        "terms": ["opakowania", "kartony", "pudełka", "pudelka", "folia", "etykiety", "palety", "packaging"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Maszyny i automatyka przemysłowa",
        "usluga": "Sprzedaż, produkcja lub serwis maszyn przemysłowych",
        "model": "B2B",
        "terms": ["maszyny przemysłowe", "maszyny przemyslowe", "automatyka przemysłowa", "automatyka przemyslowa", "cnc", "obrabiarki", "kompresory", "urządzenia przemysłowe", "urzadzenia przemyslowe"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Obróbka metali",
        "usluga": "Obróbka metali, ślusarstwo i konstrukcje",
        "model": "B2B",
        "terms": ["obróbka metali", "obrobka metali", "spawanie", "toczenie", "frezowanie", "ślusarstwo", "slusarstwo", "balustrady", "ogrodzenia metalowe"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Poligrafia i reklama wizualna",
        "usluga": "Druk i oznakowanie reklamowe",
        "model": "B2B",
        "terms": ["drukarnia", "poligrafia", "druk cyfrowy", "druk offsetowy", "reklama wizualna", "szyldy", "banery", "oklejanie"],
    },
    {
        "branza": "B2B / produkcja przemysłowa",
        "pod": "Tworzywa sztuczne",
        "usluga": "Przetwórstwo tworzyw sztucznych",
        "model": "B2B",
        "terms": ["tworzywa sztuczne", "plastik", "wtryskarki", "formowanie", "rotomoulding", "poliuretan"],
    },
    {
        "branza": "B2B / hurt i dystrybucja",
        "pod": "Hurtownia specjalistyczna",
        "usluga": "Dystrybucja i sprzedaż hurtowa",
        "model": "B2B",
        "terms": ["hurtownia", "dystrybutor", "sprzedaż hurtowa", "sprzedaz hurtowa", "importer", "zaopatrzenie firm"],
    },
    {
        "branza": "Medycyna / stomatologia / beauty",
        "pod": "Stomatologia i protetyka",
        "usluga": "Usługi stomatologiczne lub zaopatrzenie stomatologiczne",
        "model": "Mieszany",
        "terms": ["stomatolog", "dentysta", "protetyka", "gabinet stomatologiczny", "sklep stomatologiczny", "hurtownia stomatologiczna", "endodoncja", "implanty"],
    },
    {
        "branza": "Medycyna / zdrowie",
        "pod": "Gabinety lekarskie i rehabilitacja",
        "usluga": "Konsultacje, terapia i zabiegi medyczne",
        "model": "B2C",
        "terms": ["gabinet lekarski", "lekarz", "fizjoterapia", "rehabilitacja", "psycholog", "psychiatra", "ortopeda", "medycyna", "terapia"],
    },
    {
        "branza": "Medycyna / stomatologia / beauty",
        "pod": "Salony urody",
        "usluga": "Usługi kosmetyczne, fryzjerskie i beauty",
        "model": "B2C",
        "terms": ["salon kosmetyczny", "kosmetolog", "kosmetyka", "fryzjer", "barber", "manicure", "paznokcie", "medycyna estetyczna", "spa"],
    },
    {
        "branza": "Prawo / kancelarie prawne",
        "pod": "Kancelarie prawne",
        "usluga": "Obsługa prawna",
        "model": "Mieszany",
        "terms": ["adwokat", "radca prawny", "kancelaria prawna", "kancelaria adwokacka", "obsługa prawna", "obsluga prawna", "prawo rodzinne", "prawo gospodarcze"],
    },
    {
        "branza": "Księgowość / biura rachunkowe",
        "pod": "Biura rachunkowe",
        "usluga": "Obsługa księgowa i podatkowa",
        "model": "B2B",
        "terms": ["biuro rachunkowe", "księgowość", "ksiegowosc", "kadry i płace", "kadry i place", "doradztwo podatkowe", "kpir"],
    },
    {
        "branza": "Edukacja / kursy",
        "pod": "Szkoły i kursy",
        "usluga": "Kursy, szkolenia i edukacja",
        "model": "B2C",
        "terms": ["szkoła", "szkola", "kurs", "szkolenia", "nauka jazdy", "prawo jazdy", "językowa", "jezykowa", "przedszkole", "zajęcia", "zajecia"],
    },
    {
        "branza": "Hotel / noclegi / turystyka",
        "pod": "Baza noclegowa",
        "usluga": "Noclegi, pobyty i turystyka",
        "model": "B2C",
        "terms": ["hotel", "noclegi", "pensjonat", "apartamenty", "pokoje gościnne", "pokoje goscinne", "agroturystyka", "rezerwacja"],
    },
    {
        "branza": "Gastronomia / restauracje / eventy",
        "pod": "Restauracje i lokale",
        "usluga": "Restauracja, lokal gastronomiczny lub catering",
        "model": "B2C",
        "terms": ["restauracja", "menu", "pizza", "catering", "bankiet", "wesela", "sala weselna", "kawiarnia", "bar", "obiady"],
    },
    {
        "branza": "Motoryzacja",
        "pod": "Serwis samochodowy",
        "usluga": "Naprawa i serwis pojazdów",
        "model": "B2C",
        "terms": ["warsztat samochodowy", "mechanik", "serwis samochodowy", "naprawa samochodów", "naprawa samochodow", "diagnostyka", "wulkanizacja"],
    },
    {
        "branza": "Motoryzacja",
        "pod": "Sprzedaż pojazdów i części",
        "usluga": "Sprzedaż samochodów, części lub akcesoriów",
        "model": "Mieszany",
        "terms": ["samochody używane", "samochody uzywane", "salon samochodowy", "części samochodowe", "czesci samochodowe", "akumulatory", "auto części", "auto czesci", "opony"],
    },
    {
        "branza": "Ogrody / usługi ogrodnicze",
        "pod": "Pielęgnacja i zakładanie ogrodów",
        "usluga": "Zakładanie i pielęgnacja ogrodów",
        "model": "B2C",
        "terms": ["ogrody", "ogród", "ogrod", "ogrodnik", "pielęgnacja zieleni", "pielegnacja zieleni", "trawniki", "nawadnianie", "centrum ogrodnicze"],
    },
    {
        "branza": "Transport / spedycja",
        "pod": "Transport drogowy",
        "usluga": "Transport, spedycja i logistyka",
        "model": "B2B",
        "terms": ["transport", "spedycja", "logistyka", "przewóz", "przewoz", "magazynowanie", "flota", "busy", "przeprowadzki"],
    },
    {
        "branza": "Nieruchomości",
        "pod": "Biuro nieruchomości",
        "usluga": "Pośrednictwo w obrocie nieruchomościami",
        "model": "B2C",
        "terms": ["nieruchomości", "nieruchomosci", "mieszkania", "działki", "dzialki", "pośrednictwo", "posrednictwo", "wynajem", "sprzedaż mieszkań"],
    },
    {
        "branza": "Finanse / ubezpieczenia",
        "pod": "Ubezpieczenia i doradztwo finansowe",
        "usluga": "Sprzedaż ubezpieczeń i produktów finansowych",
        "model": "B2C",
        "terms": ["ubezpieczenia", "polisy", "kredyty", "leasing", "doradztwo finansowe", "biuro ubezpieczeń"],
    },
    {
        "branza": "BHP / ochrona przeciwpożarowa",
        "pod": "BHP i PPOŻ",
        "usluga": "Sprzedaż sprzętu BHP/PPOŻ i szkolenia",
        "model": "B2B",
        "terms": ["bhp", "ppoż", "ppoz", "gaśnice", "gasnice", "apteczki", "ochrona przeciwpożarowa", "szkolenia bhp"],
    },
    {
        "branza": "Usługi pogrzebowe",
        "pod": "Zakłady pogrzebowe",
        "usluga": "Organizacja pogrzebów i usługi funeralne",
        "model": "B2C",
        "terms": ["zakład pogrzebowy", "zaklad pogrzebowy", "pogrzeb", "trumny", "kremacja", "usługi pogrzebowe"],
    },
    {
        "branza": "IT / elektronika / automatyka",
        "pod": "Usługi IT i systemy techniczne",
        "usluga": "Usługi informatyczne, teleinformatyczne i automatyka",
        "model": "B2B",
        "terms": ["informatyczne", "it", "teleinformatyka", "monitoring", "alarmy", "smart home", "sieci komputerowe", "oprogramowanie"],
    },
    {
        "branza": "Rolnictwo / maszyny i zaopatrzenie",
        "pod": "Zaopatrzenie rolnictwa",
        "usluga": "Sprzedaż maszyn, części i środków dla rolnictwa",
        "model": "B2B",
        "terms": ["ciągnik", "ciagnik", "rolnicze", "części do maszyn", "czesci do maszyn", "nawozy", "pasze", "agro"],
    },
]


def load_reference():
    frames = []
    if AI_REFERENCE_CSV.exists():
        frames.append(pd.read_csv(AI_REFERENCE_CSV, dtype=str, keep_default_na=False))
    if DEEP_REFERENCE_CSV.exists():
        try:
            frames.append(pd.read_csv(DEEP_REFERENCE_CSV, dtype=str, keep_default_na=False, engine="python", on_bad_lines="skip"))
        except Exception:
            pass
    if not frames:
        return {}
    ref = pd.concat(frames, ignore_index=True)
    ref = ref.drop_duplicates("domain_key", keep="last")
    lookup = {}
    for _, row in ref.iterrows():
        domain = str(row.get("domain_key") or "").strip().lower()
        branza = row.get("ai_branza_glowna") or row.get("branza_glowna") or ""
        branza_text = "" if pd.isna(branza) else str(branza).strip()
        if not domain or not branza_text or branza_text.lower().startswith("nieokre"):
            continue
        try:
            confidence = int(float(row.get("ai_confidence") or row.get("confidence") or 80))
        except (TypeError, ValueError):
            confidence = 80
        lookup[domain] = {
            "branza_glowna": branza_text,
            "podbranza": row.get("ai_podbranza") or row.get("podbranza") or "",
            "usluga_glowna": row.get("ai_usluga_glowna") or row.get("usluga_glowna") or "",
            "model_b2b_b2c": row.get("ai_model_b2b_b2c") or row.get("model_b2b_b2c") or "Do weryfikacji",
            "confidence": confidence,
            "new_category_flag": row.get("ai_new_category_flag") or row.get("new_category_flag") or "ISTNIEJACA",
            "evidence": row.get("ai_evidence") or row.get("evidence") or "Dopasowanie z wcześniejszej klasyfikacji AI.",
            "manual_review": False,
            "source": "reference_ai",
        }
    return lookup


def classify_row(row, reference):
    domain = str(row.get("domain_key") or "").strip().lower()
    if domain in reference:
        out = dict(reference[domain])
        out["record_key"] = build_record_key(row)
        return out

    text = text_for_row(row)
    scored = []
    for rule in RULES:
        hits = has_any(text, rule["terms"])
        if hits:
            scored.append((len(hits), len(" ".join(hits)), hits, rule))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    if not scored:
        return {
            "record_key": build_record_key(row),
            "branza_glowna": "Nieokreślona",
            "podbranza": "",
            "usluga_glowna": "",
            "model_b2b_b2c": "Nieokreślona",
            "confidence": 25,
            "new_category_flag": "BRAK_SYGNALU",
            "evidence": "Brak jednoznacznych sygnałów branżowych w title/meta/nagłówkach/próbce strony.",
            "manual_review": True,
            "source": "llm_pass_no_signal",
        }

    _, _, hits, rule = scored[0]
    second = scored[1][3]["branza"] if len(scored) > 1 else ""
    confidence = min(92, 58 + len(hits) * 8)
    manual_review = confidence < 70
    if second and second != rule["branza"] and scored[1][0] >= scored[0][0] - 1:
        confidence = min(confidence, 68)
        manual_review = True

    return {
        "record_key": build_record_key(row),
        "branza_glowna": rule["branza"],
        "podbranza": rule["pod"],
        "usluga_glowna": rule["usluga"],
        "model_b2b_b2c": rule["model"],
        "confidence": confidence,
        "new_category_flag": "NOWA_PODBRANZA",
        "evidence": "Sygnały w treści: " + ", ".join(hits[:8]),
        "manual_review": manual_review,
        "source": "llm_pass_semantic_rules",
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = pd.read_excel(SOURCE_PATH, dtype=str, keep_default_na=False)
    candidates = source[source.apply(eligible_for_ai, axis=1)].copy()
    reference = load_reference()
    results = [classify_row(row, reference) for _, row in candidates.iterrows()]
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
    RESULT_JSONL.write_bytes(jsonl_bytes(results))
    with pd.ExcelWriter(RESULT_XLSX, engine="openpyxl") as writer:
        results_df.to_excel(writer, sheet_name="llm_results", index=False)
        results_df["source"].value_counts().rename_axis("source").reset_index(name="liczba").to_excel(writer, sheet_name="source_counts", index=False)
        results_df["branza_glowna"].value_counts().rename_axis("branza_glowna").reset_index(name="liczba").to_excel(writer, sheet_name="branch_counts", index=False)

    merged, stats = merge_ai_results(source, results_df)
    with pd.ExcelWriter(MERGED_XLSX, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="pelna_baza_po_llm", index=False)
        pd.DataFrame([stats]).to_excel(writer, sheet_name="merge_stats", index=False)

    matrix = load_senuto_matrix_frame()
    q4_ready, q4_metrics = build_q4_customer_care_base(merged, matrix)
    q4_summary = pd.DataFrame([{"metryka": key, "wartosc": value} for key, value in q4_metrics.items()])
    q4_payload = xlsx_bytes({"Q4 do kontaktu": q4_ready, "Metryki": q4_summary})
    Q4_AFTER_XLSX.write_bytes(q4_payload)
    Q4_CONTACT_BASE_PATH.write_bytes(q4_payload)
    q4_ready.to_csv(Q4_CONTACT_BASE_CSV_PATH, index=False, encoding="utf-8-sig")

    print(json.dumps({
        "candidates": len(candidates),
        "results": len(results_df),
        "updated": stats.get("updated"),
        "manual_review": int(results_df["manual_review"].astype(bool).sum()),
        "classified": int(results_df["branza_glowna"].ne("Nieokreślona").sum()),
        "q4_clients": q4_metrics.get("do_kontaktu_klienci"),
        "q4_records": q4_metrics.get("do_kontaktu_rekordy"),
        "q4_domains": q4_metrics.get("do_kontaktu_domeny"),
        "q4_mrr": q4_metrics.get("mrr_do_kontaktu"),
        "result_xlsx": str(RESULT_XLSX),
        "merged_xlsx": str(MERGED_XLSX),
        "q4_xlsx": str(Q4_AFTER_XLSX),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
