"""Column-name-only scan; never reads or prints row values."""
import re
from sql_parser import ParsedSQL

DEFAULT_KEYWORDS = {
    "email", "password", "user", "username", "user_id", "first_name",
    "last_name", "full_name", "phone", "address", "dob", "date_of_birth",
    "birth_date", "card_number", "cvc", "ccv", "exp_month", "exp_year",
}

def _normalize(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.casefold()).strip('_')

def find_user_related_tables(parsed: ParsedSQL, keywords=None, partial: bool = False) -> dict[str, list[str]]:
    keys = {_normalize(k) for k in (keywords or DEFAULT_KEYWORDS)}
    matches = {}
    for table_name, table in parsed.tables.items():
        found = []
        for col in table.columns:
            norm = _normalize(col)
            if norm in keys or (partial and any(k and k in norm for k in keys)):
                found.append(col)
        if found:
            matches[table_name] = list(dict.fromkeys(found))
    return matches
