"""Streaming table export; output is written incrementally and SQL is never executed."""
from pathlib import Path
import os
from sql_parser import ParsedSQL, SQLParseError, iter_file_statements


def _statement_table(stmt: str) -> str | None:
    import re
    m = re.match(r'(?is)^\s*INSERT\s+INTO\s+(.+?)\s+(?:\((.*?)\)\s*)?VALUES\b', stmt)
    if not m:
        return None
    from sql_parser import _unquote_identifier
    return ''.join(_unquote_identifier(m.group(1).strip()).split())


def export_table(parsed: ParsedSQL, table_name: str, output_path: Path, source_path: Path | None = None,
                 progress_callback=None, chunk_size: int = 4 * 1024 * 1024,
                 file_progress_callback=None) -> int:
    """Export CREATE + matching INSERT statements. With source_path, INSERTs are streamed from disk."""
    table = parsed.tables.get(table_name)
    if table is None:
        raise ValueError(f"Table not found: {table_name}")
    if not table.create_statement and not table.insert_statements:
        # A streaming source may still contain INSERTs even though they were not retained in ParsedSQL.
        if source_path is None:
            raise SQLParseError(f"No exportable CREATE/INSERT statements were found for {table_name}.")
    output_path = Path(output_path)
    if source_path is not None and Path(source_path).resolve() == output_path.resolve():
        raise ValueError('Output path must not overwrite the source SQL file.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + '.tmp')
    count = 0
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as out:
            if table.create_statement:
                out.write('-- Recognized CREATE TABLE statement\n\n')
                out.write(table.create_statement.rstrip(';') + ';\n\n')
            out.write('-- Recognized INSERT statements (original order)\n')
            if source_path is not None:
                for idx, stmt in enumerate(
                    iter_file_statements(source_path, chunk_size, file_progress_callback), 1
                ):
                    if _statement_table(stmt) == table_name:
                        out.write(stmt.rstrip(';') + ';\n\n')
                        count += 1
                    if progress_callback and idx % 10000 == 0:
                        progress_callback(idx, count)
            else:
                for stmt in table.insert_statements:
                    out.write(stmt.rstrip(';') + ';\n\n')
                    count += 1
        if not table.create_statement and count == 0:
            temp.unlink(missing_ok=True)
            raise SQLParseError(f"No exportable CREATE/INSERT statements were found for {table_name}.")
        os.replace(temp, output_path)
        return count
    except Exception:
        try: temp.unlink(missing_ok=True)
        except OSError: pass
        raise
