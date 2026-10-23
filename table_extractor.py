from sql_parser import ParsedSQL

def list_tables(parsed: ParsedSQL) -> list[str]:
    """Return unique table names in first-seen order."""
    return list(parsed.tables.keys())
