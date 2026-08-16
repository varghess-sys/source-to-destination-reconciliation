"""
main.py
-------
Run:  python main.py [config.json] [output.xlsx|output.pdf]

Loads the mapping config, reads every source and the destination, applies
currency conversion and field derivation, runs the reconciliation, prints
a console summary, and writes the report. The report format is chosen by
the output file's extension:
  .xlsx -> Excel workbook (default; sortable/filterable, easiest to read)
  .pdf  -> PDF report (original fixed-layout format, still available)
"""

import sys
import json

import readers
from readers import read_source, read_destination
from derive import (
    apply_derived_fields,
    apply_currency_conversion,
    standardize_name_components,
)
from reconcile import reconcile, summarize


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "reconciliation_report.xlsx"

    with open(config_path) as f:
        config = json.load(f)

    base_currency = config.get("base_currency")
    fx_rates = config.get("fx_rates", {})

    readers.READ_WARNINGS.clear()

    print(f"Loading {len(config['sources'])} source(s)...")
    sources_records = {}
    salary_analysis = []
    for src_cfg in config["sources"]:
        recs = read_source(src_cfg)
        if src_cfg.get("currency_field") and base_currency:
            recs = apply_currency_conversion(
                recs, src_cfg["currency_field"], base_currency, fx_rates,
                src_cfg.get("currency_amount_fields", []),
            )
        recs = apply_derived_fields(recs, src_cfg.get("derived_fields"))
        recs = standardize_name_components(recs, config.get("name_standardization"))
        for rec in recs:
            salary_analysis.extend(rec.get("_salary_analysis", []))
        sources_records[src_cfg["name"]] = recs
        print(f"  - {src_cfg['name']} ({src_cfg['type']}): {len(recs)} records")

    print("Loading destination...")
    dest_records = read_destination(config["destination"])
    dest_records = apply_derived_fields(dest_records, config["destination"].get("derived_fields"))
    dest_records = standardize_name_components(dest_records, config.get("name_standardization"))
    print(f"  - destination: {len(dest_records)} records")

    if readers.READ_WARNINGS:
        print(f"\n--- {len(readers.READ_WARNINGS)} row(s) skipped/flagged while reading ---")
        for w in readers.READ_WARNINGS:
            print(f"  ! {w}")

    print("\nReconciling...")
    results = reconcile(sources_records, dest_records, config)
    summary = summarize(results)

    print("\n--- Summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if output_path.lower().endswith(".pdf"):
        from report import build_report
    else:
        from report_xlsx import build_report

    print(f"\nBuilding report -> {output_path}")
    build_report(results, summary, config, output_path, salary_analysis=salary_analysis)
    print("Done.")


if __name__ == "__main__":
    main()
