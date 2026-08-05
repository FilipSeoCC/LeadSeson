"""ElevenLabs text-to-speech client for audit narration voice-overs.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md modul 3 (glos) + sekcja 11 (ekonomia:
narracja 2-3 min ~2500-3000 znakow, koszt na planie Creator ~0.60 USD/audyt).

Free tier: 10 000 znakow/miesiac, BEZ klonowania glosu -- Instant Voice
Cloning wymaga planu Starter (5 USD/mies.). Zweryfikowane 2026-08-05: TTS
przez API DZIALA na free tier z gotowym (premade) glosem aktualnie
przypisanym do konta -- trzeba jednak uzywac voice_id z GET /v1/voices dla
TEGO konta, nie identyfikatora z przykladu/dokumentacji sprzed lat (stare ID
jak "Rachel" moga juz nie byc czescia domyslnej biblioteki i zwracaja 402
paid_plan_required, co wyglada jak blokada planu, a jest tylko nieaktualnym ID).
Klucz API musi miec wlaczone uprawnienie "Glosy: Przeczytane", zeby
list_voices()/get_usage() dzialaly (domyslnie klucze maja to wylaczone).

Wymaga ELEVENLABS_API_KEY w .env. Uzyty model to eleven_multilingual_v2,
ktory wspiera polski (Flash v2.5 jest tanszy ale gorszej jakosci -- sekcja 11
rekomenduje Multilingual v2 dla samej narracji).
"""
import os

import requests

API_BASE = "https://api.elevenlabs.io/v1"
# "Adam" -- premade voice potwierdzony dzialajacy przez API na free tier
# 2026-08-05. Starszy/legacy ID "Rachel" (21m00Tcm4TlvDq8ikWAM) nie jest juz
# czescia domyslnej biblioteki kont i zwraca 402 paid_plan_required -- lista
# aktualnych glosow konta: GET /v1/voices (wymaga uprawnienia "Glosy: Przeczytane"
# na kluczu API, domyslnie wylaczonego).
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_TIMEOUT = 60


class ElevenLabsConfigError(RuntimeError):
    """Raised when ELEVENLABS_API_KEY is missing."""


class ElevenLabsAPIError(RuntimeError):
    """Wraps an ElevenLabs error response with its actual `detail.message`.

    Confirmed 2026-08-05: a stale/legacy voice_id (e.g. the old "Rachel" ID
    21m00Tcm4TlvDq8ikWAM, no longer part of the current default library) gets
    402 payment_required / paid_plan_required even on accounts that CAN use
    TTS via API on the free tier -- it is not a blanket free-tier API ban.
    Always resolve voice_id from GET /v1/voices for the current account
    (list_voices() below) rather than hardcoding an ID found in old docs/
    examples; DEFAULT_VOICE_ID is one confirmed to work as of that date, but
    accounts differ in which voices are actually provisioned to them.
    """


def _api_key() -> str:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ElevenLabsConfigError("ELEVENLABS_API_KEY nie jest ustawiony w .env.")
    return api_key


def get_usage() -> dict:
    """Status limitu znakow -- sprawdz PRZED synteza, zeby nie wypasc z darmowego limitu."""
    resp = requests.get(f"{API_BASE}/user/subscription", headers={"xi-api-key": _api_key()}, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    used = data.get("character_count") or 0
    limit = data.get("character_limit") or 0
    return {
        "characters_used": used,
        "characters_limit": limit,
        "characters_remaining": limit - used,
        "reset_unix": data.get("next_character_count_reset_unix"),
    }


def list_voices() -> list[dict]:
    resp = requests.get(f"{API_BASE}/voices", headers={"xi-api-key": _api_key()}, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("voices", [])


def synthesize_narration(text: str, voice_id: str = DEFAULT_VOICE_ID, model_id: str = DEFAULT_MODEL_ID) -> bytes:
    """Zwraca surowe bajty MP3.

    Raises ElevenLabsConfigError if no API key is configured, and
    requests.HTTPError on API failure (np. przekroczony limit znakow,
    nieprawidlowy voice_id) -- caller decides how to record that as a
    failed generation.
    """
    headers = {"xi-api-key": _api_key(), "Content-Type": "application/json", "Accept": "audio/mpeg"}
    payload = {"text": text, "model_id": model_id}
    resp = requests.post(f"{API_BASE}/text-to-speech/{voice_id}", headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
    if not resp.ok:
        try:
            message = resp.json()["detail"]["message"]
        except (ValueError, KeyError, TypeError):
            message = resp.text
        raise ElevenLabsAPIError(f"ElevenLabs {resp.status_code}: {message}")
    return resp.content
