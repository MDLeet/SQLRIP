import tempfile, unittest
from pathlib import Path
from sql_parser import parse_sql_text
from table_exporter import export_table
from sql_parser import parse_sql_file

class ExportTests(unittest.TestCase):
    def test_export(self):
        p = parse_sql_text("CREATE TABLE t (id INT); INSERT INTO t VALUES (1), (2);")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.txt"
            export_table(p, "t", out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("CREATE TABLE t", text)
            self.assertIn("INSERT INTO t VALUES", text)


    def test_streaming_export_from_source_file(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "dump.sql"
            source.write_text("CREATE TABLE t (id INT); INSERT INTO t VALUES (1); INSERT INTO other VALUES (2); INSERT INTO t VALUES (3);", encoding="utf-8")
            parsed = parse_sql_file(source, chunk_size=8)
            out = Path(d) / "t.txt"
            count = export_table(parsed, "t", out, source_path=source, chunk_size=8)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(count, 2)
            self.assertIn("CREATE TABLE t", text)
            self.assertIn("VALUES (1)", text)
            self.assertIn("VALUES (3)", text)
            self.assertNotIn("other", text)


    def test_streaming_export_reports_byte_progress(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "dump.sql"
            source.write_text("CREATE TABLE t (id INT);\n" + "INSERT INTO t VALUES (1);\n" * 30, encoding="utf-8")
            parsed = parse_sql_file(source, chunk_size=12)
            out = Path(d) / "t.txt"
            progress = []
            export_table(parsed, "t", out, source_path=source, chunk_size=12,
                         file_progress_callback=lambda done, total: progress.append((done, total)))
            self.assertTrue(progress)
            self.assertEqual(progress[-1][0], source.stat().st_size)
            self.assertEqual(progress[-1][1], source.stat().st_size)

    def test_export_cannot_overwrite_source(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "dump.sql"
            source.write_text("CREATE TABLE t (id INT);", encoding="utf-8")
            parsed = parse_sql_file(source)
            with self.assertRaises(ValueError):
                export_table(parsed, "t", source, source_path=source)

    def test_missing_table(self):
        p = parse_sql_text("CREATE TABLE t (id INT);")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                export_table(p, "missing", Path(d) / "out.txt")

if __name__ == "__main__":
    unittest.main()
