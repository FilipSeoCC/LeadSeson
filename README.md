# LeadSeason

Strategiczny plan wdrożenia w Customer Care: PLAN_CUSTOMER_CARE_LEADSEASON.md.

Generator leadów sezonowych dla dużych list klientów SEO/WWW.

Input:

```text
XML/XLSX/CSV with id, detail_id/ditel, nip, domain, company, service
```

Output:

```text
CSV / XLSX / JSON with one row per input record/contract
```

The crawler deduplicates domains, crawls each unique domain once, caches the domain result, and then maps that result back to every XML record.

## Run CLI

```powershell
python bulk_crawler.py --input sample_input.xml --output output/results.csv --workers 12
```

XLSX template generated from KartaAccount is also supported:

```powershell
python bulk_crawler.py --input templates/leadflame_bulk_upload_template_from_kartaaccount.xlsx --output output/kartaaccount_results.csv --workers 12
```

Test only first N records:

```powershell
python bulk_crawler.py --input clients.xml --output output/test.csv --limit 500
```

Ignore cache:

```powershell
python bulk_crawler.py --input clients.xml --output output/results.csv --force
```

## Run app

```powershell
START_BULK_APP.bat
```

The starter opens Streamlit on:

```text
http://localhost:8510
```

If an older tab on `8502` or `8503` is still open, close it and use `8504`.

## Run backend API

Local backend for the LeadSeason pipeline:

```powershell
START_BACKEND.bat
```

API:

```text
http://127.0.0.1:8010
```

OpenAPI docs:

```text
http://127.0.0.1:8010/docs
```

On Vercel the same backend is exposed through:

```text
/api/health
/api/dashboard/summary
/api/q4/summary
/api/q4/actions
```

Key endpoints:

- `GET /health` - backend status
- `GET /outputs` - files available in `output/`
- `GET /dashboard/summary` - operational metrics for the active output file
- `GET /q4/summary` - Q4 action base summary
- `GET /q4/actions?limit=100` - JSON list of Q4 customers/domains to act on
- `GET /q4/actions.xlsx` - downloadable Q4 action file
- `POST /uploads` - upload XLSX/CSV/XML input file
- `POST /crawl/jobs` - start crawl/enrichment job in the backend
- `GET /crawl/jobs/{job_id}` - check crawl job status

Architecture direction:

```text
Streamlit frontend -> FastAPI backend -> crawler / Places / LLM export / Senuto matrix / Q4 action base
```

## What It Crawls

FAST homepage crawl:

- title
- meta description
- meta keywords
- OpenGraph title/description
- canonical
- lang
- h1/h2/h3
- schema.org types
- menu/offer links
- body text sample

## Classification

Rule-based industry classifier:

- HVAC
- e-commerce / wyposażenie domu / porcelana
- ogrody
- motoryzacja/opony
- gastronomia/eventy
- przeprowadzki
- edukacja
- medycyna/beauty
- budownictwo/remonty
- hotel/noclegi

For every row it adds:

- `detected_industry`
- `industry_confidence`
- `season_peak`
- `contact_start`
- `recommended_product`
- `lead_topic`
- `evidence_keywords`

## Optional Google Places / GMB category enrichment

The homepage crawl stays enabled and remains the main source of website text for AI analysis. Google Places can be added as a second signal for business category / GMB-like industry context.

The first business seasonality matrix is stored in:

```text
config/leadseason_seasonality_matrix.csv
```

Run with Places from CLI:

```powershell
$env:GOOGLE_PLACES_API_KEY="YOUR_KEY"
python bulk_crawler.py --input templates/przykladowy_plik_100_rekordow_leadseason.xlsx --output output/places_test.xlsx --limit 100 --places
```

Additional output columns:

- `places_status`
- `places_id`
- `places_name`
- `places_address`
- `places_primary_type`
- `places_types`
- `places_business_status`
- `places_phone`
- `places_website`
- `places_match_confidence`
- `places_match_reasons`
- `places_industry_hint`

If `detected_industry` is `Nieokreślona` and Places returns a confident match, the crawler can use `places_industry_hint` as the detected industry.

Additionally, each run creates:

```text
<output-name>.summary.json
```

with total records, unique domains, crawl statuses and industry distribution.

## Important

Google `site:` scraping is not used as the main method. At this scale it is unstable and likely to hit captcha/blocking. The stable MVP is homepage metadata + headings + menu + text sample.
