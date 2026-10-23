"""Streaming, conservative SQL dump scanner. It never executes SQL."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import codecs
import re
from typing import Iterable, Iterator, TextIO

class SQLParseError(ValueError):
    pass

@dataclass
class TableData:
    name: str
    create_statement: str | None = None
    insert_statements: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)

@dataclass
class ParsedSQL:
    tables: dict[str, TableData] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    statement_count: int = 0


def _split_chunks(chunks: Iterable[str]) -> Iterator[str]:
    """Yield statements split at semicolons outside quotes/comments, across chunk edges."""
    state = "normal"
    dollar_tag: str | None = None
    buf: list[str] = []
    pending = ""
    # The pending suffix lets two-character tokens and dollar tags span chunks.
    for chunk in chunks:
        text = pending + chunk
        pending = ""
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            nxt = text[i+1] if i+1 < n else ""
            if state == "normal":
                if ch == "'": state = "single"; buf.append(ch); i += 1; continue
                if ch == '"': state = "double"; buf.append(ch); i += 1; continue
                if ch == '`': state = "backtick"; buf.append(ch); i += 1; continue
                if ch == '[': state = "bracket"; buf.append(ch); i += 1; continue
                if ch == '-' and nxt == '-': state = "line_comment"; i += 2; continue
                if ch == '#': state = "line_comment"; i += 1; continue
                if ch == '/' and nxt == '*': state = "block_comment"; i += 2; continue
                if ch == '$':
                    m = re.match(r'\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$', text[i:])
                    if m:
                        tag = m.group(0)
                        # If the tag may be cut at the end of this chunk, wait for more input.
                        if i + len(tag) == n and not text.endswith(tag):
                            pending = text[i:]; break
                        dollar_tag = tag; state = "dollar"; buf.append(tag); i += len(tag); continue
                    suffix = text[i:]
                    if re.fullmatch(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?', suffix):
                        pending = suffix; break
                if ch == ';':
                    stmt = ''.join(buf).strip()
                    if stmt: yield stmt
                    buf = []; i += 1; continue
                buf.append(ch); i += 1; continue
            if state == "single":
                buf.append(ch)
                if ch == '\\' and i+1 < n:
                    i += 1; buf.append(text[i])
                elif ch == "'" and nxt == "'":
                    i += 1; buf.append(text[i])
                elif ch == "'": state = "normal"
                elif i+1 == n and ch == '\\':
                    pending = buf.pop(); break
                i += 1; continue
            if state in ("double", "backtick", "bracket"):
                buf.append(ch)
                close = {'double':'"', 'backtick':'`', 'bracket':']'}[state]
                if ch == close and nxt == close:
                    i += 1; buf.append(text[i])
                elif ch == close: state = "normal"
                i += 1; continue
            if state == "dollar":
                if text.startswith(dollar_tag or '', i):
                    buf.append(dollar_tag or ''); i += len(dollar_tag or ''); state = "normal"
                elif dollar_tag and text[i:] == dollar_tag[:len(text)-i]:
                    pending = text[i:]; break
                else:
                    buf.append(ch); i += 1
                continue
            if state == "line_comment":
                if ch in '\r\n': buf.append(ch); state = "normal"
                i += 1; continue
            if state == "block_comment":
                if ch == '*' and nxt == '/': i += 2; state = "normal"
                elif i+1 == n and ch == '*': pending = '*'; break
                else: i += 1
                continue
    # Process final pending text as ordinary continuation; incomplete constructs error below.
    if pending:
        if state == "normal": buf.extend(pending)
        else: buf.extend(pending)
    if state in ("single", "double", "backtick", "bracket", "block_comment", "dollar"):
        raise SQLParseError(f"Unterminated SQL token/comment (state={state}).")
    tail = ''.join(buf).strip()
    if tail: yield tail


def iter_sql_statements(stream: TextIO, chunk_size: int = 4 * 1024 * 1024,
                        progress_callback=None, total_bytes: int | None = None) -> Iterator[str]:
    """Yield SQL statements incrementally and optionally report byte progress."""
    def chunks():
        last_reported = -1
        while True:
            part = stream.read(chunk_size)
            if not part:
                break
            if progress_callback:
                try:
                    processed = stream.tell()
                except (OSError, ValueError):
                    processed = 0
                progress_callback(min(processed, total_bytes) if total_bytes else processed,
                                  total_bytes)
            yield part
        if progress_callback:
            progress_callback(total_bytes or 0, total_bytes)
    yield from _split_chunks(chunks())


def _unquote_identifier(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0], value[-1]) in {('`','`'),('"','"'),('[',']')}):
        return value[1:-1].replace(value[0]*2, value[0])
    return value


def _extract_columns(body: str) -> list[str]:
    depth = 0; quote = None; token = []; pieces = []; i = 0
    while i < len(body):
        ch = body[i]; nxt = body[i+1] if i+1 < len(body) else ""
        if quote:
            token.append(ch)
            if ch == quote and nxt == quote: i += 1; token.append(body[i])
            elif ch == quote: quote = None
        elif ch in ("'", '"', '`'): quote = ch; token.append(ch)
        elif ch == '[': quote = ']'; token.append(ch)
        elif ch == '(': depth += 1; token.append(ch)
        elif ch == ')':
            if depth == 0:
                piece = ''.join(token).strip()
                if piece: pieces.append(piece)
                break
            depth -= 1; token.append(ch)
        elif ch == ',' and depth == 0: pieces.append(''.join(token).strip()); token = []
        else: token.append(ch)
        i += 1
    cols = []
    for piece in pieces:
        if not piece or re.match(r'(?is)^(CONSTRAINT|PRIMARY|UNIQUE|KEY|INDEX|FOREIGN|CHECK|EXCLUDE)\b', piece): continue
        m = re.match(r'(?s)^\s*(`[^`]+`|"[^"]+"|\[[^]]+\]|[^\s]+)', piece)
        if m: cols.append(_unquote_identifier(m.group(1)))
    return cols


def _consume_statement(result: ParsedSQL, stmt: str, store_inserts: bool) -> None:
    result.statement_count += 1
    m = re.match(r'(?is)^\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(.+?)\s*\(', stmt)
    if m:
        name = re.sub(r'\s+', '', _unquote_identifier(m.group(1).strip()))
        table = result.tables.setdefault(name, TableData(name))
        if table.create_statement and table.create_statement != stmt:
            result.warnings.append(f"Multiple CREATE TABLE statements for {name}; keeping the last.")
        table.create_statement = stmt + ';'
        table.columns = _extract_columns(stmt[m.end():])
        return
    m = re.match(r'(?is)^\s*INSERT\s+INTO\s+(.+?)\s+(?:\((.*?)\)\s*)?VALUES\b', stmt)
    if m:
        name = re.sub(r'\s+', '', _unquote_identifier(m.group(1).strip()))
        table = result.tables.setdefault(name, TableData(name))
        if store_inserts: table.insert_statements.append(stmt + ';')
        return
    if re.match(r'(?is)^\s*(COPY\s+.+\s+FROM\s+STDIN|LOAD\s+DATA|DELIMITER\s+)', stmt):
        result.warnings.append("Detected data-loading syntax not supported for row extraction.")


def parse_sql_text(text: str) -> ParsedSQL:
    result = ParsedSQL()
    for stmt in _split_chunks([text]): _consume_statement(result, stmt, True)
    return result


def _open_sql_text(path: Path):
    # Select encoding from a small sample; then stream without reading the whole file.
    with path.open('rb') as raw:
        sample = raw.read(65536)
    try:
        sample.decode('utf-8-sig')
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        encoding = 'cp1252'
    return path.open('r', encoding=encoding, errors='strict', newline='')


def parse_sql_file(path: Path, chunk_size: int = 4 * 1024 * 1024, progress_callback=None) -> ParsedSQL:
    """Stream the file and retain schema metadata only (no INSERT bodies in memory)."""
    path = Path(path)
    result = ParsedSQL()
    try:
        total_bytes = path.stat().st_size
        with _open_sql_text(path) as stream:
            for stmt in iter_sql_statements(stream, chunk_size, progress_callback, total_bytes):
                _consume_statement(result, stmt, False)
    except UnicodeDecodeError as exc:
        raise SQLParseError("File encoding is not UTF-8 or Windows-1252; convert it to UTF-8.") from exc
    except OSError as exc:
        raise SQLParseError(f"Could not read SQL file: {exc}") from exc
    if result.statement_count == 0 and path.stat().st_size:
        result.warnings.append("No SQL statements were recognized.")
    return result


def iter_file_statements(path: Path, chunk_size: int = 4 * 1024 * 1024,
                         progress_callback=None) -> Iterator[str]:
    path = Path(path)
    try:
        total_bytes = path.stat().st_size
        with _open_sql_text(path) as stream:
            yield from iter_sql_statements(stream, chunk_size, progress_callback, total_bytes)
    except UnicodeDecodeError as exc:
        raise SQLParseError("File encoding is not UTF-8 or Windows-1252; convert it to UTF-8.") from exc
    except OSError as exc:
        raise SQLParseError(f"Could not read SQL file: {exc}") from exc
