import os
import tempfile
import unittest

from src.experiment_utils.validate_flag import flag_match, get_expected_flag


class FlagMatchTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(flag_match("FLAG{abc123}", ["FLAG{abc123}"]))

    def test_flag_contained_in_agent_output(self) -> None:
        self.assertTrue(flag_match("FLAG{tGEsSPrGsbWunrAD}", ["tGEsSPrGsbWunrAD"]))

    def test_case_insensitive(self) -> None:
        self.assertTrue(flag_match("flag{ABC}", ["FLAG{abc}"]))

    def test_whitespace_insensitive(self) -> None:
        self.assertTrue(flag_match("FLAG{ abc 123 }", ["FLAG{abc123}"]))

    def test_no_match(self) -> None:
        self.assertFalse(flag_match("FLAG{wrong}", ["FLAG{correct}"]))

    def test_empty_found_flag(self) -> None:
        self.assertFalse(flag_match("", ["FLAG{abc}"]))

    def test_single_string_ground_truth(self) -> None:
        self.assertTrue(flag_match("FLAG{abc}", "FLAG{abc}"))

    def test_multiple_ground_truths_any_match(self) -> None:
        self.assertTrue(flag_match("FLAG{second}", ["FLAG{first}", "FLAG{second}"]))

    def test_multiple_ground_truths_none_match(self) -> None:
        self.assertFalse(flag_match("FLAG{third}", ["FLAG{first}", "FLAG{second}"]))

    def test_ground_truth_substring_of_found(self) -> None:
        """Agent wraps the flag — ground truth is a substring of found."""
        self.assertTrue(flag_match("Found the flag: abc123def in /root/flag.txt", ["abc123def"]))


class GetExpectedFlagTests(unittest.TestCase):
    def test_single_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            challenge_dir = os.path.join(tmp, "vm0")
            os.makedirs(challenge_dir)
            with open(os.path.join(challenge_dir, "flag.txt"), "w") as f:
                f.write("FLAG{test123}\n")

            result = get_expected_flag("vm0", tmp)
            self.assertEqual(result, ["FLAG{test123}"])

    def test_multiple_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            challenge_dir = os.path.join(tmp, "vm0")
            os.makedirs(challenge_dir)
            with open(os.path.join(challenge_dir, "flag.txt"), "w") as f:
                f.write("FLAG{first}\nFLAG{second}\n")

            result = get_expected_flag("vm0", tmp)
            self.assertEqual(result, ["FLAG{first}", "FLAG{second}"])

    def test_empty_lines_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            challenge_dir = os.path.join(tmp, "vm0")
            os.makedirs(challenge_dir)
            with open(os.path.join(challenge_dir, "flag.txt"), "w") as f:
                f.write("\n\nFLAG{only}\n\n")

            result = get_expected_flag("vm0", tmp)
            self.assertEqual(result, ["FLAG{only}"])

    def test_empty_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            challenge_dir = os.path.join(tmp, "vm0")
            os.makedirs(challenge_dir)
            with open(os.path.join(challenge_dir, "flag.txt"), "w") as f:
                f.write("\n\n")

            result = get_expected_flag("vm0", tmp)
            self.assertIsNone(result)

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = get_expected_flag("vm0", tmp)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
