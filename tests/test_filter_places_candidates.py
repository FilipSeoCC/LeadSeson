import pandas as pd
from datetime import date

from bulk_crawler import filter_places_candidates


def _row(domain_key, end_date, row_id="1"):
    return {"domain_key": domain_key, "end_date": end_date, "id": row_id}


def test_excludes_contract_ending_in_h2_current_year():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("h2-end.pl", "2026-09-15"),
        _row("next-year.pl", "2027-03-01"),
    ])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["next-year.pl"]


def test_excludes_contract_already_ended():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("already-ended.pl", "2026-01-10"),
        _row("still-active.pl", "2027-01-10"),
    ])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["still-active.pl"]


def test_keeps_rows_with_blank_end_date():
    today = date(2026, 7, 27)
    df = pd.DataFrame([_row("no-end-date.pl", "")])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["no-end-date.pl"]


def test_excludes_debtor_domain_keys():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("debtor.pl", "2027-01-10", row_id="42"),
        _row("ok.pl", "2027-01-10", row_id="43"),
    ])
    result = filter_places_candidates(df, today=today, debtor_domain_keys={"debtor.pl"})
    assert list(result["domain_key"]) == ["ok.pl"]


def test_empty_dataframe_returns_empty():
    df = pd.DataFrame(columns=["domain_key", "end_date", "id"])
    result = filter_places_candidates(df, today=date(2026, 7, 27))
    assert result.empty
