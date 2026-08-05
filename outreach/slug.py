"""Slug generation for the per-lead micro-app URL (sekcja 7: audyt.ai-ops.pl/nazwa-firmy)."""
import re
import unicodedata

_LEGAL_SUFFIXES = re.compile(
    r"\b(sp\.?\s*z\s*o\.?\s*o\.?|s\.?p\.?\s*z\s*o\.?\s*o\.?|spolka\s+z\s+ograniczona\s+odpowiedzialnoscia|"
    r"s\.?a\.?|sa|sc|s\.?c\.?|jednoosobowa\s+dzialalnosc\s+gospodarcza)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify_company_name(company_name: str) -> str:
    """Turn a Polish company name into a readable URL slug, stripping legal suffixes.

    'Demo HVAC Sp. z o.o.' -> 'demo-hvac'. Diacritics are normalized (ą->a etc.)
    since URL slugs should stay ASCII-safe.
    """
    normalized = unicodedata.normalize("NFKD", company_name).encode("ascii", "ignore").decode("ascii")
    without_suffix = _LEGAL_SUFFIXES.sub("", normalized)
    slug = _NON_ALNUM.sub("-", without_suffix.lower()).strip("-")
    return slug or "firma"
