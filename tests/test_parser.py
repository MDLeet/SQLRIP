import unittest
import tempfile
from pathlib import Path
from sql_parser import parse_sql_text, parse_sql_file, iter_file_statements, SQLParseError

class ParserTests(unittest.TestCase):
    def test_multiple_tables_and_inserts(self):
        p = parse_sql_text("""
        CREATE TABLE users (id INTEGER, email TEXT, PRIMARY KEY (id));
        INSERT INTO users VALUES (1, 'a;b@example.com'), (2, 'x');
        CREATE TABLE `audit` (`user_id` INT, note TEXT);
        """)
        self.assertEqual(list(p.tables), ["users", "audit"])
        self.assertEqual(p.tables["users"].columns, ["id", "email"])
        self.assertEqual(len(p.tables["users"].insert_statements), 1)

    def test_semicolon_inside_string(self):
        p = parse_sql_text("INSERT INTO t VALUES ('hello; world');")
        self.assertEqual(len(p.tables["t"].insert_statements), 1)

    def test_comments_and_quotes(self):
        p = parse_sql_text("-- hi\nCREATE TABLE t (\"Email\" TEXT, note TEXT);")
        self.assertEqual(p.tables["t"].columns[0], "Email")

    def test_empty_and_no_tables(self):
        self.assertEqual(parse_sql_text("").tables, {})
        self.assertEqual(parse_sql_text("SELECT 1;").tables, {})


    def test_streaming_file_keeps_metadata_without_insert_bodies(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "large-ish.sql"
            path.write_text("CREATE TABLE users (id INT, email TEXT);\nINSERT INTO users VALUES (1, 'a;b'), (2, 'c');\n", encoding="utf-8")
            parsed = parse_sql_file(path, chunk_size=7)
            self.assertIn("users", parsed.tables)
            self.assertEqual(parsed.tables["users"].columns, ["id", "email"])
            self.assertEqual(parsed.tables["users"].insert_statements, [])
            statements = list(iter_file_statements(path, chunk_size=7))
            self.assertEqual(len(statements), 2)
            self.assertIn("'a;b'", statements[1])

    def test_streaming_dollar_quote_and_comment_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "quoted.sql"
            path.write_text("CREATE TABLE t (v TEXT); INSERT INTO t VALUES ($tag$a;b$tag$); /*x;y*/", encoding="utf-8")
            statements = list(iter_file_statements(path, chunk_size=5))
            self.assertEqual(len(statements), 2)
            self.assertIn("$tag$a;b$tag$", statements[1])


    def test_parse_progress_callback_reaches_file_size(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "progress.sql"
            path.write_text("CREATE TABLE t (id INT);\n" + "INSERT INTO t VALUES (1);\n" * 30, encoding="utf-8")
            progress = []
            parse_sql_file(path, chunk_size=11, progress_callback=lambda done, total: progress.append((done, total)))
            self.assertTrue(progress)
            self.assertEqual(progress[-1][0], path.stat().st_size)
            self.assertEqual(progress[-1][1], path.stat().st_size)

    def test_unterminated_string(self):
        with self.assertRaises(SQLParseError):
            parse_sql_text("INSERT INTO t VALUES ('broken);")

if __name__ == "__main__":
    unittest.main()
