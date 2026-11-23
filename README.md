# Journal Metadata Checker

Before publishing an issue, an editor might need to compare an article list with a registry export. This tool turns two CSVs into a short review queue. It does not decide which source is correct or change either file.

A personal prototype inspired by Tawhid's editorial work at MAHSA University. It was not developed for or deployed at MAHSA. The initial implementation and tests were AI-assisted. The fixtures are fictional; their names, articles and mock DOI values are for demonstration only.

## Try it

Use Python 3.9 or newer. No packages, accounts or network access are needed.

```sh
mkdir -p reports
python3 checker.py fixtures/issue.csv fixtures/snapshot.csv reports/demo.csv
python3 -m unittest discover -s tests -v
```

On Windows, use `py -3` instead of `python3`, and create the `reports` folder first. The demo prints **5 matched, 2 need review, 3 not comparable**. Open the report and filter its `status` column. Pick a fresh output filename for repeat runs; an existing file won't be overwritten.

## How it decides what to flag

Both CSVs need a header with `doi,title,authors`. Separate authors with semicolons in byline order. The checker pairs records by normalized DOI (ignoring case and common prefixes), then compares title and author lists, ignoring case, whitespace and punctuation for those text fields but retaining accents.

- **Match:** the values agree under those rules.
- **Review:** values differ, including the same names in a different byline order.
- **Not comparable:** a field is missing or incomplete, the DOI is invalid or repeated in the issue, or the DOI isn't in this snapshot. A snapshot with duplicate or invalid DOIs is rejected.

A row absent from a snapshot is not proof that the DOI doesn't exist. This prototype does not verify DOI registrations, infer name aliases or compare dates or other publication fields. It uses simple text rules, so a human still needs to review consequential differences.

**Review decision:** Keep reordered authors flagged as the default, or use the tool only to check who is on the list? To compare the two behaviours, rerun the demo with `--ignore-author-order` and a different output filename. In the second report, the same two names in reverse order match, but a different author would still be flagged.
