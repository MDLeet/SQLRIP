import unittest
from sql_parser import parse_sql_text
from column_analyzer import find_user_related_tables

class ColumnAnalyzerTests(unittest.TestCase):
    def test_case_and_normalization(self):
        p = parse_sql_text("CREATE TABLE users (EMAIL TEXT, user_id INT, password_hash TEXT);")
        result = find_user_related_tables(p)
        self.assertEqual(result, {"users": ["EMAIL", "user_id"]})

    def test_partial_opt_in(self):
        p = parse_sql_text("CREATE TABLE users (password_hash TEXT);")
        self.assertEqual(find_user_related_tables(p), {})
        self.assertEqual(find_user_related_tables(p, partial=True), {"users": ["password_hash"]})

if __name__ == "__main__":
    unittest.main()
