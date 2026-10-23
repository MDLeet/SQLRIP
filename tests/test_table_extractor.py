import unittest
from sql_parser import parse_sql_text
from table_extractor import list_tables

class TableExtractorTests(unittest.TestCase):
    def test_unique_names(self):
        p = parse_sql_text("CREATE TABLE t (id INT); INSERT INTO t VALUES (1);")
        self.assertEqual(list_tables(p), ["t"])

if __name__ == "__main__":
    unittest.main()
