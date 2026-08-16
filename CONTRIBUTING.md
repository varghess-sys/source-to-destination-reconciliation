# Contributing

This repository is intended for controlled collaboration between the owner and
one invited contributor.

## Recommended workflow

1. Create a branch, for example `data/update-lop-scenarios`.
2. Make one logical set of changes.
3. Run the reconciliation locally.
4. Inspect the Summary, Issues, Accepted Transforms, Salary Analysis and Full
   Detail sheets.
5. Commit the code/config/data changes, but not generated reports unless an
   example report is intentionally being updated.
6. Open a pull request and describe the expected effect on reconciliation.
7. Merge only after the owner reviews the change.

## Data rules

- Use fictional employee and payroll data only.
- Do not commit API keys, passwords, connection strings or `.env` files.
- Preserve headers expected by `config.json`.
- Document deliberate mismatch/orphan/missing-value test cases.
- If changing salary or LOP data, state the expected net salary.
- If changing compensation logic, update `config.json`, documentation and test
  expectations together.

## Validation before submitting

```powershell
py -m py_compile *.py
py main.py config.json reconciliation_report_review.xlsx
py main.py config_test_cases.json reconciliation_report_test_cases_review.xlsx
```

The clean configuration should produce no genuine issues. Confirm that any new
mismatches are intentional and explained in the negative-test dataset.
