"""Send (or preview) an outreach email for one lead.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12: test wysylki (mail+audio,
mala proba) przed inwestycja w modul wideo.

WAZNE: to jest infrastruktura do testu wysylki NA WLASNY ADRES, nie do
wysylki na prawdziwych leadow bez wyraznej decyzji/zgody -- patrz sekcja 9
(RODO/cold mail) i sekcja 7C (gate ze zgoda) w dokumencie strategii.

Usage:
    python scripts/send_outreach_email.py --slug <slug> --to twoj@adres.pl --dry-run
    python scripts/send_outreach_email.py --slug <slug> --to twoj@adres.pl
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outreach import repository  # noqa: E402
from outreach.db import Base, SessionLocal, engine  # noqa: E402
from outreach.send.outreach_email import build_outreach_email, send_outreach_email_for_lead  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", required=True, help="Lead.slug (patrz /audyt/{slug})")
    parser.add_argument("--to", required=True, help="Adres odbiorcy testu (Twoj wlasny, nie realny lead)")
    parser.add_argument("--dry-run", action="store_true", help="Zbuduj i wypisz tresc, nie wysylaj")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    lead = repository.get_lead_by_slug(db, args.slug)
    if lead is None:
        print(f"Brak leada o slug={args.slug!r}.")
        db.close()
        return

    content = build_outreach_email(lead, db)
    print(f"--- Mail dla {lead.company_name} -> {args.to} ---")
    print("Temat:", content["subject"])
    print("Link:", content["audyt_url"])
    print()
    print(content["html_body"])
    print("---")

    if args.dry_run:
        print("Dry-run: nie wyslano.")
        db.close()
        return

    event = send_outreach_email_for_lead(db, lead, args.to)
    if event.status == "sent":
        print(f"OK: wyslano, Resend id={event.content_ref}")
    else:
        print(f"BLAD: {event.content_ref}")

    db.close()


if __name__ == "__main__":
    main()
