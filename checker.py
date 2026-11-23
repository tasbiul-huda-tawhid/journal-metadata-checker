"""Compare a journal issue CSV against a local registry snapshot."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import re
import sys
import unicodedata


FIELDS = ("doi", "title", "authors")
REPORT_FIELDS = ("issue_row", "doi", "field", "status", "issue_value", "snapshot_value", "note")


def normalize_doi(value):
    value = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", value.strip(),
                   flags=re.IGNORECASE)
    return value.casefold()


def normalize_text(value):
    """Ignore case and cosmetic whitespace/punctuation, but keep accents."""
    value = unicodedata.normalize("NFC", value).casefold()
    return " ".join("".join(" " if unicodedata.category(c).startswith("P") else c
                            for c in value).split())


def normalize_authors(value):
    if not value.strip():
        return []
    return [normalize_text(name) for name in value.split(";")]


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not set(FIELDS).issubset(headers):
            raise ValueError(f"{path}: expected distinct columns doi, title and authors")
        rows = []
        for number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}: record {number} has the wrong number of columns")
            rows.append({field: row[field].strip() for field in FIELDS})
            rows[-1]["number"] = number
    return rows


def index_snapshot(rows):
    index = {}
    for row in rows:
        doi = normalize_doi(row["doi"])
        if not valid_doi(doi):
            raise ValueError(f"snapshot record {row['number']} has a missing or invalid DOI")
        if doi in index:
            raise ValueError(f"snapshot record {row['number']} repeats DOI {doi}")
        index[doi] = row
    if not index:
        raise ValueError("snapshot contains a header but no records")
    return index


def valid_doi(doi):
    # Basic structural check only; this does not establish that a DOI is registered.
    return re.fullmatch(r"10\.\d{4,9}/[^\s]+", doi, flags=re.ASCII) is not None


def find_issues(issue, snapshot, ignore_author_order=False):
    index = index_snapshot(snapshot)
    if not issue:
        raise ValueError("issue contains a header but no records")
    doi_counts = Counter(normalize_doi(row["doi"]) for row in issue)
    for row in issue:
        doi = normalize_doi(row["doi"])
        number = row["number"]
        if not valid_doi(doi):
            yield number, doi, "doi", "not_comparable", row["doi"], "", "Missing or invalid DOI"
            continue
        if doi_counts[doi] > 1:
            yield number, doi, "doi", "not_comparable", row["doi"], "", "DOI repeated in issue"
            continue
        if doi not in index:
            yield number, doi, "doi", "not_comparable", row["doi"], "", "No record in this snapshot"
            continue
        reference = index[doi]
        for field, normalize in (("title", normalize_text), ("authors", normalize_authors)):
            left, right = normalize(row[field]), normalize(reference[field])
            if not left or not right or (field == "authors" and ("" in left or "" in right)):
                sides = []
                for side, value in (("issue", left), ("snapshot", right)):
                    if not value or (field == "authors" and "" in value):
                        sides.append(side)
                status, note = "not_comparable", "Missing or incomplete in " + " and ".join(sides)
            elif left == right:
                status, note = "match", ""
            elif field == "authors" and Counter(left) == Counter(right):
                if ignore_author_order:
                    status, note = "match", "Same author names; order comparison disabled"
                else:
                    status, note = "review", "Same author names in a different order"
            else:
                status, note = "review", "Compared values differ"
            yield number, doi, field, status, row[field], reference[field], note


def spreadsheet_text(value):
    # Quoting CSV does not stop spreadsheets from evaluating a formula.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_report(path, results):
    # Exclusive creation guards against replacing either an input or an existing report.
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(REPORT_FIELDS)
        for result in results:
            writer.writerow(spreadsheet_text(value) for value in result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", type=Path, help="journal issue CSV")
    parser.add_argument("snapshot", type=Path, help="local registry snapshot CSV")
    parser.add_argument("report", type=Path, help="new output CSV; must not exist")
    parser.add_argument("--ignore-author-order", action="store_true",
                        help="treat reordered author lists as matches")
    args = parser.parse_args(argv)
    try:
        results = list(find_issues(load_csv(args.issue), load_csv(args.snapshot),
                                   args.ignore_author_order))
        write_report(args.report, results)
    except (OSError, ValueError, csv.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    counts = Counter(result[3] for result in results)
    print(f"Checks: {counts['match']} matched, {counts['review']} need review, "
          f"{counts['not_comparable']} not comparable.")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
