import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from checker import find_issues, load_csv, write_report


PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT / "fixtures"


def record(doi="10.0000/one", title="Title", authors="A. Vale;B. Tan", number=2):
    return {"doi": doi, "title": title, "authors": authors, "number": number}


def outcomes(issue, snapshot, ignore_author_order=False):
    return {row[2]: row[3] for row in find_issues([issue], [snapshot], ignore_author_order)}


class ComparisonTests(unittest.TestCase):
    def test_cosmetic_differences_and_composed_accents_match(self):
        self.assertEqual(outcomes(record("HTTPS://DOI.ORG/10.0000/ONE", "A: Title",
                                         "R. Garci\u0301a; B. Tan"),
                                  record(title="a title", authors="R García;B Tan")),
                         {"title": "match", "authors": "match"})

    def test_accent_difference_is_not_automatically_merged(self):
        self.assertEqual(outcomes(record(authors="R García"), record(authors="R Garcia"))["authors"],
                         "review")

    def test_byline_order_is_a_separate_review_decision(self):
        left, right = record(authors="A;B"), record(authors="B;A")
        self.assertEqual(outcomes(left, right)["authors"], "review")
        self.assertEqual(outcomes(left, right, True)["authors"], "match")
        self.assertEqual(outcomes(left, record(authors="B;C"), True)["authors"], "review")
        self.assertEqual(outcomes(record(authors="A;A;B"), right, True)["authors"], "review")

    def test_missing_fields_and_trailing_author_separator_not_comparable(self):
        self.assertEqual(outcomes(record(title="", authors="A;"), record(authors="A")),
                         {"title": "not_comparable", "authors": "not_comparable"})

    def test_doi_not_in_snapshot_or_invalid_doi_not_comparable(self):
        for doi in ("10.0000/not-there", "a typo", ""):
            with self.subTest(doi=doi):
                self.assertEqual(outcomes(record(doi), record()), {"doi": "not_comparable"})

    def test_duplicate_issue_dois_ambiguity_is_reported_for_both(self):
        results = list(find_issues([record(), record("doi:10.0000/ONE", number=3)], [record()]))
        self.assertEqual([(row[0], row[3]) for row in results],
                         [(2, "not_comparable"), (3, "not_comparable")])

    def test_duplicate_or_bad_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "repeats DOI"):
            list(find_issues([record()], [record(), record("doi:10.0000/ONE", number=3)]))
        with self.assertRaisesRegex(ValueError, "missing or invalid DOI"):
            list(find_issues([record()], [record("")]))

    def test_empty_input_is_rejected(self):
        for issue, snapshot in (([], [record()]), ([record()], [])):
            with self.subTest(issue=bool(issue)):
                with self.assertRaisesRegex(ValueError, "no records"):
                    list(find_issues(issue, snapshot))


class FileTests(unittest.TestCase):
    def test_reader_rejects_malformed_header_or_column_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            for text in ("doi,title,title,authors\na,b,c,d\n", "doi,title,authors\na,b,c,d\n"):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_csv(path)

    def test_export_handles_formula_like_cells_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.csv"
            write_report(path, [(2, "10.0000/one", "title", "review", "=1+1", "Safe, title", "")])
            with path.open(encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["issue_value"], "'=1+1")
            self.assertEqual(row["snapshot_value"], "Safe, title")
            with self.assertRaises(FileExistsError):
                write_report(path, [])

    def test_cli_runs_sample_and_preserves_input_files(self):
        issue, snapshot = FIXTURES / "issue.csv", FIXTURES / "snapshot.csv"
        before = (issue.read_bytes(), snapshot.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "demo.csv"
            result = subprocess.run([sys.executable, str(PROJECT / "checker.py"),
                                     str(issue), str(snapshot), str(report)],
                                    capture_output=True, text=True, check=True)
            self.assertIn("5 matched, 2 need review, 3 not comparable", result.stdout)
            with report.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 10)
            self.assertEqual([r["note"] for r in rows if r["status"] == "review"],
                             ["Same author names in a different order", "Compared values differ"])
        self.assertEqual(before, (issue.read_bytes(), snapshot.read_bytes()))
