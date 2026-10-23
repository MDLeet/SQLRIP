# [SQLRIP] SQL Analyzer — Streaming CLI

Offline Python command-line tool for analyzing SQL dump files and exporting recognized SQL statements. It **never executes SQL** and never connects to a database.

## Requirements
- Python 3.10 or newer
- Windows or Linux
- No third-party packages

## Run

Windows PowerShell:
```powershell
py -3 main.py
```

Linux:
```bash
python3 main.py
```

Choose a `.sql` file once. The tool then behaves like a shell: enter `tables`, `users`, `overview`, `export`, `open`, `status`, `help`, or `exit` at the `sql-analyzer>` prompt. The commands can be repeated without showing a numbered menu each time.

## Session cache and large files

For the selected file, the tool performs one initial streaming analysis pass and caches the recognized table names, CREATE statements, and column names in memory. It does **not** retain INSERT bodies. Repeating `tables`, `users`, or `overview` reuses the cache and does not parse the file again. Choosing a different file with `open` creates a new cache.

Export necessarily performs another sequential streaming pass over the source file to find INSERT statements for the selected table. This is intentional: retaining every INSERT from a 100 GB dump in memory would defeat the large-file design. Export writes to a temporary TXT file and replaces the destination only after a successful pass.

The file is read incrementally in 4 MiB chunks by default. During the initial analysis and export scan, the CLI displays a progress bar and percentage based on the source file byte position (updates are throttled to avoid flooding the terminal). This is suitable for very large files, including files around 100 GB, provided there is enough disk space and the machine can finish the sequential scans. It is not a guarantee of a particular runtime or support for every SQL dialect. Memory usage depends on parser state plus the largest individual SQL statement; one multi-gigabyte INSERT statement can still require substantial memory.

## Commands

| Command | Description |
|---|---|
| `tables` or `1` | List all recognized tables |
| `users` or `2` | List tables with user-related column names |
| `export` or `3` | Export one table's CREATE + matching INSERT statements to TXT |
| `open` or `4` | Select another SQL file |
| `overview` or `5` | Show all tables together; tables with user-related column names are highlighted in red |
| `status` | Show selected file, size, and cached counts |
| `help` or `?` | Show command help |
| `exit`, `quit`, or `0` | Exit |

Colors are enabled in interactive terminals and disabled when output is redirected.

## User-related column detection

The default exact, case-insensitive keyword list includes `email`, `password`, `user`, `username`, `user_id`, `first_name`, `last_name`, `full_name`, `phone`, `address`, `dob`, and `date_of_birth`. Only column names are inspected; row values are not printed or analyzed for this feature.

## SQL syntax limitations

This is a conservative scanner, not a complete SQL dialect parser. It recognizes common `CREATE TABLE` definitions and `INSERT INTO ... VALUES` statements. PostgreSQL `COPY ... FROM STDIN`, MySQL `LOAD DATA`, stored procedures/triggers, custom delimiter scripts, and dialect-specific forms may not be exportable. Schema-qualified and quoted identifiers are handled conservatively; test against a representative dump before relying on results. No SQL is run.

## Encoding and privacy

UTF-8 (including BOM) is preferred; if the initial sample is not valid UTF-8, Windows-1252 is used. Files are read locally and no content is sent over the network. Logs may contain file paths; review `sql_analyzer.log` before sharing it.

## Tests

```bash
python -m unittest discover -s tests -v
```
