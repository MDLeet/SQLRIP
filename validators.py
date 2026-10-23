from pathlib import Path

def validate_sql_file(path: Path) -> None:
    if not str(path).strip():
        raise ValueError("Path cannot be empty.")
    if not path.exists():
        raise ValueError("File does not exist.")
    if not path.is_file():
        raise ValueError("Path is not a regular file.")
    if path.suffix.lower() != ".sql":
        raise ValueError("File must have a .sql extension.")
    try:
        with path.open("rb") as stream:
            sample = stream.read(4096)
    except OSError as exc:
        raise ValueError(f"File is not readable: {exc}") from exc
    if not sample:
        raise ValueError("File is empty.")
    # Lightweight content sanity check, not a guarantee that SQL is valid.
    printable = sum(b in (9, 10, 13) or 32 <= b <= 126 or b >= 128 for b in sample)
    if printable / len(sample) < 0.75:
        raise ValueError("File does not look like a text SQL dump.")
