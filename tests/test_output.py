import unittest

from src.utils.output import strip_ansi_escape_codes, truncate_output


class TruncateOutputTests(unittest.TestCase):
    def test_short_output_unchanged(self) -> None:
        output = "hello world"
        self.assertEqual(truncate_output(output, 100), output)

    def test_exact_limit_unchanged(self) -> None:
        output = "x" * 100
        self.assertEqual(truncate_output(output, 100), output)

    def test_long_output_truncated(self) -> None:
        output = "A" * 50 + "B" * 50
        result = truncate_output(output, 80)
        self.assertIn("[SYSTEM WARNING", result)
        self.assertIn("A", result)
        self.assertIn("B", result)
        self.assertLess(len(result), len(output) + 200)

    def test_head_and_tail_preserved(self) -> None:
        output = "HEAD" + "x" * 1000 + "TAIL"
        result = truncate_output(output, 100)
        self.assertIn("HEAD", result)
        self.assertIn("TAIL", result)

    def test_separator_present(self) -> None:
        output = "x" * 200
        result = truncate_output(output, 100)
        self.assertIn("...", result)

    def test_empty_output(self) -> None:
        self.assertEqual(truncate_output("", 100), "")


class StripAnsiTests(unittest.TestCase):
    def test_strips_color_codes(self) -> None:
        colored = "\x1b[31mRed text\x1b[0m"
        self.assertEqual(strip_ansi_escape_codes(colored), "Red text")

    def test_strips_cursor_movement(self) -> None:
        with_cursor = "\x1b[2Jcleared"
        self.assertEqual(strip_ansi_escape_codes(with_cursor), "cleared")

    def test_plain_text_unchanged(self) -> None:
        plain = "just normal text\nwith newlines"
        self.assertEqual(strip_ansi_escape_codes(plain), plain)

    def test_preserves_tabs_and_newlines(self) -> None:
        text = "col1\tcol2\nrow2"
        self.assertEqual(strip_ansi_escape_codes(text), text)


if __name__ == "__main__":
    unittest.main()
