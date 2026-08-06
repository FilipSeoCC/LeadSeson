"""Narration script generator for the audit voice-over.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md modul 2 opisuje "Claude API -- narracja
audytu z JSON-a danych" jako osobny modul, ktorego jeszcze nie zbudowalismy
(brak ANTHROPIC_API_KEY podpietego w tym repo). Ten generator jest natomiast
deterministycznym szablonem Pythonowym -- wystarczajacy, zeby przetestowac
jakosc/koszt samego ElevenLabs (sekcja 11) bez czekania na modul 2. Podmiana
na prawdziwa narracje z Claude to naturalny nastepny krok, nie wymaga zmian
w outreach/voice/elevenlabs_tts.py -- ten modul konsumuje zwykly str.

Cel dlugosci z sekcji 11: 2-3 min ~ 2500-3000 znakow. Rzeczywista dlugosc
zalezy od tego, ile audytow ma dany lead -- to miekki cel, nie twardy limit.
"""
from sqlalchemy.orm import Session

from outreach import models
from outreach.audit_utils import latest_audits_by_type

AUDIT_SPOKEN_LABELS = {
    "seo": "audyt SEO na Twojej stronie",
    "pagespeed": "szybkość ładowania strony",
    "aeo_geo": "widoczność w narzędziach AI, takich jak ChatGPT i Perplexity",
    "senuto": "sezonowość Twojej branży",
    "places": "profil w Google Maps",
    "seasonality": "sezonowość Twojej branży",
}

# Zrodla summary_text, ktore mowimy na glos doslownie: tylko nasze wlasne,
# polskojezyczne audyty (seo_onpage.py). aeo_geo/pagespeed pochodza z
# zewnetrznych bibliotek (geo-optimizer-skill, PageSpeed) i ich issues/
# recommendations sa po angielsku -- wklejenie ich wprost do polskiej
# narracji brzmi w TTS koszmarnie (model probuje wymowic angielskie zdanie
# polska fonetyka). Dla tych audytow mowimy tylko wynik liczbowy.
QUOTABLE_SUMMARY_TYPES = {"seo", "senuto", "seasonality"}


def _score_comment(score: float) -> str:
    if score >= 80:
        return "to bardzo dobry wynik"
    if score >= 50:
        return "jest tu jeszcze sporo do poprawy"
    return "to wynik, który wymaga pilnej uwagi"


def build_narration_script(lead: models.Lead, db: Session | None = None) -> str:
    """Buduje tekst narracji po polsku, gotowy do syntezy TTS."""
    audits = latest_audits_by_type(lead, db)
    parts = [
        f"Dzień dobry. Przygotowaliśmy dla firmy {lead.company_name} krótki audyt widoczności online.",
    ]

    ordered_types = ["aeo_geo", "seo", "pagespeed", "senuto", "seasonality", "places"]
    covered = [t for t in ordered_types if t in audits]
    for audit_type in covered:
        audit = audits[audit_type]
        label = AUDIT_SPOKEN_LABELS.get(audit_type, audit_type)
        if audit.score is not None:
            parts.append(f"Sprawdziliśmy {label}. Wynik to {audit.score:.0f} na 100 — {_score_comment(audit.score)}.")
        else:
            parts.append(f"Sprawdziliśmy {label}.")
        if audit_type in QUOTABLE_SUMMARY_TYPES and audit.summary_text:
            first_issue = audit.summary_text.split(";")[0].strip()
            if first_issue and not first_issue.lower().startswith("brak"):
                parts.append(first_issue.rstrip(".") + ".")

    if lead.season_peak:
        parts.append(
            f"Dodatkowo, Twoja branża wchodzi w sezon szczytowy w okresie: {lead.season_peak}. "
            "Warto przygotować się na ten moment z wyprzedzeniem."
        )

    if not covered and not lead.season_peak:
        parts.append("Pełne wyniki audytu przygotujemy wkrótce.")

    parts.append(
        "Pełny raport z konkretnymi rekomendacjami czeka na Ciebie w mikroaplikacji, "
        "do której link wysłaliśmy razem z tą wiadomością. "
        "Jeśli chcesz omówić wyniki, chętnie umówimy krótką rozmowę."
    )

    return " ".join(parts)
