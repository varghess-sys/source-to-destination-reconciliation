# Source-to-Destination Reconciliation Tool

## Objective

This project validates that a transformed destination dataset can be traced
back to its source extracts and that every configured transformation has been
applied correctly before the destination is loaded into another system.

It is designed to answer five questions:

1. Does every destination employee exist in at least one source?
2. Does each destination field match an appropriate source value?
3. Are expected transformations, such as name splitting and phone
   normalisation, correct?
4. Are calculated payroll values, including loss-of-pay deductions, bonus and
   total compensation, correct?
5. Which records require investigation before loading?

The tool is a **reconciliation and validation tool**. It does not create the
destination file, update a production database, or act as an attendance or
payroll system.

## End-to-end flow

1. Read heterogeneous sources: CSV, XML, flat text and Excel.
2. Map each source's field names to canonical names defined in `config.json`.
3. Apply transformations and derivations.
4. Read the already-transformed `destination.csv`.
5. Match records by normalised `EmployeeID`.
6. Compare every configured field and calculate cross-source values.
7. Produce an Excel or PDF reconciliation report.

```text
Source extracts -> Mapping and derivation -> Expected canonical values
                                                     |
Destination file ------------------------------------+
                                                     |
                                             Reconciliation report
```

## Important distinction

- `destination.csv` is the final transformed dataset supplied to the tool for
  validation. In this sample pack it is the clean, internally auditable version.
- `destination_test_cases.csv` is a separate deliberately defective dataset
  used only with `config_test_cases.json`.
- `config.json` defines mappings, transformations and calculation rules.
- `reconciliation_report.xlsx` or `.pdf` is the matching report produced by
  the tool.

## Python files

| File | Responsibility |
|---|---|
| `main.py` | Command-line entry point. Loads configuration, reads sources and destination, applies conversions/derivations, runs reconciliation and chooses Excel or PDF output. |
| `readers.py` | Reads CSV, XML, flat-text, Excel, Access and database sources. Applies field mappings, aggregation, deduplication and malformed-row warnings. |
| `transforms.py` | Contains reusable comparison normalisations for IDs, names, phone numbers, addresses and numeric/currency values. |
| `derive.py` | Splits combined name/address/phone fields, inserts configured name fillers, converts currencies, prorates salary and calculates loss-of-pay deductions. |
| `reconcile.py` | Builds source indexes, matches destination records, assigns reconciliation statuses and calculates cross-source fields such as performance bonus and total compensation. |
| `report_xlsx.py` | Produces the filterable Excel report: Summary, By Field, Salary Analysis, Issues, Accepted Transforms and Full Detail. |
| `report.py` | Produces the PDF version of the reconciliation report. |

See `docs/PROJECT_GUIDE.md` and `Project_Guide.xlsx` for detailed explanations.

## Configuration

`config.json` is the control centre. It defines:

- the matching key and key normalisation;
- the three-part name rule and `XX` filler;
- base currency and FX rates;
- fields to validate and their comparison transforms;
- source file paths and source-specific field mappings;
- split, aggregation, deduplication and salary derivation rules;
- performance bonus and total compensation calculations;
- destination file type, path and field mapping.

## Key business rules

### Names

Names are represented as `FirstName`, `MiddleName` and `LastName`. Missing
optional middle or last names receive the configured filler `XX`. A source
that contains no name fields is not given fabricated name data.

### Employee IDs

Employee IDs are normalised for matching so formatting differences such as
`E007`, `e-007` and leading zeros do not create false missing-key errors.

### Salary and loss of pay

Each monthly salary column contains the full-month salary rate. Each month has
a corresponding LOP-days column, for example `JanLOPDays`.

```text
Eligible gross salary = Full-month salary x Eligible days / Calendar days
LOP deduction         = Full-month salary x LOP days / Calendar days
Net monthly salary    = Eligible gross salary - LOP deduction
TotalSalary           = Sum of net monthly salaries
```

The calculation uses the actual days in each month, including leap-year
February. Join and leave dates restrict eligible days. LOP days cannot exceed
eligible days.

### Bonus and total compensation

Quarterly bonus rows are aggregated into `TotalBonus`. The current
configuration also calculates a `PerformanceBonus` from salary and rating:

- A: 15%
- B: 10%
- C: 5%

The current calculation is:

```text
TotalCompensation = TotalSalary + TotalBonus + PerformanceBonus
```

The clean sample exposes every component used in the calculation:
`GrossSalary`, `TotalLossOfPayDays`, `LossOfPayDeduction`, net `TotalSalary`,
`TotalBonus`, `PerformanceBonus` and `TotalCompensation`.

## Sample files

| File | Format | Purpose |
|---|---|---|
| `sample_data/source_hr.csv` | CSV | Core employee identity, combined name, address and phone source. |
| `sample_data/source_legacy.xml` | XML | Legacy employee source with split name and contact fields. |
| `sample_data/source_notepad.txt` | Pipe-delimited text | Time-stamped employee records; latest record per employee is retained. |
| `sample_data/source_salary.xlsx` | Excel | Monthly salary, currency, join/leave dates and monthly LOP days. |
| `sample_data/source_bonus.txt` | Pipe-delimited text | Quarterly bonus rows aggregated to annual `TotalBonus`. |
| `sample_data/source_performance.csv` | CSV | Performance rating used to calculate `PerformanceBonus`. |
| `sample_data/destination.csv` | CSV | Clean final transformed target data; all true checks pass. |
| `sample_data/destination_test_cases.csv` | CSV | Deliberately defective target with documented negative-test scenarios. |
| `examples/lop_sample_data.xlsx` | Excel | Original LOP reference values; these values are already merged into `source_salary.xlsx`. |

Detailed schemas and test purposes are documented in
`docs/PROJECT_GUIDE.md`.

## Reconciliation statuses

| Status | Meaning |
|---|---|
| `MATCH` | Destination and source values are identical. |
| `MATCH_AFTER_TRANSFORM` | They match after an approved normalisation. |
| `MISMATCH` | The source carries the field, but the destination value is different. |
| `MISSING_IN_DESTINATION` | A source value exists but the destination is empty. |
| `FIELD_NOT_IN_SOURCE` | No matching source carries that field. |
| `KEY_NOT_FOUND_IN_SOURCE` | The destination employee does not exist in any source. |

## Report outputs

### Excel

```powershell
py main.py config.json reconciliation_report.xlsx
```

The workbook contains:

- `Summary`
- `By Field`
- `Salary Analysis`
- `Issues`
- `Accepted Transforms`
- `Full Detail`

`Issues` contains only genuine exceptions. Approved normalized comparisons,
including numeric formatting and configured fillers, appear under `Accepted
Transforms` and are not errors.

### PDF

```powershell
py main.py config.json reconciliation_report.pdf
```

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

The sample files are already included under `sample_data/`.

Run the clean validation:

```powershell
py main.py config.json reconciliation_report_clean.xlsx
```

Run the deliberately defective negative-test dataset:

```powershell
py main.py config_test_cases.json reconciliation_report_test_cases.xlsx
```

## Data-editing guidance

- Use fictional data only. Do not commit real employee names, salaries,
  addresses or attendance information.
- Keep headers aligned with `config.json`.
- CSV, XML, JSON and text files can be edited directly on GitHub.
- Excel files must normally be downloaded, edited in Excel and uploaded again.
- Generated reports should not be committed unless they are intentionally
  retained as examples.
- Changes should be made on a branch and reviewed through a pull request.

## Repository access recommendation

Use a **private GitHub repository**. Keep yourself as owner and invite the one
collaborator with `Write` access. A public repository would allow everyone to
view the sample data, although only collaborators could change the repository.

## Publication status

The data, compensation rule and clean/negative-test separation are complete.
The remaining GitHub handoff inputs are:

1. the empty private repository URL; and
2. the collaborator's exact GitHub username.

The repository should contain fictional sample data only.
