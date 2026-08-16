# Project Guide

## 1. Purpose and scope

The project reconciles data from several differently formatted employee and
payroll sources against a transformed destination file. It independently
recreates the values that should have reached the destination and reports
matches, expected transformations, missing data, mismatches and orphan
records.

The destination is an input to validation. This project does not generate or
load it.

## 2. Processing sequence

| Step | Component | What happens |
|---:|---|---|
| 1 | `main.py` | Loads `config.json` and initialises the run. |
| 2 | `readers.py` | Reads each source and maps source-specific headers to canonical fields. |
| 3 | `derive.py` | Applies currency conversion, field splitting, name fillers, salary proration and LOP deduction. |
| 4 | `readers.py` | Reads the final transformed destination. |
| 5 | `reconcile.py` | Matches employee keys and compares each configured field. |
| 6 | `reconcile.py` | Calculates performance bonus and total compensation when configured. |
| 7 | `report_xlsx.py` or `report.py` | Produces the Excel or PDF report. |

## 3. Python file details

### `main.py`

- Accepts optional configuration and output paths.
- Clears prior read warnings.
- Reads all configured sources.
- Converts source currencies before salary calculations.
- Applies configured derived fields and the name filler.
- Collects month-level salary analysis rows.
- Reads and standardises the destination.
- Runs reconciliation and prints a summary.
- Selects the report writer from the output extension.

Change this file when the overall orchestration or command-line interface
changes.

### `readers.py`

- Reads CSV, pipe-delimited/key-value text, XML, Excel and Access files.
- Can read a live destination database through SQLAlchemy.
- Applies source-specific `field_map` mappings.
- Aggregates repeated component rows, such as quarterly bonus entries.
- Deduplicates repeated records by latest effective date.
- Records malformed-row warnings instead of silently losing data.

Change this file when introducing a new source format or record-collapsing
rule.

### `transforms.py`

- Provides case, whitespace, digit, phone, address, identifier and numeric
  normalisation.
- Helps separate legitimate format changes from genuine data discrepancies.

Change this file when a comparison needs a new approved normalisation rule.

### `derive.py`

- Splits combined names into first, middle and last components.
- Splits comma-separated addresses and phone components.
- Adds `XX` to configured missing optional name components.
- Converts currency amounts using configured rates.
- Sums monthly columns.
- Prorates salary for partial join/leave months.
- Calculates monthly gross eligible salary, LOP deduction and net salary.
- Supplies month-level salary analysis rows to the report.

Change this file when a new transformation or salary rule is required.

### `reconcile.py`

- Normalises and indexes matching keys for every source.
- Collects every available source value for each destination field.
- Assigns field-level reconciliation statuses.
- Resolves values across sources for computed fields.
- Calculates tier-based performance bonuses and sum-based totals.
- Summarises status counts.

Change this file when matching rules, status definitions or cross-source
calculations change.

### `report_xlsx.py`

- Builds a filterable Excel workbook.
- Provides Summary, By Field, Salary Analysis, Issues, Accepted Transforms and
  Full Detail sheets.
- Keeps approved normalized matches out of the Issues sheet.
- Applies status colours and configured field ordering.

Change this file when the Excel report structure or presentation changes.

### `report.py`

- Builds a landscape PDF report with summary, salary analysis, issues and full
  audit detail.

Change this file when the PDF layout changes.

## 4. Sample-data guide

### `source_hr.csv`

Expected mapped inputs: `EmpID`, `FullName`, `HomeAddress`, `PhoneNumber`.
Demonstrates CSV reading and splitting of combined values.

### `source_legacy.xml`

Expected employee elements include ID, first name, last name, address and
telephone. Demonstrates XML parsing and an already-split name source.

### `source_notepad.txt`

Expected pipe-delimited fields: `EMP_ID`, `EMP_NAME`, `PHONE`,
`EFFECTIVE_DATE`. Demonstrates latest-record deduplication.

### `source_salary.xlsx`

Expected columns:

- `EmployeeID`, `Currency`, `JoinDate`, `LeaveDate`
- `Jan` through `Dec`
- `JanLOPDays` through `DecLOPDays`

Demonstrates currency conversion, join/leave proration and monthly LOP
deductions. Missing LOP values are treated as zero.

### `source_bonus.txt`

Expected fields: `EMP_ID`, `QUARTER`, `BONUS_AMOUNT`. Demonstrates aggregation
of several quarterly rows into annual `TotalBonus`.

### `source_performance.csv`

Expected fields: `EMP_ID`, `RATING`. Supplies the A/B/C rating used by the
performance-bonus calculation.

### `destination.csv`

Represents data after the external transformation process. The tool validates
this file; it does not create it. The supplied version is the clean final
transformed sample and exposes `GrossSalary`, `TotalLossOfPayDays`,
`LossOfPayDeduction`, net `TotalSalary`, `TotalBonus`, `PerformanceBonus` and
`TotalCompensation`.

### `destination_test_cases.csv`

Contains deliberate errors and an explanatory `TestCaseNote`. Use it only with
`config_test_cases.json`; it is not the clean transformed output.

## 5. LOP example

For a monthly salary of 20,000 in April with two LOP days:

```text
Daily rate    = 20,000 / 30
LOP deduction = 20,000 / 30 x 2 = 1,333.33
Net April pay = 20,000 - 1,333.33 = 18,666.67
```

The annual `TotalSalary` used for reconciliation is the sum of monthly net
salary, not the unreduced annual entitlement.

## 6. Report interpretation

`Summary` provides overall counts. `By Field` shows where issues concentrate.
`Salary Analysis` explains month-level LOP calculations. `Issues` contains
only genuine exceptions. `Accepted Transforms` contains successful comparisons
after approved normalization, including formatting changes; those rows are not
errors. `Full Detail` is the field-by-field audit trail.

The supplied clean run performs 102 field checks: 72 exact matches and 30
matches after approved normalization, with no mismatches, missing values or
missing keys.

## 7. Test design

A useful sample pack should contain:

- at least one clean match;
- a format-only match;
- an incorrect transformed value;
- a missing destination value;
- a field unavailable in any source;
- an orphan destination key;
- a joiner or leaver;
- LOP in February, a 30-day month and a 31-day month;
- a correct net salary and an intentionally unreduced salary;
- a clearly documented compensation calculation.

## 8. Collaboration and change control

Use a private repository with one collaborator granted Write access. Ask the
collaborator to work on a branch and submit a pull request. Keep the main branch
as the reviewed reference version.

Never commit real employee or payroll data. Use fictional test data and keep
real extracts outside Git.
