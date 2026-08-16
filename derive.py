"""
derive.py
---------
Some sources give you one combined field (e.g. "John Robert Smith").
Others already give you split components (e.g. <First>, <Last> tags).
The destination is usually split into its final component columns.

This module derives split components FROM a combined source field, so the
reconciliation engine can compare the destination's FirstName/MiddleName/
LastName (etc.) against what the source *should* produce -- not just
compare whole blobs of text. This is what actually proves the transform
step derived things correctly, rather than just proving two strings match.

Configured per-source in config.json under "derived_fields":
    {"source_field": "Name", "type": "split_name",
     "output_fields": ["FirstName", "MiddleName", "LastName"]}

There's also a second kind of derived field -- one that COMBINES several
raw columns on the same record into one value, rather than splitting one
column apart. This is what turns "12 monthly salary columns" into one
"TotalSalary" figure:
    {"source_fields": ["Jan", "Feb", ..., "Dec"], "type": "sum_columns",
     "output_field": "TotalSalary"}

A variant, "sum_columns_prorated", does the same monthly sum but PRORATES
the join and leave months by day count, for employees who started or left
partway through the year:
    {"source_fields": ["Jan", ..., "Dec"], "type": "sum_columns_prorated",
     "output_field": "TotalSalary",
     "join_date_field": "JoinDate", "leave_date_field": "LeaveDate",
     "year": 2026}
This assumes each monthly column holds the FULL-month rate; only the
join/leave month's column gets scaled down (days actually worked / days in
that month). Every other month counts in full. This is a simplifying
assumption -- it doesn't handle mid-year raises or multiple employments in
one year -- but it's usually enough to catch a payroll extract that forgot
to prorate at all.

If a source already provides a component directly (via field_map), that
direct value is NOT overwritten by a derived one -- direct mappings win.
"""

import calendar
from datetime import datetime

from transforms import digits_only, numeric
from readers import _parse_date


def split_name(value):
    if not value or not str(value).strip():
        return {"FirstName": None, "MiddleName": None, "LastName": None}
    parts = str(value).strip().split()
    if len(parts) == 1:
        return {"FirstName": parts[0], "MiddleName": None, "LastName": None}
    if len(parts) == 2:
        return {"FirstName": parts[0], "MiddleName": None, "LastName": parts[1]}
    return {"FirstName": parts[0], "MiddleName": " ".join(parts[1:-1]), "LastName": parts[-1]}


def standardize_name_components(records: list, cfg: dict | None) -> list:
    """Makes configured name components structurally consistent.

    A name filler is added only to configured optional components (normally
    MiddleName and LastName), and only on records that already carry at least
    one name component. Sources such as salary/bonus files that contain no
    name at all are left untouched, so a filler can never fabricate a person.
    """
    if not cfg:
        return records
    fields = cfg.get("fields", ["FirstName", "MiddleName", "LastName"])
    fill_when_missing = cfg.get("fill_when_missing", fields[1:])
    filler = str(cfg.get("filler", "XX")).strip() or "XX"

    for rec in records:
        if not any(field in rec for field in fields):
            continue
        for field in fill_when_missing:
            if rec.get(field) is None or not str(rec.get(field)).strip():
                rec[field] = filler
    return records


def split_address(value):
    if not value or not str(value).strip():
        return {"AddressLine1": None, "AddressLine2": None, "AddressLine3": None}
    parts = [p.strip() for p in str(value).split(",")]
    parts = (parts + [None, None, None])[:3]
    return {"AddressLine1": parts[0], "AddressLine2": parts[1], "AddressLine3": parts[2]}


def split_phone(value):
    if not value:
        return {"CountryCode": None, "AreaCode": None, "LocalNumber": None}
    digits = digits_only(value)
    if len(digits) == 10:
        return {"CountryCode": "1", "AreaCode": digits[0:3], "LocalNumber": digits[3:]}
    if len(digits) == 11:
        return {"CountryCode": digits[0], "AreaCode": digits[1:4], "LocalNumber": digits[4:]}
    return {"CountryCode": None, "AreaCode": None, "LocalNumber": digits or None}


def sum_columns(rec: dict, rule: dict):
    """Sums several numeric-ish columns on the SAME record (e.g. 12 monthly
    salary columns) into one total. Unlike split_name/split_address/
    split_phone, this deriver needs the whole record, not one value -- see
    the branch in apply_derived_fields below."""
    total = 0.0
    any_val = False
    for f in rule["source_fields"]:
        n = numeric(rec.get(f))
        if n is not None:
            total += n
            any_val = True
    return round(total, 2) if any_val else None


def sum_columns_prorated(rec: dict, rule: dict):
    """Like sum_columns, but the join/leave month is scaled by the fraction
    of that month actually worked. Assumes source_fields are given in
    calendar order Jan..Dec (override with "month_numbers" if not)."""
    source_fields = rule["source_fields"]
    month_numbers = rule.get("month_numbers", list(range(1, len(source_fields) + 1)))
    join_date = _parse_date(rec.get(rule["join_date_field"])) if rule.get("join_date_field") else None
    leave_date = _parse_date(rec.get(rule["leave_date_field"])) if rule.get("leave_date_field") else None
    year = rule.get("year") or (join_date.year if join_date else (leave_date.year if leave_date else None))

    total = 0.0
    any_val = False
    for field, month in zip(source_fields, month_numbers):
        amt = numeric(rec.get(field))
        if amt is None:
            continue
        any_val = True
        if year is None:
            total += amt
            continue
        days_in_month = calendar.monthrange(year, month)[1]
        start_day = join_date.day if (join_date and join_date.year == year and join_date.month == month) else 1
        end_day = leave_date.day if (leave_date and leave_date.year == year and leave_date.month == month) else days_in_month
        worked_days = max(0, end_day - start_day + 1)
        total += amt * worked_days / days_in_month
    return round(total, 2) if any_val else None


def salary_with_lop(rec: dict, rule: dict):
    """Calculates gross, loss-of-pay deduction, and net annual salary.

    Each salary column contains the full-month salary rate. Its paired LOP
    column contains unpaid days for that month. The daily rate uses the actual
    calendar-day count (28/29/30/31), and join/leave dates restrict the days
    for which salary can be earned. LOP days are capped at eligible days so a
    malformed input cannot create a negative salary.

    The returned ``_salary_analysis`` rows feed the optional Salary Analysis
    report sheet; the canonical output fields feed normal reconciliation.
    """
    salary_fields = rule.get("salary_fields", rule.get("source_fields", []))
    lop_fields = rule.get("loss_of_pay_fields", [])
    if len(salary_fields) != len(lop_fields):
        raise ValueError("salary_with_lop requires one loss_of_pay_field per salary field")

    month_numbers = rule.get("month_numbers", list(range(1, len(salary_fields) + 1)))
    if len(month_numbers) != len(salary_fields):
        raise ValueError("salary_with_lop month_numbers must match salary_fields")
    month_labels = rule.get("month_labels", salary_fields)
    if len(month_labels) != len(salary_fields):
        raise ValueError("salary_with_lop month_labels must match salary_fields")

    join_date = _parse_date(rec.get(rule.get("join_date_field"))) if rule.get("join_date_field") else None
    leave_date = _parse_date(rec.get(rule.get("leave_date_field"))) if rule.get("leave_date_field") else None
    year = rule.get("year") or (join_date.year if join_date else (leave_date.year if leave_date else None))
    key_field = rule.get("key_field", "EmployeeID")

    gross_total = 0.0
    lop_days_total = 0.0
    lop_deduction_total = 0.0
    net_total = 0.0
    any_salary = False
    analysis_rows = []

    for salary_field, lop_field, month, month_label in zip(
        salary_fields, lop_fields, month_numbers, month_labels
    ):
        monthly_rate = numeric(rec.get(salary_field))
        raw_lop_days = numeric(rec.get(lop_field))
        lop_days = max(0.0, raw_lop_days or 0.0)

        if year is None:
            days_in_month = None
            eligible_days = None
        else:
            days_in_month = calendar.monthrange(year, month)[1]
            month_start = datetime(year, month, 1)
            month_end = datetime(year, month, days_in_month)
            eligible_start = max(month_start, join_date) if join_date else month_start
            eligible_end = min(month_end, leave_date) if leave_date else month_end
            eligible_days = max(0, (eligible_end - eligible_start).days + 1)

        if monthly_rate is None:
            gross_salary = None
            accepted_lop_days = min(lop_days, float(eligible_days or 0)) if eligible_days is not None else lop_days
            lop_deduction = None
            net_salary = None
        elif days_in_month is None:
            any_salary = True
            gross_salary = monthly_rate
            accepted_lop_days = lop_days
            lop_deduction = 0.0
            net_salary = monthly_rate
            gross_total += gross_salary
            net_total += net_salary
        else:
            any_salary = True
            accepted_lop_days = min(lop_days, float(eligible_days))
            gross_salary = monthly_rate * eligible_days / days_in_month
            lop_deduction = monthly_rate * accepted_lop_days / days_in_month
            net_salary = gross_salary - lop_deduction
            gross_total += gross_salary
            lop_deduction_total += lop_deduction
            net_total += net_salary

        lop_days_total += accepted_lop_days
        analysis_rows.append({
            "EmployeeID": rec.get(key_field),
            "Month": str(month_label),
            "DaysInMonth": days_in_month,
            "EligibleDays": eligible_days,
            "LossOfPayDays": round(accepted_lop_days, 2),
            "GrossSalary": round(gross_salary, 2) if gross_salary is not None else None,
            "LossOfPayDeduction": round(lop_deduction, 2) if lop_deduction is not None else None,
            "NetSalary": round(net_salary, 2) if net_salary is not None else None,
        })

    output_fields = rule.get("output_fields", {})
    return {
        output_fields.get("gross_salary", "GrossSalary"): round(gross_total, 2) if any_salary else None,
        output_fields.get("loss_of_pay_days", "TotalLossOfPayDays"): round(lop_days_total, 2),
        output_fields.get("loss_of_pay_deduction", "LossOfPayDeduction"): round(lop_deduction_total, 2) if any_salary else None,
        output_fields.get("net_salary", rule.get("output_field", "TotalSalary")): round(net_total, 2) if any_salary else None,
        "_salary_analysis": analysis_rows,
    }


DERIVERS = {
    "split_name": split_name,
    "split_address": split_address,
    "split_phone": split_phone,
}

# Derivers in this set take the whole record + the full rule dict
# (rec, rule) -> single value, and write to one "output_field" -- as
# opposed to DERIVERS above, which take one value and split it into
# several "output_fields".
MULTI_FIELD_DERIVERS = {
    "sum_columns": sum_columns,
    "sum_columns_prorated": sum_columns_prorated,
}

# These derivers use the whole record and can produce several canonical
# outputs plus analysis metadata in a single calculation.
RECORD_DERIVERS = {
    "salary_with_lop": salary_with_lop,
}


def apply_derived_fields(records: list, derived_fields_cfg: list) -> list:
    """Mutates and returns records, adding derived fields.
    A derived value only fills in a field that is missing/blank -- a value
    the source already mapped directly always wins over a derived guess."""
    if not derived_fields_cfg:
        return records
    for rec in records:
        for rule in derived_fields_cfg:
            if rule["type"] in RECORD_DERIVERS:
                derived = RECORD_DERIVERS[rule["type"]](rec, rule)
                for out_field, value in derived.items():
                    if out_field.startswith("_") or rec.get(out_field) in (None, ""):
                        rec[out_field] = value
                continue
            if rule["type"] in MULTI_FIELD_DERIVERS:
                fn = MULTI_FIELD_DERIVERS[rule["type"]]
                out_field = rule["output_field"]
                if rec.get(out_field) in (None, ""):
                    rec[out_field] = fn(rec, rule)
                continue
            fn = DERIVERS[rule["type"]]
            raw_val = rec.get(rule["source_field"])
            derived = fn(raw_val)
            for out_field in rule["output_fields"]:
                if rec.get(out_field) in (None, ""):
                    rec[out_field] = derived.get(out_field)
    return records


def apply_currency_conversion(records: list, currency_field: str, base_currency: str,
                               fx_rates: dict, amount_fields: list) -> list:
    """Converts amount_fields on each record into base_currency, in place,
    using that record's OWN currency (read from currency_field -- rows can
    be in different currencies within the same file) and
    fx_rates = {currency_code: units of base_currency per 1 unit of that
    currency}. Rows already in base_currency, or missing a currency value,
    are left untouched."""
    if not currency_field or not amount_fields:
        return records
    for rec in records:
        cur = rec.get(currency_field)
        if not cur or cur == base_currency:
            continue
        if cur not in fx_rates:
            raise ValueError(f"No fx_rate configured for currency '{cur}'")
        rate = fx_rates[cur]
        for f in amount_fields:
            n = numeric(rec.get(f))
            if n is not None:
                rec[f] = round(n * rate, 2)
    return records
