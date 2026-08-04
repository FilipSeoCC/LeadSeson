# Strategia: System pozyskiwania leadów oparty o audyt, AI i mikro-aplikacje

> Dokument roboczy podsumowujący dyskusję strategiczną nt. rozbudowy modułu LeadSeason
> o warstwę pozyskiwania klientów (audyt → AI → wideo/głos → outreach → konwersja).
> Status: koncepcja, przed decyzją wdrożeniową.

---

## 1. Cel i punkt wyjścia

Punktem wyjścia był pomysł zbudowania modułu działającego jako flow:

1. Zbieranie kompletu danych o biznesie klienta (audyt marketingowy/wizerunkowy) pod kątem usług: SEO, social media, PPC, budowa stron WWW.
2. Sklejenie danych w audyt (AI) — docelowo plik tekstowy / PDF z wykresami.
3. Audyt techniczny strony (PageSpeed).
4. Warstwa głosowa — transkrypcja tekstu na mowę na bazie sklonowanego głosu (ElevenLabs).
5. Nagranie/montaż wideo prezentującego audyt i kluczowe błędy.
6. Wysyłka maila z nagraniem, na podstawie danych: domena → adres mailowy osoby decyzyjnej.
7. Monitoring i obsługa odpowiedzi.

Założenia kosztowe: maksymalnie open source / darmowe narzędzia, płatność tylko za to co konieczne, wykorzystanie darmowych okresów próbnych do testu workflow przed skalowaniem.

Dodatkowe założenie: wykorzystanie istniejącego **modułu sezonowości** (LeadSeason) zarówno do pozyskiwania klientów, jak i jako element strategii/audytu pokazywany samym klientom jako uzasadnienie działań.

---

## 2. Pierwotny stack techniczny (moduł po module)

### Moduł 1 — Dane / audyt źródłowy
- Senuto API/MCP (już podpięte) — widoczność SEO domeny
- Google PageSpeed Insights API — darmowe, audyt techniczny strony
- Google Places API — dane GBP publiczne (oceny, recenzje, kategoria, zdjęcia); **uwaga:** brak dostępu do panelu GBP klienta bez jego autoryzacji
- Search Console — **działa tylko dla zweryfikowanych własnych domen**, nie da się zrobić audytu SC cudzej strony
- Wappalyzer/BuiltWith API — tech stack strony, darmowy tier z limitami
- Playwright (open source) — własny scraper/screenshoty danych publicznych

### Moduł 2 — Audyt AI + PDF
- Claude API — generowanie narracji audytu z JSON-a danych
- matplotlib/plotly — wykresy
- WeasyPrint (HTML→PDF) lub ReportLab — render PDF
- Jinja2 — szablon HTML audytu

### Moduł 3 — Głos
- ElevenLabs API
  - Free: 10k znaków/mies., bez klonowania
  - Starter: 5 USD/mies. — Instant Voice Cloning, 30k znaków
  - Creator: 22 USD/mies. — Professional Voice Cloning, 100k znaków
  - API rozliczane per znak: ok. 0,15–0,30 USD / 1000 znaków w zależności od modelu
- **Wymóg prawny:** od 2 sierpnia 2026 AI Act wymaga oznaczania treści generowanej przez AI w UE — materiał marketingowy z klonowanym głosem musi być oznaczony jako AI-generated

### Moduł 4 — Wideo
- Zamiast live screen recording (nieskalowalne) → automatyzacja:
  - Playwright — screenshoty stron/wyników
  - ffmpeg (open source) — animacja Ken Burns, cięcia, nakładanie audio
  - moviepy + Pillow — sterowanie timeline'em, overlaye/podświetlenia błędów

### Moduł 5 — Wysyłka i monitoring
- Hunter.io — wyszukiwanie maila decyzyjnego (darmowy tier: 25 wyszukiwań/mies.)
- Amazon SES (lub inny tani SMTP) — wysyłka, ~0,10 USD/1000 maili
- IMAP polling (Python `imaplib`) + Claude API — klasyfikacja odpowiedzi
- SQLite/Postgres — baza statusu leada w pipeline (kręgosłup systemu)

### Orkiestracja
- n8n (open source, self-hosted) — spinanie modułów zamiast pisania orchestracji ręcznie w Pythonie

### Rekomendowana kolejność budowy (pierwotna)
1. Baza danych + schemat leada
2. Moduł 1 (dane) na 5–10 testowych firmach
3. Moduł 2 (PDF audytu) — ocena jakości treści
4. Moduł 3 (głos) — mail z PDF + audio, jeszcze bez wideo
5. Test wysyłki na małej próbie **bez wideo** — walidacja czy audyt+głos w ogóle konwertuje
6. Moduł 4 (wideo) — dopiero po potwierdzeniu konwersji
7. n8n spinające całość + monitoring odpowiedzi

---

## 3. Analiza konkurencji

### Rynek globalny
Kategoria „spersonalizowane wideo do cold outreachu” jest dojrzała i dobrze sfinansowana:
- **Sendspark** — AI-personalizowany outreach sprzedażowy, prawdziwi przedstawiciele na wideo + klonowanie głosu + dynamiczne tła, tysiące wariantów z jednego nagrania
- **HeyGen** — w pełni syntetyczne awatary AI, mocne w wielojęzycznym marketingu skalowym, słabsze w cold outreachu (odbiorcy rozpoznają awatar)
- **Tavus** — od kwietnia 2026 pivot w stronę API dla deweloperów (Conversational Video Interface), realtime rozmowy wideo z replikami
- **Vidyard** — najstarszy gracz, AI Avatars + Video Sales Agent generujący wideo automatycznie po akcjach kupującego, głęboka analityka widza
- **Potion, Sendr.ai** — podobna kategoria: personalizacja tekst→wideo, sekwencje wielokanałowe

Wniosek: to nie jest nisza technologiczna — to skomodytyzowana usługa SaaS z dużym kapitałem konkurentów. Budowa własnego odpowiednika tej technologii **jako produktu do sprzedania innym firmom** nie ma sensu.

### Audyt jako hak — dane branżowe
Udokumentowany, powtarzalny workflow agencyjny (audyt + wideo):
- Generyczny cold email: 1–3% odpowiedzi
- Spersonalizowany outreach oparty na audycie: 6–15% odpowiedzi
- Wideo z osobistym omówieniem audytu (Loom-style): do 20% odpowiedzi, **ale „źle się skaluje”** — im bardziej automatyzujesz wideo, tym bardziej zbliżasz się do niższego pułapu

### Rynek polski
- „Darmowy audyt SEO” jako hak jest już **komercyjnie wypalony** — część rynku (świadomi właściciele firm) jest nieufna wobec automatycznych audytów, które generują absurdalne rekomendacje lub halucynują nieistniejące błędy
- Nikt zidentyfikowany w PL nie łączy audytu z klonowanym głosem i wideo — to realna luka lokalna
- Cold mailing tekstowy w PL **działa i jest ekonomiczny**: agencja robiąca cold mailing jako główny kanał (ok. 200 maili/tydzień) może zdobywać 3–8 nowych umów miesięcznie, dobre kampanie osiągają 8–15% odpowiedzi, CAC wychodzi 1200–1800 zł (kilkukrotnie mniej niż Google Ads, gdzie CAC agencji często przekracza 3–8 tys. zł)

### Werdykt biznesowy
- Jako **produkt SaaS na sprzedaż innym agencjom** — brak sensu, rynek zajęty przez dobrze sfinansowanych graczy (Sendspark, HeyGen itd.)
- Jako **wewnętrzne narzędzie pozyskiwania klientów dla WeNet / ai-ops.pl** — ma sens, bo:
  - lokalny rynek wciąż głównie operuje na cold mailingu tekstowym → wideo/głos to realna przewaga różnicująca
  - unikalny dostęp do danych Senuto, WeNet i modułu sezonowości = przewaga, której generyczne narzędzia (Sendspark itp.) nie mają
  - ekonomia bazowa (CAC 1200–1800 zł na czystym cold mailingu) już się opłaca — ulepszenie audytem/głosem musi tylko podnieść konwersję, nie musi „wymyślić kategorii”

---

## 4. Elementy innowacyjne / różnicujące

Ponieważ na samej technologii wideo/AI-avatara nie da się wygrać z dobrze sfinansowanymi graczami globalnymi, przewaga ma wynikać z unikalnych zasobów (dane WeNet, Senuto, moduł sezonowości), nie z lepszego avatara.

1. **Lejek kosztowy (tierowanie leadów)** — nie każdy lead dostaje od razu drogie wideo:
   - Tier 1 (cała lista): tani tekstowy mail z 1–2 konkretnymi faktami z audytu
   - Tier 2 (kto otworzył/kliknął): dogrywane audio z klonowanym głosem
   - Tier 3 (kto odpisał / długo przeglądał mikrostronę): pełne wideo + osobisty follow-up
   - Najdroższy zasób (wideo, czas własny) trafia tylko do najcieplejszych leadów

2. **Audyt porównawczy zamiast „Twoja strona jest zepsuta”** — zamiast generycznego raportu błędów: „3 firmy z Twojej branży w promieniu 10 km biją Cię w mapach Google, a Ty tracisz X% ruchu sezonowego”. Konkret + porównanie do sąsiadów trudniej zignorować niż ogólny raport.

3. **Timing napędzany sezonowością** (unikalna przewaga — nikt inny w PL nie ma tego modułu) — wysyłka dokładnie w momencie, gdy dana branża wchodzi w sezonowy wzrost zapytań, z komunikatem typu „Twój sezon zaczyna się za 6 tygodni, a Twoja widoczność jest X% poniżej potencjału”. Zmiana ramy z „sprzedaję usługę” na „ostrzegam przed utratą pieniędzy w konkretnym oknie czasowym”.

4. **Trigger-based outreach** — monitoring zmian (spadek z mapy Google, spadek liczby recenzji, wejście nowego konkurenta) i wysyłka w momencie, gdy coś realnie się wydarzyło u klienta, zamiast statycznej listy wysyłanej losowo.

5. **Mikrostrona zamiast PDF-a** — spersonalizowany link zamiast załącznika. Pozwala trackować kto wszedł, ile czasu spędził, co przeczytał → sygnał do tierowania (pkt 1) bez płacenia za drogie narzędzia typu Clay.

6. **Human-in-the-loop na końcu, nie AI od początku do końca** — krótka ręczna weryfikacja top 3 wniosków audytu przed wysyłką + wzmianka w mailu („audyt zweryfikowany osobiście”). Koszt: ok. 2 minuty na leada. Zbija największy zarzut wobec tej kategorii narzędzi (halucynacje, absurdalne rekomendacje) obecny na rynku PL.

---

## 5. Kontekst rynkowy — top metody pozyskiwania klientów B2B 2026

Polscy praktycy wprost wskazują, że cold mail i zimne wiadomości na LinkedIn to metody sprzed ok. dwóch lat — rynek się nasyca i przesuwa w stronę innych podejść:

1. **Signal-based / trigger-based prospecting** — wysyłka tylko wtedy, gdy coś się realnie wydarzyło (spadek w mapach, nowa konkurencja, zmiana na stronie) — pokrywa się z modułem sezonowości/trigger opisanym w sekcji 4.
2. **AEO/GEO (Answer Engine / Generative Engine Optimization)** — pozycjonowanie w wynikach AI (ChatGPT, Perplexity, Google AI Overviews), nowy front SEO, dopiero się rodzi. Można sprzedawać jako usługę i wykorzystać do własnego pozycjonowania eksperckiego.
3. **Free tool zamiast free audytu** — narzędzie diagnostyczne (self-service checker, interaktywny dashboard), do którego ludzie wracają i które polecają dalej, zamiast jednorazowego raportu lądującego w koszu.
4. **Telefon wraca — model hybrydowy AI + human** — AI robi research/kwalifikację/follow-up, ale pierwszy realny kontakt po zainteresowaniu to telefon, nie kolejny mail. Skuteczność w 2026 zależy od jakości rozmów, nie ich liczby.
5. **Content/founder-led growth** — regularny, konkretny content (case studies, insighty z sezonowości) zamiast czystego outboundu — generuje leady inbound, tańsze w konwersji.

### Rekomendowana kombinacja dla ai-ops.pl / WeNet
1. Darmowe narzędzie (pkt 3) jako magnes — generuje ciepłe leady samo z siebie
2. Trigger-based outreach (pkt 1, sezonowość) do zimnej bazy — precyzyjny timing zamiast masowej wysyłki
3. Audyt+wideo jako „dowód kompetencji” wysyłany dopiero do zakwalifikowanych/zainteresowanych
4. Telefon jako zamknięcie, nie mail

---

## 6. Zrewidowana koncepcja: dynamiczna mikro-aplikacja per klient

Zamiast statycznego PDF-a lub setek ręcznie generowanych stron — **jedna aplikacja z dynamicznym routingiem** (np. `audyt.ai-ops.pl/nazwa-firmy`), która ciągnie dane leada z bazy i renderuje wykresy (sezonowość, porównanie do konkurencji, snapshot GBP) na żywo. Jeden kod, tysiące „spersonalizowanych” stron bez ręcznej roboty. PDF zostaje opcjonalnym przyciskiem „pobierz” generowanym server-side z tych samych danych — nie głównym formatem.

### Struktura mikro-aplikacji

**A. Insight-trigger jako nagłówek** — mikro-apka od razu pokazuje konkretny trigger („Twoja widoczność spadła o X% w tym tygodniu” / „Twój sezon zaczyna się za 5 tygodni”), nie generyczne „oto Twój audyt”.

**B. Progressive disclosure (kolejność ujawniania treści)** — twardy gate od razu na starcie działa słabo, bo user nie widział jeszcze wartości. Właściwy wzorzec:
1. Pierwsze 20–30 sekund / scroll do pewnego punktu — bez gate'a: sam hak, jeden konkretny wykres, coś co realnie „boli”
2. Gate pojawia się dopiero przy przejściu do szczegółów (pełna analiza, rekomendacje, porównanie do konkurencji) — user już zainwestował uwagę

**C. Gate = rejestracja z pełną zgodą** — żeby zobaczyć resztę raportu, user samodzielnie:
- podaje e-mail i numer telefonu
- zaznacza zgodę na kontakt (checkbox **odznaczony domyślnie**, z jasną, konkretną treścią celu, np. „zgadzam się na kontakt telefoniczny/SMS w celu omówienia wyników audytu” — nie ogólne „zgadzam się na przetwarzanie danych”)

To rozwiązuje problem prawny opisany w sekcji 8: dobrowolna, udokumentowana zgoda zebrana bezpośrednio od użytkownika, zamiast cold outreachu na numer, do którego nie było podstawy prawnej.

Zalecenia dodatkowe:
- Wszystkie pola (mail + telefon + zgoda) w jednym kroku, nie rozbite na etapy — ryzyko porzucenia formularza przed dotarciem do zgody
- Double opt-in na mailu (link potwierdzający) — dodatkowe zabezpieczenie prawne i filtr botów/fałszywych danych
- Technicznie: prosty stan w React (timer lub IntersectionObserver na scroll) do wyzwolenia gate'a

**D. Tracking zachowania → lead scoring** — mikro-apka śledzi czas na stronie, klikane wykresy, powroty. Rejestracja = najsilniejszy możliwy sygnał kwalifikacyjny (silniejszy niż samo otwarcie maila) → automatyczny trigger do bazy, lead trafia od razu do Tier 3.

**E. Free konto jako warstwa retencyjna** — zamiast kończyć relację na jednym audycie, zaproszenie do darmowego konta, gdzie klient może wracać i śledzić swoją sezonowość/widoczność w czasie. Zamienia jednorazowy lead magnet w produkt freemium, tworzy ciągły punkt kontaktu bez konieczności ponownego cold outreachu.

---

## 7. Kanał SMS — analiza

### Dlaczego SMS ma sens w tym miejscu lejka
- Open rate SMS: zwykle 90%+ w ciągu kilku minut vs. 20–30% dla maila w ciągu godzin/dni
- Krótki link do mikro-apki pasuje naturalnie do formatu SMS (hak + link, bez pełnego kontekstu)
- Dobrze sprawdza się jako **drugi dotyk**: mail nieotwarty w 48h → SMS jako przypomnienie z linkiem

### Ryzyko prawne
Wysyłka SMS marketingowych bez wcześniejszej zgody podlega art. 172 Prawa telekomunikacyjnego — ryzyko wyższe niż przy cold mailu B2B na adres firmowy, bo numer telefonu to bardziej bezpośrednie dane osobowe, traktowane surowiej przez UOKiK/UODO.

### Rekomendacja podziału zastosowań
1. **Baza aktywna WeNet (zgoda już istnieje)** — bezpieczne do testowania od razu, wysoka szansa na podniesienie zaangażowania (patrz sekcja 9 — problem 7% logowań do portalu)
2. **Cold acquisition (nowi leadzi bez zgody)** — pozostać przy mailu jako głównym kanale; SMS dopiero po zebraniu zgody przez formularz w mikro-apce (sekcja 6C) lub po konsultacji prawnej

---

## 8. Agenci głosowi (dzwoniący) — kierunek na później

Gotowe API do zbudowania agenta dzwoniącego z klonowanym głosem: **Vapi, Retell AI, Bland AI, ElevenLabs Conversational AI** — nie trzeba budować od zera.

Warunki wdrożenia:
- **Prawnie**: automatyczne połączenia marketingowe w PL wymagają zgody (art. 172 Prawa telekomunikacyjnego) — ryzykowniejsze niż cold mail do firmowego adresu, wymaga konsultacji prawnej przed skalowaniem
- **Sekwencyjnie**: ma sens dopiero jako ostatni krok dla najcieplejszych leadów (tych, którzy przeszli przez gate w mikro-apce i zostawili numer wraz ze zgodą), nie jako masowy cold-calling

---

## 9. Otwarty kontekst wewnętrzny WeNet

- Istniejący wewnętrzny system raportowy dla aktywnych klientów WeNet ma **poniżej 7% wskaźnika logowania** — silny dowód na to, że model „portal, do którego trzeba samemu wejść” przegrywa z modelem push (insight trafia do klienta, nie odwrotnie). Potwierdza to wybór architektury opisanej w sekcji 6 (insight-trigger + SMS/mail zamiast statycznego dashboardu)
- WeNet posiada narzędzie **NetScanner** do pozyskiwania klientów, które działa lepiej niż portal raportowy — mechanika i szczegóły do doprecyzowania

### Otwarte pytania (do rozstrzygnięcia przed dalszym wdrożeniem)
1. Co dokładnie robi NetScanner i jaki mechanizm/kanał/dane odpowiadają za jego skuteczność względem portalu raportowego?
2. Czy projektowany system ma **uzupełniać** NetScanner w ramach WeNet, czy być **osobnym narzędziem** pod ai-ops.pl / Synergię i inne pozyskania zewnętrzne, niezależnym od infrastruktury WeNet?

To pytanie ma znaczenie strategiczne — determinuje, czy budować rozwiązanie komplementarne do istniejącej infrastruktury pracodawcy, czy niezależny produkt pod własną działalność.

---

## 10. Kwestie prawne — zbiorczo

| Kanał | Podstawa prawna / ryzyko | Rekomendacja |
|---|---|---|
| Cold mail B2B na adres firmowy | RODO + ustawa o świadczeniu usług drogą elektroniczną; B2B do ogólnego maila firmy bezpieczniejsze niż do prywatnego maila właściciela | Opt-out link, mała próba na start, monitoring reputacji domeny |
| Klonowany głos / wideo AI w mailingu | AI Act — obowiązek oznaczania treści jako AI-generated od 2 sierpnia 2026 (UE) | Wdrożyć etykietowanie od początku |
| SMS marketingowy | Art. 172 Prawa telekomunikacyjnego — wymagana zgoda, ryzyko wyższe niż mail | Tylko do bazy z istniejącą zgodą lub po zebraniu zgody przez formularz w mikro-apce |
| Automatyczne połączenia telefoniczne (agent głosowy) | Art. 172 Prawa telekomunikacyjnego — wymagana zgoda, ryzyko najwyższe z omawianych kanałów | Tylko dla leadów po jawnej zgodzie z formularza, docelowo z konsultacją prawną |

**Zastrzeżenie:** powyższe nie stanowi porady prawnej — przy skalowaniu któregokolwiek z kanałów wymagana jest konsultacja z prawnikiem.

---

## 11. Rekomendowana kolejność wdrożenia (finalna, po rewizji)

1. Baza danych + schemat leada (fundament)
2. Moduł danych (Moduł 1) + walidacja jakości na 5–10 testowych firmach
3. Jedna dynamiczna mikro-aplikacja z routingiem per-lead (sekcja 6) — zastępuje PDF jako główny format
4. Insight-trigger jako nagłówek mikro-apki + progressive disclosure + gate rejestracyjny ze zgodą
5. Tracking zachowania → prosty lead-scoring / tierowanie (sekcja 4, pkt 1)
6. Test wysyłki (mail, mała próba) prowadzącej do mikro-apki — walidacja konwersji **przed** inwestycją w głos/wideo
7. Moduł głosu (ElevenLabs) — dogrywany dla Tier 2/3 po walidacji
8. Moduł wideo — dopiero po potwierdzeniu, że audyt + głos konwertuje
9. „Free konto” jako warstwa retencyjna
10. SMS do bazy z istniejącą zgodą (WeNet) — test podniesienia wskaźnika zaangażowania (obecnie <7%)
11. Agent głosowy (Vapi/Retell/Bland/ElevenLabs Conversational AI) — wyłącznie dla najcieplejszych leadów po zgodzie, po konsultacji prawnej
12. n8n spinające całość + moduł monitoringu odpowiedzi

---

*Dokument wygenerowany na podstawie sesji strategicznej z Claude, dodany do repozytorium jako punkt odniesienia przed rozpoczęciem prac wdrożeniowych.*
