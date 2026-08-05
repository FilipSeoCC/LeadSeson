# Strategia: System pozyskiwania leadów oparty o audyt, AI i mikro-aplikacje

> Dokument roboczy podsumowujący dyskusję strategiczną nt. rozbudowy modułu LeadSeason
> o warstwę pozyskiwania klientów (audyt → AI → wideo/głos → outreach → konwersja).
> Status: koncepcja, przed decyzją wdrożeniową.

---

## 1. Cel i punkt wyjścia

Flow docelowy:

1. Zbieranie kompletu danych o biznesie klienta (audyt marketingowy/wizerunkowy) pod usługi: SEO, social media, PPC, budowa stron WWW.
2. Sklejenie danych w audyt przez AI.
3. Audyt techniczny strony (PageSpeed/Lighthouse).
4. Warstwa głosowa — TTS na bazie sklonowanego głosu (ElevenLabs).
5. Wideo prezentujące audyt i kluczowe błędy.
6. Wysyłka do osoby decyzyjnej (domena → mail).
7. Monitoring i obsługa odpowiedzi.

Założenia kosztowe: maksymalnie open source, płatność tylko za konieczne, darmowe triale do testu workflow przed skalowaniem.

Dodatkowe założenie: wykorzystanie **modułu sezonowości** (LeadSeason) zarówno do pozyskiwania klientów, jak i jako element strategii/audytu pokazywany klientom jako uzasadnienie działań.

---

## 2. Stack techniczny (moduł po module)

### Moduł 1 — Dane / audyt źródłowy
- Senuto API/MCP (już podpięte) — widoczność SEO domeny
- Google PageSpeed Insights API — darmowe, audyt techniczny
- Google Places API — dane GBP publiczne; **brak dostępu do panelu GBP klienta bez jego autoryzacji**
- Search Console — **tylko dla zweryfikowanych własnych domen**, nie da się audytować cudzej strony
- Wappalyzer/BuiltWith API — tech stack, darmowy tier z limitami
- Playwright — scraper/screenshoty danych publicznych

### Moduł 2 — Audyt AI + render
- Claude API — narracja audytu z JSON-a danych
- matplotlib/plotly — wykresy
- WeasyPrint (HTML→PDF) lub ReportLab
- Jinja2 — szablon audytu

### Moduł 3 — Głos
- ElevenLabs API
  - Free: 10k znaków/mies., bez klonowania
  - Starter: 5 USD — Instant Voice Cloning, 30k znaków
  - Creator: 22 USD — Professional Voice Cloning, 100k znaków
  - API: ok. 0,15–0,30 USD / 1000 znaków zależnie od modelu
- **AI Act:** od 2 sierpnia 2026 obowiązek oznaczania treści AI-generated w UE

### Moduł 4 — Wideo
- Zamiast live screen recording (nieskalowalne):
  - Playwright — screenshoty stron/wyników
  - ffmpeg — Ken Burns, cięcia, audio
  - moviepy + Pillow — timeline, overlaye/podświetlenia błędów

### Moduł 5 — Wysyłka i monitoring
- Hunter.io — mail decyzyjny (darmowy tier: 25 wyszukiwań/mies.)
- Amazon SES — ~0,10 USD/1000 maili
- IMAP polling + Claude API — klasyfikacja odpowiedzi
- SQLite/Postgres — baza statusu leada (kręgosłup systemu)

### Orkiestracja
- n8n (open source, self-hosted)

---

## 3. Analiza konkurencji

### Rynek globalny
Kategoria „spersonalizowane wideo do cold outreachu" jest dojrzała i dobrze sfinansowana:
- **Sendspark** — AI-personalizowany outreach, prawdziwi przedstawiciele + klonowanie głosu + dynamiczne tła
- **HeyGen** — syntetyczne awatary, mocne w wielojęzycznym marketingu, słabsze w cold outreachu (odbiorcy rozpoznają awatar)
- **Tavus** — od kwietnia 2026 pivot w API dla deweloperów (Conversational Video Interface)
- **Vidyard** — najstarszy gracz, AI Avatars + Video Sales Agent, głęboka analityka widza
- **Potion, Sendr.ai** — personalizacja tekst→wideo, sekwencje wielokanałowe

Wniosek: to skomodytyzowana usługa SaaS z dużym kapitałem konkurentów. Budowa odpowiednika **jako produktu na sprzedaż** nie ma sensu.

### Audyt jako hak — benchmarki
- Generyczny cold email: 1–3% odpowiedzi
- Outreach oparty na audycie: 6–15%
- Wideo z osobistym omówieniem audytu (Loom-style): do 20%, **ale „źle się skaluje"** — im więcej automatyzacji, tym bliżej dolnego pułapu

### Rynek polski
- „Darmowy audyt SEO" jako hak jest **komercyjnie wypalony** — świadomi właściciele firm są nieufni wobec automatów generujących absurdalne rekomendacje lub halucynujących błędy
- Nikt zidentyfikowany w PL nie łączy audytu z klonowanym głosem i wideo — realna luka lokalna
- Cold mailing tekstowy w PL działa: ~200 maili/tydzień → 3–8 umów miesięcznie, dobre kampanie 8–15% odpowiedzi, CAC 1200–1800 zł (vs. 3–8 tys. zł przy Google Ads)

### Werdykt
- Jako **SaaS na sprzedaż innym agencjom** — brak sensu
- Jako **wewnętrzne narzędzie pozyskiwania dla ai-ops.pl** — ma sens: przewaga z danych Senuto + moduł sezonowości + wideo/głos na rynku, który operuje głównie tekstem. Ekonomia bazowa już się opłaca, ulepszenie musi tylko podnieść konwersję.

---

## 4. Elementy różnicujące

1. **Lejek kosztowy (tierowanie)** — nie każdy lead dostaje drogie wideo:
   - Tier 1 (cała lista): tekstowy mail z 1–2 konkretami z audytu
   - Tier 2 (otworzył/kliknął): audio z klonowanym głosem
   - Tier 3 (odpisał / długo przeglądał mikro-apkę): pełne wideo + osobisty follow-up

2. **Audyt porównawczy** — zamiast „Twoja strona jest zepsuta": „3 firmy z Twojej branży w promieniu 10 km biją Cię w mapach, tracisz X% ruchu sezonowego".

3. **Timing sezonowy** (unikalna przewaga) — wysyłka gdy branża wchodzi w sezonowy wzrost: „Twój sezon startuje za 6 tygodni, Twoja widoczność jest X% poniżej potencjału". Zmiana ramy ze sprzedaży na ostrzeżenie przed utratą pieniędzy w konkretnym oknie.

4. **Trigger-based outreach** — monitoring zmian (spadek w mapach, spadek recenzji, nowy konkurent) i wysyłka gdy coś realnie się wydarzyło.

5. **Mikro-apka zamiast PDF-a** — link zamiast załącznika, tracking zachowania → tierowanie bez płacenia za Clay.

6. **Human-in-the-loop** — ręczna weryfikacja top 3 wniosków przed wysyłką (~2 min/lead) + wzmianka w mailu. Zbija największy zarzut wobec tej kategorii na rynku PL.

---

## 5. Kontekst rynkowy — metody pozyskiwania B2B 2026

Cold mail i zimne wiadomości na LinkedIn to według polskich praktyków metody sprzed ~2 lat. Aktualne kierunki:

1. **Signal/trigger-based prospecting** — wysyłka tylko po realnym zdarzeniu (pokrywa się z sekcją 4)
2. **AEO/GEO** — patrz sekcja 6, potraktowane osobno jako kluczowy kierunek
3. **Free tool zamiast free audytu** — narzędzie diagnostyczne, do którego się wraca i które się poleca, zamiast jednorazowego raportu
4. **Telefon wraca — hybryda AI + human** — AI robi research/kwalifikację/follow-up, pierwszy realny kontakt to telefon
5. **Content/founder-led growth** — case studies i insighty z sezonowości generują tańsze leady inbound

### Rekomendowana kombinacja
1. Darmowe narzędzie jako magnes
2. Trigger-based outreach (sezonowość) do zimnej bazy
3. Audyt+wideo jako dowód kompetencji — dopiero dla zakwalifikowanych
4. Telefon jako zamknięcie, nie mail

---

## 6. AEO/GEO — priorytetowy kierunek

**Answer Engine Optimization / Generative Engine Optimization** — optymalizacja pod cytowalność w ChatGPT, Perplexity, Gemini i Google AI Overviews. Powód wysokiego priorytetu:

- **Nowy, niewypalony temat** — w przeciwieństwie do „darmowego audytu SEO", rynek nie jest jeszcze zmęczony tym komunikatem
- **Wysoki lęk decydentów** — pytanie „czy AI w ogóle mnie widzi/poleca?" jest dla właściciela firmy nowe i niepokojące, co czyni je mocnym hakiem outreachowym
- **Podwójne zastosowanie** — nowa usługa do sprzedania **i** nowa sekcja audytu, której nikt w PL nie robi masowo
- **Gotowy kod open source** — `Auriti-Labs/geo-optimizer-skill` (644⭐, Python + MCP): audyt i tracking czy ChatGPT/Perplexity/Gemini/AI Overviews cytują daną stronę
- **Wsparcie własnego pozycjonowania** — content o AEO buduje pozycję ekspercką (founder-led growth z sekcji 5)

**Rekomendacja:** AEO powinno być osobną, wyróżnioną sekcją mikro-apki i osobnym hakiem w komunikacji — nie dodatkiem do klasycznego audytu SEO. Potencjalnie mocniejszy trigger niż sezonowość dla części segmentów.

---

## 7. Mikro-aplikacja per klient

Zamiast statycznego PDF-a lub setek ręcznych stron — **jedna aplikacja z dynamicznym routingiem** (`audyt.ai-ops.pl/nazwa-firmy`) ciągnąca dane leada z bazy i renderująca wykresy na żywo. Jeden kod, tysiące „spersonalizowanych" stron. PDF zostaje opcjonalnym przyciskiem „pobierz".

### Struktura

**A. Insight-trigger jako nagłówek** — konkret („Twoja widoczność spadła o X%" / „ChatGPT nie cytuje Twojej strony" / „sezon za 5 tygodni"), nie generyczne „oto Twój audyt".

**B. Progressive disclosure** — twardy gate na starcie działa słabo, bo user nie widział wartości:
1. Pierwsze 20–30 s / scroll do punktu — bez gate'a: hak, jeden wykres, coś co realnie boli
2. Gate przy przejściu do szczegółów (pełna analiza, rekomendacje, porównanie do konkurencji)

**C. Gate = rejestracja ze zgodą** — user samodzielnie podaje mail + telefon i zaznacza zgodę (checkbox **odznaczony domyślnie**, konkretna treść celu: „zgadzam się na kontakt telefoniczny/SMS w celu omówienia wyników audytu", nie ogólne „przetwarzanie danych"). To rozwiązuje problem prawny z sekcji 9 — dobrowolna, udokumentowana zgoda zamiast cold outreachu na numer bez podstawy.

Dodatkowo:
- Wszystkie pola w jednym kroku — rozbijanie na etapy grozi porzuceniem przed dotarciem do zgody
- Double opt-in na mailu — zabezpieczenie prawne i filtr botów
- Technicznie: timer lub IntersectionObserver w React

**D. Tracking zachowania → lead scoring** — czas na stronie, klikane wykresy, powroty. Rejestracja = najsilniejszy sygnał kwalifikacyjny → automatyczny trigger, lead do Tier 3.

**E. Free konto jako retencja** — klient wraca śledzić swoją sezonowość/widoczność/cytowalność w AI. Zamienia jednorazowy lead magnet w freemium, tworzy ciągły punkt kontaktu bez ponownego cold outreachu.

---

## 8. Kanały uzupełniające

### SMS
- Open rate ~90%+ w kilka minut vs. 20–30% dla maila — dobry jako **drugi dotyk** (mail nieotwarty w 48h → SMS z linkiem)
- **Ryzyko:** art. 172 Prawa telekomunikacyjnego wymaga zgody; wyższe ryzyko niż cold mail B2B
- **Zastosowanie:** wyłącznie do numerów pozyskanych przez gate w mikro-apce (sekcja 7C), nigdy do cold acquisition

### Agenci głosowi (dzwoniący)
- Gotowe API: **Vapi, Retell AI, Bland AI, ElevenLabs Conversational AI** — nie trzeba budować od zera
- **Prawnie:** art. 172 — wymagana zgoda, ryzyko najwyższe z omawianych kanałów
- **Sekwencyjnie:** ostatni krok dla najcieplejszych leadów po gate'cie, nie masowy cold-calling

---

## 9. Kwestie prawne — zbiorczo

| Kanał | Podstawa prawna / ryzyko | Rekomendacja |
|---|---|---|
| Cold mail B2B na adres firmowy | RODO + ustawa o świadczeniu usług drogą elektroniczną; ogólny mail firmy bezpieczniejszy niż prywatny właściciela | Opt-out link, mała próba, monitoring reputacji domeny |
| Klonowany głos / wideo AI | AI Act — oznaczanie treści jako AI-generated od 2 sierpnia 2026 (UE) | Etykietowanie od początku |
| SMS marketingowy | Art. 172 Prawa telekom. — wymagana zgoda | Tylko po zgodzie z gate'a w mikro-apce |
| Automatyczne połączenia (agent głosowy) | Art. 172 — ryzyko najwyższe | Tylko po jawnej zgodzie, z konsultacją prawną |
| Scraping Map Google | Narusza ToS Google; zbieranie maili/telefonów pod RODO | Bezpieczniejsze do audytu konkretnej firmy niż do masowego budowania bazy |

**Zastrzeżenie:** powyższe nie stanowi porady prawnej — przy skalowaniu wymagana konsultacja z prawnikiem.

---

## 10. Gotowe komponenty open source

Przegląd publicznych repozytoriów — znaczna część pipeline'u jest już rozwiązana.

### Audyt techniczny/SEO
| Repo | ⭐ | Licencja | Ocena |
|---|---|---|---|
| `StJudeWasHere/seonaut` | 749 | **MIT** | Najmocniejszy kandydat. Go, Docker-compose, aktywny (push V 2026). Bezpieczny komercyjnie |
| `viasite/site-audit-seo` | 301 | NOASSERTION | JS/Puppeteer, crawl + Lighthouse na wszystkich podstronach, output JSON/CSV/XLSX. Bardzo blisko use-case'u, **ale licencja do weryfikacji** |
| `StanGirard/seo-audits-toolkit` | 804 | **brak** | Lighthouse + security headers + ekstraktory, ale brak LICENSE i ostatni commit 2023 → tylko inspiracja, nie baza kodu |
| `seo-skills/seo-audit-skill` | 336 | — | 108 reguł audytowych w 12 kategoriach — sama lista reguł wartościowa |

### Dane GBP / lead sourcing
| Repo | ⭐ | Licencja | Ocena |
|---|---|---|---|
| `omkarcloud/google-maps-scraper` | 3063 | **MIT** | 50+ punktów danych: maile, telefony, profile social, enrichment. Pokrywa jednocześnie lead sourcing i dane GBP do audytu. Największa oszczędność czasu — **ale patrz ryzyko ToS/RODO w sekcji 9** |

### Wideo
| Repo | ⭐ | Ocena |
|---|---|---|
| `calesthio/OpenMontage` | 45102 | Agentowy system produkcji wideo: ffmpeg + ElevenLabs + Remotion, 12 pipeline'ów. Pokrywa cały moduł 4 — warto podejrzeć pipeline zamiast pisać moviepy od zera |

### AEO/GEO i audyt AI
| Repo | ⭐ | Ocena |
|---|---|---|
| `Auriti-Labs/geo-optimizer-skill` | 644 | Python + MCP, audyt i tracking cytowalności w ChatGPT/Perplexity/Gemini/AI Overviews. Podstawa pod sekcję 6 |
| `zubair-trabzada/ai-marketing-claude` | 2266 | 15 skilli marketingowych z generowaniem PDF-ów dla klientów — blisko modułu 2 |
| `unifapi-agent/agents` | 534 | Agenci marketingowi przez MCP: audyty SEO, GEO/AI-visibility, local SEO, brand monitoring |

### Wnioski
1. **Moduły 1 i 4 można w dużej mierze złożyć z gotowców** — oszczędność rzędu 60–70% pracy na najcięższych częściach planu
2. **Licencje przesądzają:** MIT (seonaut, google-maps-scraper) bezpieczne; brak licencji = brak prawa użycia; NOASSERTION wymaga weryfikacji przed komercyjnym wdrożeniem
3. **Czego NIE ma gotowego:** modułu sezonowości (własna przewaga — i dobrze) oraz dynamicznej mikro-apki per-lead z gate'em (sedno lejka, własny kod)

---

## 11. Ekonomia i cele konwersji

### Koszt warstwy głosowej — niższy niż zakładano
Narracja audytu 2–3 min ≈ 2500–3000 znaków.
- Plan Creator (22 USD / 100k znaków) → ok. 0,22 USD / 1000 znaków
- **Jeden audyt ≈ 0,60 USD ≈ 2,40 zł**
- 100k znaków/mies. → ~35–37 audytów
- Flash v2.5 (~0,15 USD/1000 zn.) taniej, ale gorsza jakość narracji niż Multilingual v2

Przy CAC 1200–1800 zł koszt głosu to **<0,2% kosztu pozyskania klienta** — pomijalny.

**Wniosek operacyjny:** głos można przesunąć wcześniej w kolejności. Starter za 5 USD (30k znaków ≈ 11 audytów) wystarcza na test walidacyjny — można od razu testować mail + audio zamiast samego tekstu. Wideo zostaje na późniejszym etapie, bo tam kosztem są tygodnie pracy, nie dolary.

### Cel konwersji — 20%, ale czego?
Cel roboczy postawiony na poziomie 20%. Wymaga doprecyzowania metryki, bo różnica jest zasadnicza:

- **20% reply rate na cold mailu** = trafienie w absolutny sufit kategorii (benchmark: 20% dotyczy ręcznego wideo Loom-style, które „źle się skaluje"). Możliwe na małej, świetnie wyselekcjonowanej próbce, ryzykowne jako założenie projektowe dla całego systemu
- **20% na dalszych etapach lejka** = realne: odpowiedź → spotkanie to typowo 20–25%; rejestracja w gate'cie → rozmowa może być jeszcze wyższa, bo ci ludzie zostawili już telefon i zgodę

### Rekomendowane podejście: liczyć wstecz od liczby umów
Przykład przy 500 mailach/mies.:

| Etap | Współczynnik | Wynik |
|---|---|---|
| Wysłane maile | — | 500 |
| Odpowiedzi | 10% | 50 |
| Rozmowy | 25% | 12–13 |
| Umowy | 30% close | ~4 |

To wynik zgodny z benchmarkiem 3–8 umów/mies. przy cold mailingu — **bez zakładania rekordów kategorii**. Ryzyko przy planowaniu na 20% reply rate: przy wyniku 8% (który jest bardzo dobry) model ekonomiczny się nie spina, mimo że system działa poprawnie.

**Do rozstrzygnięcia:** która metryka jest celem — reply rate, wejścia w mikro-apkę, rejestracje za gate'em czy umowy.

---

## 12. Kolejność wdrożenia

1. Baza danych + schemat leada (fundament)
2. Moduł danych — fork/integracja `seonaut` + PageSpeed + Senuto, walidacja na 5–10 firmach
3. Warstwa AEO (`geo-optimizer-skill`) jako osobna sekcja audytu — kluczowy różnicownik
4. Dynamiczna mikro-apka z routingiem per-lead — zastępuje PDF jako główny format
5. Insight-trigger jako nagłówek + progressive disclosure + gate ze zgodą
6. Tracking zachowania → lead-scoring / tierowanie
7. Moduł głosu (ElevenLabs) — przesunięty wcześniej ze względu na pomijalny koszt
8. Test wysyłki (mail + audio, mała próba) → walidacja konwersji **przed** inwestycją w wideo
9. Moduł wideo (baza: `OpenMontage`) — dopiero po potwierdzeniu konwersji
10. Free konto jako warstwa retencyjna
11. SMS jako drugi dotyk — wyłącznie do numerów ze zgodą z gate'a
12. Agent głosowy dla najcieplejszych leadów
13. n8n spinające całość + monitoring odpowiedzi

---

*Dokument wygenerowany na podstawie sesji strategicznej z Claude jako punkt odniesienia przed rozpoczęciem prac wdrożeniowych.*
