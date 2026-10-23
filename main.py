from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

from sql_parser import parse_sql_file, SQLParseError
from table_extractor import list_tables
from column_analyzer import find_user_related_tables
from table_exporter import export_table
from validators import validate_sql_file

logging.basicConfig(
    filename="sql_analyzer.log",
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
)

BANNER = r"""
===========================================================
 $$$$$$\   $$$$$$\  $$\       $$$$$$$\  $$$$$$\ $$$$$$$\  
$$  __$$\ $$  __$$\ $$ |      $$  __$$\ \_$$  _|$$  __$$\ 
$$ /  \__|$$ /  $$ |$$ |      $$ |  $$ |  $$ |  $$ |  $$ |
\$$$$$$\  $$ |  $$ |$$ |      $$$$$$$  |  $$ |  $$$$$$$  |
 \____$$\ $$ |  $$ |$$ |      $$  __$$<   $$ |  $$  ____/ 
$$\   $$ |$$ $$\$$ |$$ |      $$ |  $$ |  $$ |  $$ |      
\$$$$$$  |\$$$$$$ / $$$$$$$$\ $$ |  $$ |$$$$$$\ $$ |      
 \______/  \___$$$\ \________|\__|  \__|\______|\__|      
               \___|                                      
                                                          
       Coded By github.com/MDLeet                                                   
       SQL Analyzer (offline)
==========================================================
Type 'help' to see commands; type 'exit' to quit.
"""

# ANSI colors work in modern Windows Terminal, PowerShell, and Linux terminals.
# If stdout is redirected, disable colors to keep output clean.
_USE_COLOR = sys.stdout.isatty()


def color(text: object, code: str) -> str:
    value = str(text)
    return f"\033[{code}m{value}\033[0m" if _USE_COLOR else value


def prompt_sql_file() -> Path:
    while True:
        raw = input("SQL file path (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        path = Path(raw.strip('"').strip("'")).expanduser()
        try:
            validate_sql_file(path)
            return path.resolve()
        except (OSError, ValueError) as exc:
            print(color(f"File error: {exc}", "31"))


def progress_bar(label: str, processed: int, total: int | None, state: dict) -> None:
    if not total or total <= 0:
        return
    percent = min(100, int(processed * 100 / total))
    # Avoid flooding the terminal: update once per percentage point, or every 10% if redirected.
    step = 1 if sys.stdout.isatty() else 10
    if percent != 100 and percent // step == state.get("last_bucket", -1):
        return
    state["last_bucket"] = percent // step
    width = 28
    filled = min(width, int(width * percent / 100))
    bar = "█" * filled + "░" * (width - filled)
    line = f"{label} [{bar}] {percent:3d}% ({processed / (1024 ** 3):.2f}/{total / (1024 ** 3):.2f} GiB)"
    if sys.stdout.isatty():
        print("\r" + line, end="", flush=True)
    else:
        print(line, flush=True)
    if percent >= 100:
        print(flush=True)


def load_metadata(path: Path):
    print(color(f"Analyzing {path} (one initial streaming pass)...", "36"))
    state = {}
    parsed = parse_sql_file(path, progress_callback=lambda done, total: progress_bar("Analyze", done, total, state))
    tables = list_tables(parsed)
    matches = find_user_related_tables(parsed)
    print(color(f"Analysis cached: {len(tables)} tables found.", "32"))
    for warning in parsed.warnings:
        print(color(f"Warning: {warning}", "33"))
    return parsed, tables, matches


def show_help() -> None:
    print("""
Commands (you can run them repeatedly without returning to a menu):
  tables / 1       List all table names
  users / 2        List tables with user-related column names
  overview / 5     List every table; user-related tables are highlighted
  export / 3       Export one table's CREATE + matching INSERT statements to TXT
  open / 4         Choose another SQL file and rebuild the session cache
  status           Show the selected file and cached table count
  help / ?         Show this help
  exit / quit / 0  Exit the program

Table analysis is cached for the current file. Export scans the source file
again incrementally to find that table's INSERT statements, without keeping
all INSERT data in memory.
""")


def show_tables(tables: list[str]) -> None:
    if not tables:
        print(color("No tables were recognized.", "33"))
        return
    for i, name in enumerate(tables, 1):
        print(f"{color(f'{i:>4}.', '90')} {color(name, '36')}")
    print(color(f"Total tables: {len(tables)}", "32"))


def show_user_tables(matches: dict[str, list[str]]) -> None:
    if not matches:
        print(color("No tables matched the user-related column keywords.", "33"))
        return
    for i, (table, cols) in enumerate(matches.items(), 1):
        print(f"{color(f'{i:>4}.', '90')} {color(table, '31;1')}  {color('columns: ' + ', '.join(cols), '33')}")
    print(color(f"Matching tables: {len(matches)}", "32"))


def show_overview(tables: list[str], matches: dict[str, list[str]]) -> None:
    if not tables:
        print(color("No tables were recognized.", "33"))
        return
    sensitive = set(matches)
    print("\nTable overview (red = contains user-related column names):")
    for i, name in enumerate(tables, 1):
        if name in sensitive:
            marker = color("[USER DATA]", "31;1")
            table_text = color(name, "31;1")
        else:
            marker = color("[regular]", "90")
            table_text = color(name, "36")
        cols = matches.get(name, [])
        suffix = f" — {', '.join(cols)}" if cols else ""
        print(f"{i:>4}. {table_text} {marker}{color(suffix, '33')}")
    print(f"\nTables: {len(tables)} | User-related: {len(sensitive)} | Other: {len(tables) - len(sensitive)}")


def choose_export(parsed, tables: list[str], path: Path) -> None:
    if not tables:
        print(color("No tables found to export.", "33"))
        return
    show_tables(tables)
    selected = input("Table number or exact table name (blank to cancel): ").strip()
    if not selected:
        print("Export cancelled.")
        return
    if selected.isdigit() and 1 <= int(selected) <= len(tables):
        table = tables[int(selected) - 1]
    else:
        table = selected
    if table not in parsed.tables:
        print(color(f"Table not found: {table}", "31"))
        return

    default_name = f"{table.replace('.', '_')}_export.txt"
    output_raw = input(f"Output TXT path [default: {default_name}]: ").strip()
    output = Path(output_raw.strip('"').strip("'")) if output_raw else Path(default_name)
    if output.suffix.lower() != ".txt":
        output = output.with_suffix(".txt")
    if output.exists():
        overwrite = input(f"{output} exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Export cancelled.")
            return

    print(color("Exporting incrementally; the source is scanned for matching INSERTs...", "36"))

    def export_progress(scanned: int, matched: int) -> None:
        # Statement count is useful as a secondary indicator on very unusual text streams.
        if scanned % 100000 == 0:
            print(f"\nScanned {scanned:,} SQL statements; exported {matched:,} INSERTs...", flush=True)

    progress_state = {}
    file_progress = lambda done, total: progress_bar("Export", done, total, progress_state)
    exported = export_table(parsed, table, output, source_path=path,
                            progress_callback=export_progress,
                            file_progress_callback=file_progress)
    if not sys.stdout.isatty():
        print()
    print(color(f"Export complete: {output.resolve()} ({exported:,} INSERT statements)", "32"))


def main() -> None:
    print(color(BANNER, "36;1"))
    try:
        path = prompt_sql_file()
    except (KeyboardInterrupt, EOFError, SystemExit):
        print("\nGoodbye.")
        return

    parsed = None
    tables: list[str] = []
    matches: dict[str, list[str]] = {}

    while True:
        try:
            # Cache metadata once per selected file. The shell prompt stays active.
            if parsed is None:
                parsed, tables, matches = load_metadata(path)
            raw = input(color("sql-analyzer> ", "32;1")).strip()
            if not raw:
                continue
            command = raw.casefold().split()[0]

            if command in {"exit", "quit", "q", "0"}:
                print("Goodbye.")
                break
            elif command in {"help", "?"}:
                show_help()
            elif command in {"tables", "table", "1"}:
                show_tables(tables)
            elif command in {"users", "sensitive", "2"}:
                show_user_tables(matches)
            elif command in {"overview", "all", "5"}:
                show_overview(tables, matches)
            elif command in {"export", "3"}:
                choose_export(parsed, tables, path)
            elif command in {"open", "file", "4"}:
                new_path = prompt_sql_file()
                if new_path != path:
                    path = new_path
                    parsed = None
                    tables = []
                    matches = {}
                else:
                    # Reuse the existing cache if the same file was selected.
                    print(color("Same file selected; reusing cached analysis.", "32"))
            elif command == "status":
                size_gb = path.stat().st_size / (1024 ** 3)
                print(f"File: {path}\nSize: {size_gb:.2f} GiB\nCached tables: {len(tables)}\nUser-related tables: {len(matches)}")
            else:
                print(color(f"Unknown command: {raw}. Type 'help' for commands.", "33"))
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted. Type 'exit' to quit or continue with another command.")
        except (OSError, ValueError, SQLParseError) as exc:
            logging.warning("Operation failed for %s: %s", path, exc)
            print(color(f"Operation failed: {exc}", "31"))
        except Exception as exc:
            logging.exception("Unexpected error")
            print(color(f"Unexpected error: {exc}. Details logged to sql_analyzer.log.", "31"))


if __name__ == "__main__":
    main()
