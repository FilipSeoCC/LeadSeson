# LeadSeason - plan wdrozenia w Customer Care

## Kontekst biznesowy

LeadSeason ma byc procesem leadowym dla Customer Care w WeNet, czyli dla opiekunow klienta obslugujacych baze MŚP. Celem nie jest samo crawlownie domen, tylko przygotowanie listy klientow, do ktorych warto zadzwonic z konkretnym powodem kontaktu wynikajacym z sezonowosci branzy, aktualnego produktu, segmentu i potencjalu upsell/cross-sell.

Manager Customer Success powinien dostac widok na:

- ktore branze maja teraz lub zaraz sensowny moment kontaktu,
- ktorzy klienci sa priorytetowi,
- jaki produkt/usluge warto proponowac,
- ktory opiekun ma jaka pule leadow,
- czy proces kontaktu jest realnie wykonywany,
- jaka jest skutecznosc rozmow na podstawie danych z Voice AI.

## Aktualne zalozenie danych

Na teraz dostepne sa:

- baza klientow / umow z CRM2 lub eksportu KartaAccount,
- domeny klientow,
- NIP,
- ID klienta,
- ID umowy / detail,
- opiekun klienta,
- pakiet / kod uslugi,
- daty uslugi,
- wartosc / MRR, jezeli jest w eksporcie,
- dane z Voice AI.

Na teraz nie ma:

- logow Avaya,
- pelnej historii wybieranych numerow przez agentow,
- potwierdzonej bazy wszystkich osob kontaktowych z CRM2.

Logi Avaya traktujemy jako etap pozniejszy, nie blokujacy MVP.

## Cel MVP

MVP ma wygenerowac plik dla Customer Care:

- klient,
- domena,
- NIP,
- opiekun,
- segment / MRR,
- wykryta branza,
- sezon / okno kontaktu,
- priorytet Q4,
- proponowany produkt do upsell/cross-sell,
- powod kontaktu,
- krotki skrypt rozmowy,
- status klasyfikacji / confidence,
- sygnaly z Voice AI, jezeli sa dostepne.

Najblizszy fokus: lipiec -> przygotowanie akcji na Q4.

## Dane WWW + Google Places

Generator powinien korzystac z dwoch niezaleznych zrodel wzbogacenia:

1. Crawl strony WWW klienta.
   - title,
   - meta description,
   - naglowki,
   - linki ofertowe,
   - probka tekstu strony.

   To zrodlo zostaje jako material dla AI, ktore ma przygotowac kontekst, powod kontaktu i skrypt rozmowy.

2. Google Places / GMB-like category enrichment.
   - `places_primary_type`,
   - `places_types`,
   - `places_name`,
   - `places_website`,
   - `places_match_confidence`,
   - `places_industry_hint`.

   To zrodlo ma pomagac w rozpoznaniu branzy, zwlaszcza tam, gdzie sama strona WWW daje wynik `Nieokreslona`.

Zasada: Google Places pomaga nazwac branze, ale nie zastepuje crawla strony. Strona WWW nadal jest potrzebna do AI i do wygenerowania sensownego argumentu handlowego.

## Q4 - branze priorytetowe

Branze, ktore powinny byc oznaczane jako wazne dla Q4:

- edukacja / kursy / szkoly jezykowe,
- e-commerce / prezenty / wyposazenie domu,
- gastronomia / eventy / wigilie firmowe,
- motoryzacja / opony / serwis sezonowy,
- beauty / medycyna estetyczna,
- przeprowadzki / transport lokalny,
- wybrane remonty / budownictwo jako ogon sezonu,
- hotel / noclegi pod ferie, sylwestra i dlugie weekendy.

## Rola Voice AI

Poniewaz nie ma jeszcze logow Avaya, Voice AI jest pierwszym zrodlem do oceny, czy z klientem byl jakosciowy kontakt.

Z Voice AI chcemy wyciagac:

- czy byla rozmowa z klientem,
- data rozmowy,
- kto prowadzil rozmowe,
- temat rozmowy,
- czy rozmowa dotyczyla sprzedazy / dosprzedazy,
- czy klient wykazal zainteresowanie,
- obiekcje klienta,
- nastepny krok,
- outcome rozmowy,
- jakosc rozmowy,
- czy warto wracac z follow-upem.

Metryki na tym etapie:

- procent klientow z bazy Q4, ktorzy maja rozmowe w Voice AI,
- procent klientow z rozmowa sprzedazowa,
- procent klientow z pozytywnym sygnalem,
- procent klientow wymagajacych follow-upu,
- penetracja rozmow per opiekun,
- penetracja rozmow per branza,
- penetracja rozmow per segment / MRR.

## Etap pozniejszy: Avaya i CRM2 kontakty

Gdy beda dostepne logi Avaya oraz baza osob kontaktowych z CRM2, dokladamy modul Contact Penetration.

Wtedy laczymy:

- baza klientow,
- baza osob kontaktowych z CRM2,
- numery telefonow,
- logi Avaya,
- Voice AI.

Klucz techniczny: normalizacja telefonu.

Przyklady, ktore musza dac ten sam klucz:

- `+48 501 222 333`
- `501222333`
- `48501222333`
- `0048501222333`

Metryki po dodaniu Avaya:

- czy byla proba kontaktu,
- ile prob kontaktu bylo na klienta,
- czy rozmowa zostala odebrana,
- czas rozmowy,
- skuteczny kontakt, np. rozmowa powyzej 60 sekund,
- skuteczny kontakt per opiekun,
- skuteczny kontakt per branza,
- skuteczny kontakt per segment,
- pokrycie bazy leadow sezonowych przez Customer Care.

## Docelowy scoring leadow

Lead powinien dostac scoring, np. 0-100.

Skladowe:

- dopasowanie do sezonu Q4,
- pewnosc rozpoznania branzy,
- wysokosc MRR / segment,
- aktualny pakiet i potencjal dosprzedazy,
- czy klient mial ostatnio rozmowe,
- czy Voice AI pokazuje zainteresowanie albo problem,
- czy klient nie byl juz niedawno kontaktowany w tej samej sprawie,
- status domeny / jakosc strony.

Przykladowe priorytety:

- `A` - dzownic teraz,
- `B` - przygotowac do kampanii wrzesien/pazdziernik,
- `C` - tylko do weryfikacji,
- `D` - niski priorytet albo brak danych.

## Eksport dla opiekunow

Plik dla opiekunow powinien miec minimalnie:

- `account_owner`,
- `client_id`,
- `detail_id`,
- `nip`,
- `company`,
- `domain`,
- `mrr`,
- `segment`,
- `detected_industry`,
- `season_peak`,
- `contact_start`,
- `q4_priority`,
- `recommended_product`,
- `lead_reason`,
- `call_script`,
- `voice_ai_last_contact_date`,
- `voice_ai_outcome`,
- `next_action`,
- `confidence`.

Najwazniejsza kolumna operacyjna:

```text
Dlaczego dzwonimy teraz?
```

Opiekun ma dostac gotowy powod kontaktu, a nie tylko etykiete branzy.

## Widok managera

Dashboard managera powinien pokazywac:

- liczba leadow Q4,
- leady Q4 per opiekun,
- leady Q4 per branza,
- leady Q4 per segment,
- suma MRR w puli,
- rozklad confidence,
- ile rekordow wymaga recznej weryfikacji,
- ile klientow ma sygnal z Voice AI,
- penetracja Voice AI per opiekun,
- lista top branż do akcji w danym miesiacu.

## Najblizsze kroki techniczne

1. Dodac w aplikacji tryb `Baza dla opiekunow Q4`.
2. Dodac eksport XLSX z osobnymi arkuszami:
   - `Leady dla opiekunow`,
   - `Summary managera`,
   - `Branze Q4`,
   - `Do weryfikacji`.
3. Dodac kolumny:
   - `q4_priority`,
   - `lead_reason`,
   - `call_script`,
   - `next_action`.
4. Przygotowac parser danych Voice AI.
5. Polaczyc Voice AI z baza klientow po dostepnych kluczach:
   - `client_id`, jezeli wystepuje,
   - `nip`, jezeli wystepuje,
   - domena / firma jako fallback,
   - telefon dopiero gdy bedzie baza kontaktow.
6. Na razie nie budowac zaleznosci od Avaya.
7. Gdy pojawia sie logi Avaya, dodac osobny modul Contact Penetration.

## Zasada produktu

Crawler odpowiada na pytanie:

```text
Do kogo warto zadzwonic i dlaczego teraz?
```

Voice AI odpowiada na pytanie:

```text
Czy juz rozmawialismy i jaki byl efekt?
```

Avaya w przyszlosci odpowie na pytanie:

```text
Czy Customer Care faktycznie probowal sie dodzwonic i jaki byl poziom penetracji bazy?
```
