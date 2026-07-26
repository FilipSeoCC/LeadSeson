# Research: sezonowosc branz MSP

Dokument zbiera zrodla do budowy matrycy:

```text
Google Places type / GMB category -> branza LeadSeason -> sezon -> okno kontaktu -> argument dla opiekuna
```

## Jak traktowac zrodla

Nie ma jednej oficjalnej bazy "sezonowosci wszystkich branz MSP". Dla LeadSeason trzeba laczyc:

- dane wyszukiwan: Google Trends,
- raporty marketplace / platform uslugowych,
- raporty branzowe,
- dane statystyczne GUS,
- wyniki z realnej bazy klientow WeNet.

Kazdy wpis w matrycy powinien miec:

- `source_url`,
- `source_quality`,
- `season_peak`,
- `contact_start`,
- `confidence`.

## Zrodla bazowe

### Google Trends

URL: https://trends.google.com/trends/

Zastosowanie:

- walidacja sezonowosci fraz,
- porownanie miesiecy piku,
- sprawdzenie trendow regionalnych.

Uwagi:

- Google Trends pokazuje wzgledne zainteresowanie, nie wolumen absolutny,
- najlepiej porownywac frazy w tej samej kategorii i regionie `Polska`.

### Google Places - typy miejsc

URL: https://developers.google.com/maps/documentation/places/web-service/place-types

Zastosowanie:

- lista `primaryType` i `types`,
- mapowanie kategorii Google na branze LeadSeason.

## Branze i sezonowosc

### E-commerce / prezenty / wyposazenie domu

Zrodla:

- Shoper, Q4 i Black Friday: https://www.shoper.pl/learn/artykul/co-sie-sprzedaje-w-q4-dane-z-raportu-shopera-przewodnik-na-podstawie-danych-z-20-000-sklepow
- Gemius, E-commerce w Polsce 2025: https://gemius.com/documents/81/RAPORT_E-COMMERCE_2025.pdf
- PwC / Strategy&, rynek e-commerce w Polsce: https://www.strategyand.pwc.com/pl/pl/publikacje/2022/perspektywy-rozwoju-rynku-e-commerce-w-polsce-2018-2027.html

Wniosek do matrycy:

- peak: listopad-grudzien,
- trigger: Black Friday, Black Week, prezenty swiateczne,
- contact_start: wrzesien-pazdziernik,
- Q4 priority: wysokie.

### Motoryzacja / opony / wulkanizacja

Zrodla:

- PZPO: https://pzpo.org.pl/85-kierowcow-zmieniajacych-opony-na-zimowe-robi-to-w-pazdzierniku-i-listopadzie/
- Rankomat / PPR: https://www.ppr.pl/wiadomosci/67-polakow-zmienia-opony-na-zimowe-badanie-rankomatpl
- Oponeo / Motofaktor: https://www.motofaktor.pl/czy-polacy-zmieniaja-opony-przed-zima-dane-oponeo-pl/

Wniosek do matrycy:

- peak zimowy: pazdziernik-listopad,
- peak letni: kwiecien-maj,
- contact_start: wrzesien dla zimowek, marzec dla letnich,
- Q4 priority: wysokie.

### Klimatyzacja / HVAC

Zrodla:

- Oferteo, raport montaz klimatyzacji: https://biuroprasowe.oferteo.pl/421008-raport-z-rynku-montaz-klimatyzacji
- Oferteo / rynek uslug: https://www.rp.pl/nieruchomosci/art42194881-sezon-na-uslugi-otwarty-polacy-chca-budowac-remontowac-i-urzadzac-ogrody
- Fakt na podstawie Barometru Oferteo: https://www.fakt.pl/pieniadze/upaly-zmienily-rynek-polacy-masowo-wybieraja-klimatyzacje/y80wswt

Wniosek do matrycy:

- peak: Q2/Q3, upaly,
- contact_start: styczen-marzec,
- Q4 priority: niskie dla nowej sprzedazy, mozliwe serwis/pompy/ogrzewanie jako osobny temat.

### Budownictwo / remonty / uslugi domowe

Zrodla:

- Oferteo / Rzeczpospolita: https://www.rp.pl/nieruchomosci/art42194881-sezon-na-uslugi-otwarty-polacy-chca-budowac-remontowac-i-urzadzac-ogrody
- Oferteo 2024 rynek uslug: https://biuroprasowe.oferteo.pl/374224-2024-na-rynku-uslug-podsumowanie

Wniosek do matrycy:

- peak: wiosna-lato oraz ogon do jesieni,
- contact_start: styczen-kwiecien, drugi push sierpien-wrzesien,
- Q4 priority: srednie, raczej koncowka sezonu / awarie / przygotowanie do zimy.

### Ogrody / ogrodnictwo

Zrodla:

- Semcore, raport SXO/e-commerce ogrodniczy: https://semcore.pl/semcore-lab/raport-sxo-e-commerce-dla-branzy-ogrodniczej/
- Oferteo / Rzeczpospolita o ogrodach i uslugach: https://www.rp.pl/nieruchomosci/art42194881-sezon-na-uslugi-otwarty-polacy-chca-budowac-remontowac-i-urzadzac-ogrody

Wniosek do matrycy:

- peak: wiosna-lato,
- contact_start: styczen-marzec,
- Q4 priority: niskie, chyba ze temat jesiennych porzadkow / przygotowania ogrodu do zimy.

### Gastronomia / eventy / catering

Zrodla:

- Poradnik Restauratora / Briefly: https://poradnikrestauratora.pl/artykuly/analiza-briefly-najwiecej-na-swiateczna-impreze-wydaja-firmy-w-warszawie-srednio-135-tys-zl/
- HorecaTrends: https://www.horecatrends.pl/gastronomia/114/catering_swiateczny_i_wigilie_firmowe_to_juz_ostatni_dzownek%2C3326.html
- Newseria, catering swiateczny: https://lifestyle.newseria.pl/wszystkie-newsy/swiateczny-catering%2Cp1171615755

Wniosek do matrycy:

- peak: grudzien dla wigilii firmowych i cateringu swiatecznego,
- contact_start: wrzesien-pazdziernik,
- Q4 priority: wysokie.

### Edukacja / kursy / szkoly jezykowe

Zrodla:

- National Geographic Learning, raport o stanie edukacji jezykowej: https://nglearning.pl/downloads/raport-o-stanie-edukacji-jezykowej/
- LangLion, rynek szkol jezykowych: https://blog.langlion.com/pl/rynek-szkol-jezykowych-w-polsce-analiza-trendy-i-prognozy-rozwoju/

Wniosek do matrycy:

- peak: sierpien-pazdziernik oraz styczen-luty,
- contact_start: czerwiec-sierpien oraz grudzien-styczen,
- Q4 priority: wysokie w lipcu/sierpniu, bo okno kontaktu juz trwa.

### Turystyka / hotel / noclegi

Zrodla:

- GUS, turystyka: https://stat.gov.pl/obszary-tematyczne/kultura-turystyka-sport/turystyka/
- GUS, wykorzystanie obiektow noclegowych 2024: https://stat.gov.pl/files/gfx/portalinformacyjny/pl/defaultaktualnosci/5494/18/3/1/wykorzystanie_turystycznych_obiektow_noclegowych_w_2024_r.pdf

Wniosek do matrycy:

- peak glowny: lipiec-sierpien,
- dodatkowe piki: ferie, dlugie weekendy, sylwester,
- contact_start: luty-kwiecien dla lata, wrzesien-listopad dla zimy/sylwestra,
- Q4 priority: srednie-wysokie dla obiektow zimowych, sylwestrowych i eventowych.

### Beauty / medycyna estetyczna / kosmetologia

Zrodla:

- Booksy Trends: https://trends-pl.booksy.com/
- Beauty Razem / raport medycyny estetycznej: https://beautyrazem.pl/juz-4-mln-polakow-zdecydowalo-sie-na-zabieg-medycyny-estetycznej-raport/

Wniosek do matrycy:

- peak: przed wakacjami, przed swietami/sylwestrem, okazje rodzinne,
- contact_start: marzec-maj oraz wrzesien-listopad,
- Q4 priority: srednie-wysokie.

## Najlepszy sposob wdrozenia w LeadSeason

1. Nie mapowac od razu wszystkich kategorii Google.
2. Najpierw pobrac `places_primary_type` i `places_types` z realnej bazy WeNet.
3. Zrobic top 100 typow Google wystepujacych w bazie.
4. Zmapowac top 100 na branze LeadSeason i sezonowosc.
5. Dla kazdego mapowania zapisac zrodlo i confidence.
6. Reszte oznaczac jako `Do weryfikacji`.

## Proponowane kolumny w matrycy sezonowosci

```text
google_type
google_category_name
leadseason_industry
season_peak
contact_start
q4_priority
recommended_product
lead_reason_template
call_script_template
source_url
source_quality
confidence
```

## Plik roboczy

Pierwsza sklejona matryca jest w:

```text
config/leadseason_seasonality_matrix.csv
```

To nie jest jeszcze komplet wszystkich kategorii Google. To praktyczna baza startowa pod MŚP i Q4, z naciskiem na branze, ktore maja sens dla procesu Customer Care:

- gastronomia / eventy,
- motoryzacja / opony,
- edukacja / kursy,
- beauty / medycyna,
- hotel / noclegi,
- e-commerce / prezenty / wyposazenie domu,
- przeprowadzki,
- budownictwo / remonty,
- HVAC,
- ogrody,
- wybrane uslugi profesjonalne.

Kolejny krok: po enrichment Google Places na realnej bazie WeNet zrobic ranking najczestszych `places_primary_type` i dopisac brakujace typy do tej matrycy.
