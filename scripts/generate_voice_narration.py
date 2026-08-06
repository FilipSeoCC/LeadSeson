"""Generate a voice narration for one lead's audit and synthesize it via ElevenLabs.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12, krok 5 (modul glosu,
przesuniety wczesniej w kolejnosci ze wzgledu na pomijalny koszt -- sekcja 11).

Free tier ElevenLabs = 10 000 znakow/miesiac. Ten skrypt sprawdza pozostaly
limit PRZED synteza i odmawia, jesli tekst by go przekroczyl -- lepiej
przerwac niz zuzyc caly darmowy budzet na jeden nieudany test.

Usage:
    python scripts/generate_voice_narration.py --slug andruszkiewicz-aleksander-4
    python scripts/generate_voice_narration.py --slug ... --dry-run   # tylko pokaz tekst, nie wolaj API
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outreach import repository  # noqa: E402
from outreach.db import Base, SessionLocal, engine  # noqa: E402
from outreach.voice.elevenlabs_tts import (  # noqa: E402
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE_ID,
    ElevenLabsAPIError,
    ElevenLabsConfigError,
    get_usage,
    synthesize_narration,
)
from outreach.voice.script import build_narration_script

AUDIO_DIR = Path(__file__).resolve().parent.parent / "outreach" / "data" / "audio"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", required=True, help="Lead.slug (patrz /audyt/{slug})")
    parser.add_argument("--voice-id", default=DEFAULT_VOICE_ID)
    parser.add_argument("--dry-run", action="store_true", help="Zbuduj i wypisz tekst, nie wolaj ElevenLabs")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    lead = repository.get_lead_by_slug(db, args.slug)
    if lead is None:
        print(f"Brak leada o slug={args.slug!r}.")
        return

    script_text = build_narration_script(lead, db)
    print(f"--- Narracja dla {lead.company_name} ({len(script_text)} znakow) ---")
    print(script_text)
    print("---")

    if args.dry_run:
        print("Dry-run: nie wywolano ElevenLabs.")
        db.close()
        return

    try:
        usage = get_usage()
    except ElevenLabsConfigError as exc:
        print(f"BLAD konfiguracji: {exc}")
        db.close()
        return

    print(f"Limit ElevenLabs: {usage['characters_used']}/{usage['characters_limit']} znakow zuzyte "
          f"({usage['characters_remaining']} pozostalo).")

    already_used_locally = repository.total_voice_characters_used(db)
    print(f"Zuzyte dotychczas przez ten skrypt (log lokalny): {already_used_locally} znakow.")

    if len(script_text) > usage["characters_remaining"]:
        print(
            f"PRZERWANO: narracja ma {len(script_text)} znakow, a pozostalo tylko "
            f"{usage['characters_remaining']} na koncie ElevenLabs. Nie wysylam zapytania."
        )
        db.close()
        return

    print("Wysylam do ElevenLabs...")
    try:
        audio_bytes = synthesize_narration(script_text, voice_id=args.voice_id)
    except ElevenLabsAPIError as exc:
        print(f"PRZERWANO: {exc}")
        db.close()
        return

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO_DIR / f"{lead.id}.mp3"
    audio_path.write_bytes(audio_bytes)

    repository.record_voice_narration(
        db,
        lead.id,
        script_text=script_text,
        characters_used=len(script_text),
        voice_id=args.voice_id,
        model_id=DEFAULT_MODEL_ID,
        audio_path=str(audio_path),
    )

    print(f"OK: zapisano {len(audio_bytes)} bajtow audio do {audio_path}")
    print(f"Zuzyto {len(script_text)} znakow z limitu ElevenLabs.")

    db.close()


if __name__ == "__main__":
    main()
