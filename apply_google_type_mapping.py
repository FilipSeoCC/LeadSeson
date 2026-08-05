# -*- coding: utf-8 -*-
# Warstwa 1: deterministyczny slownik google_type (places_primary_type) -> branza/podbranza,
# uzywajacy kanonicznych nazw z macierzy Senuto (zeby unikac driftu nazewnictwa jak przy
# recznej klasyfikacji testu 100). Stosowany TYLKO do rekordow z places_status=OK i
# pustym ai_branza_glowna - nie nadpisuje istniejacej klasyfikacji.
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"

# generyczne typy Google - NIE mapujemy deterministycznie, ida do Warstwy 2 (recznej)
GENERIC_TYPES = {
    "service", "general_contractor", "manufacturer", "store", "consultant", "supplier",
    "corporate_office", "point_of_interest", "health", "food", "general_store",
    "association_or_organization", "non_profit_organization", "research_institute",
    "local_government_office", "government_office", "embassy", "",
}

# google_type -> (branza_glowna, podbranza, confidence)
TYPE_MAPPING = {
    "car_repair": ("Motoryzacja / opony / wulkanizacja", "Serwis samochodowy", 80),
    "car_wash": ("Motoryzacja / opony / wulkanizacja", "Serwis samochodowy", 60),
    "tire_shop": ("Motoryzacja / opony / wulkanizacja", "Sprzedaż opon i części", 80),
    "auto_parts_store": ("Motoryzacja / opony / wulkanizacja", "Sprzedaż opon i części", 80),
    "car_dealer": ("Motoryzacja", "Sprzedaż pojazdów i części", 75),
    "truck_dealer": ("Motoryzacja", "Sprzedaż pojazdów i części", 70),
    "car_rental": ("Motoryzacja", "Wynajem samochodów", 80),

    "lawyer": ("Prawo / kancelarie prawne", "Kancelarie prawne", 80),

    "accounting": ("Księgowość / biura rachunkowe", "Biura rachunkowe", 80),

    "doctor": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 70),
    "medical_clinic": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 70),
    "medical_center": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 65),
    "physiotherapist": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 70),
    "hospital": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 60),
    "medical_lab": ("Medycyna / stomatologia / beauty", "Gabinety lekarskie", 60),
    "dentist": ("Medycyna / stomatologia / beauty", "Stomatologia", 80),
    "dental_clinic": ("Medycyna / stomatologia / beauty", "Stomatologia", 80),
    "veterinary_care": ("Weterynaria", "Gabinety weterynaryjne", 80),
    "pet_boarding_service": ("Weterynaria", "Gabinety weterynaryjne", 55),
    "pet_care": ("Weterynaria", "Gabinety weterynaryjne", 55),
    "skin_care_clinic": ("Medycyna / stomatologia / beauty", "Salony urody", 75),
    "beauty_salon": ("Medycyna / stomatologia / beauty", "Salony urody", 75),
    "hair_salon": ("Medycyna / stomatologia / beauty", "Salony urody", 75),
    "nail_salon": ("Medycyna / stomatologia / beauty", "Salony urody", 75),
    "massage": ("Medycyna / stomatologia / beauty", "Salony urody", 60),
    "massage_spa": ("Medycyna / stomatologia / beauty", "Salony urody", 60),
    "spa": ("Medycyna / stomatologia / beauty", "Salony urody", 65),
    "barber_shop": ("Medycyna / stomatologia / beauty", "Salony urody", 75),
    "beautician": ("Medycyna / stomatologia / beauty", "Salony urody", 70),
    "foot_care": ("Medycyna / stomatologia / beauty", "Salony urody", 55),
    "body_art_service": ("Medycyna / stomatologia / beauty", "Salony urody", 55),
    "tanning_studio": ("Medycyna / stomatologia / beauty", "Salony urody", 60),

    "finance": ("Finanse / ubezpieczenia", "Ubezpieczenia i doradztwo finansowe", 65),
    "insurance_agency": ("Finanse / ubezpieczenia", "Ubezpieczenia i doradztwo finansowe", 80),
    "bank": ("Finanse / ubezpieczenia", "Ubezpieczenia i doradztwo finansowe", 55),

    "transportation_service": ("Transport / spedycja", "Transport drogowy", 65),
    "taxi_service": ("Transport / spedycja", "Transport drogowy", 55),
    "chauffeur_service": ("Transport / spedycja", "Transport drogowy", 55),
    "airport_shuttle_service": ("Transport / spedycja", "Transport drogowy", 55),
    "shipping_service": ("Transport / spedycja", "Transport drogowy", 60),
    "courier_service": ("Transport / spedycja", "Transport drogowy", 60),
    "moving_company": ("Przeprowadzki / transport lokalny", "Przeprowadzki", 85),
    "storage": ("Przeprowadzki / transport lokalny", "Przeprowadzki", 60),

    "educational_institution": ("Edukacja / kursy", "Szkoły i kursy", 65),
    "school": ("Edukacja / kursy", "Szkoły i kursy", 70),
    "university": ("Edukacja / kursy", "Szkoły i kursy", 65),
    "preschool": ("Edukacja / kursy", "Szkoły i kursy", 65),
    "primary_school": ("Edukacja / kursy", "Szkoły i kursy", 65),
    "secondary_school": ("Edukacja / kursy", "Szkoły i kursy", 65),
    "sports_school": ("Edukacja / kursy", "Szkoły i kursy", 55),
    "child_care_agency": ("Edukacja / kursy", "Szkoły i kursy", 55),

    "hotel": ("Hotel / noclegi / turystyka", "Baza noclegowa", 85),
    "lodging": ("Hotel / noclegi / turystyka", "Baza noclegowa", 80),
    "guest_house": ("Hotel / noclegi / turystyka", "Baza noclegowa", 80),
    "bed_and_breakfast": ("Hotel / noclegi / turystyka", "Baza noclegowa", 80),
    "farmstay": ("Hotel / noclegi / turystyka", "Baza noclegowa", 65),
    "resort_hotel": ("Hotel / noclegi / turystyka", "Baza noclegowa", 80),
    "extended_stay_hotel": ("Hotel / noclegi / turystyka", "Baza noclegowa", 70),
    "inn": ("Hotel / noclegi / turystyka", "Baza noclegowa", 70),
    "camping_cabin": ("Hotel / noclegi / turystyka", "Baza noclegowa", 60),
    "campground": ("Hotel / noclegi / turystyka", "Baza noclegowa", 60),
    "travel_agency": ("Turystyka / wyjazdy", "Biuro podrozy", 80),
    "tour_agency": ("Turystyka / wyjazdy", "Biuro podrozy", 70),
    "tourist_attraction": ("Turystyka / wyjazdy", "Biuro podrozy", 45),

    "restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 80),
    "pizza_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 80),
    "bistro": ("Gastronomia / restauracje / eventy", "Restauracje", 70),
    "italian_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "family_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "sushi_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "polish_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "indian_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "eastern_european_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 70),
    "buffet_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 65),
    "dumpling_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 70),
    "japanese_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 75),
    "asian_restaurant": ("Gastronomia / restauracje / eventy", "Restauracje", 70),
    "kebab_shop": ("Gastronomia / restauracje / eventy", "Restauracje", 70),
    "food_court": ("Gastronomia / restauracje / eventy", "Restauracje", 50),
    "cafe": ("Gastronomia / restauracje / eventy", "Restauracje", 65),
    "coffee_shop": ("Gastronomia / restauracje / eventy", "Restauracje", 65),
    "bar": ("Gastronomia / restauracje / eventy", "Restauracje", 60),
    "pub": ("Gastronomia / restauracje / eventy", "Restauracje", 60),
    "cocktail_bar": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "lounge_bar": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "bakery": ("Gastronomia / restauracje / eventy", "Restauracje", 60),
    "pastry_shop": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "cake_shop": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "dessert_shop": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "candy_store": ("Gastronomia / restauracje / eventy", "Restauracje", 45),
    "chocolate_factory": ("Gastronomia / restauracje / eventy", "Restauracje", 50),
    "coffee_roastery": ("Gastronomia / restauracje / eventy", "Restauracje", 55),
    "catering_service": ("Gastronomia / restauracje / eventy", "Catering i eventy", 80),
    "event_venue": ("Gastronomia / restauracje / eventy", "Catering i eventy", 70),
    "banquet_hall": ("Gastronomia / restauracje / eventy", "Catering i eventy", 65),

    "funeral_home": ("Usługi pogrzebowe", "Zakłady pogrzebowe", 90),
    "cemetery": ("Usługi pogrzebowe", "Zakłady pogrzebowe", 55),

    "real_estate_agency": ("Nieruchomości", "Biuro nieruchomości", 85),
    "condominium_complex": ("Nieruchomości", "Biuro nieruchomości", 50),

    "garden_center": ("Ogrody / usługi ogrodnicze", "Sklep i centrum ogrodnicze", 80),
    "farm": ("Rolnictwo / maszyny i zaopatrzenie", "Zaopatrzenie rolnictwa", 45),
    "ranch": ("Rolnictwo / maszyny i zaopatrzenie", "Zaopatrzenie rolnictwa", 40),

    "plumber": ("Budownictwo / instalacje", "Instalacje sanitarne", 75),
    "electrician": ("Budownictwo / instalacje", "Instalacje elektryczne", 75),
    "roofing_contractor": ("Budownictwo / remonty", "Dachy i elewacje", 75),
    "painter": ("Budownictwo / remonty", "Remonty ogólnobudowlane", 60),
    "locksmith": ("Budownictwo / remonty", "Remonty ogólnobudowlane", 55),
    "home_improvement_store": ("Budownictwo / remonty", "Remonty ogólnobudowlane", 60),
    "hardware_store": ("Budownictwo / remonty", "Remonty ogólnobudowlane", 55),
    "building_materials_store": ("Budownictwo / materiały budowlane", "Materiały i akcesoria budowlane", 80),

    "furniture_store": ("E-commerce / wyposażenie domu", "Sklep z wyposażeniem domu", 75),
    "home_goods_store": ("E-commerce / wyposażenie domu", "Sklep z wyposażeniem domu", 75),

    "clothing_store": ("E-commerce / moda", "Odziez i obuwie", 75),
    "shoe_store": ("E-commerce / moda", "Odziez i obuwie", 75),
    "womens_clothing_store": ("E-commerce / moda", "Odziez i obuwie", 70),
    "sportswear_store": ("E-commerce / moda", "Odziez i obuwie", 60),
    "jewelry_store": ("E-commerce / sklep internetowy", "Jubilerstwo", 80),
    "cosmetics_store": ("E-commerce / moda", "Odziez i obuwie", 55),

    "electronics_store": ("E-commerce / elektronika", "Sklep elektroniczny", 80),
    "telecommunications_service_provider": ("E-commerce / elektronika", "Sklep elektroniczny", 55),
    "toy_store": ("E-commerce / prezenty / wyposazenie domu", "Zabawki i prezenty", 80),

    "sporting_goods_store": ("Sport i rekreacja", "Sklep sportowy", 75),
    "bicycle_store": ("E-commerce / sklep internetowy", "Sklep rowerowy", 80),
    "sports_club": ("Sport i rekreacja", "Sklep sportowy", 50),
    "sports_activity_location": ("Sport i rekreacja", "Sklep sportowy", 45),
    "sports_complex": ("Sport i rekreacja", "Sklep sportowy", 45),
    "fitness_center": ("Fitness / sport / zdrowie", "Silownie i kluby fitness", 80),
    "gym": ("Fitness / sport / zdrowie", "Silownie i kluby fitness", 80),
    "yoga_studio": ("Fitness / sport / zdrowie", "Silownie i kluby fitness", 65),

    "florist": ("Kwiaciarnia / prezenty / okazje", "Kwiaciarnia", 85),

    "insurance_agency_v2_unused": None,  # placeholder removed below
}
TYPE_MAPPING.pop("insurance_agency_v2_unused", None)


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)

    needs_classification = (
        df["places_status"].eq("OK")
        & df["ai_branza_glowna"].astype(str).str.strip().eq("")
    )
    print(f"Kandydaci (Places OK, brak ai_branza_glowna): {needs_classification.sum()}")

    updated_count = 0
    for idx in df[needs_classification].index:
        ptype = str(df.at[idx, "places_primary_type"]).strip()
        if ptype in GENERIC_TYPES or ptype not in TYPE_MAPPING:
            continue
        branza, podbranza, confidence = TYPE_MAPPING[ptype]
        df.at[idx, "ai_branza_glowna"] = branza
        df.at[idx, "ai_podbranza"] = podbranza
        df.at[idx, "ai_confidence"] = str(confidence)
        df.at[idx, "ai_evidence"] = f"Warstwa 1: google_type={ptype} -> {branza}/{podbranza} (deterministyczny slownik)"
        df.at[idx, "classification_source"] = "google_type_mapping"
        updated_count += 1

    print(f"Sklasyfikowano deterministycznie: {updated_count}")
    df.to_excel(CONSOLIDATED_PATH, index=False)
    print("Zapisano.")


if __name__ == "__main__":
    main()
