"""
reconcile.py
------------
Core engine. For every destination record:
  1. Find that key in every configured source.
  2. For each field being validated, collect the value(s) found across
     all sources that contain that key.
  3. Compare the destination's value against those source value(s), after
     applying the field's configured transformation rule to both sides.
  4. Classify the result.

Statuses produced (per field, per record):
  MATCH                  - destination value matches a source value exactly
                            (post-transform)
  MATCH_AFTER_TRANSFORM  - same as above but only equal after normalization
                            (i.e. raw strings differed, e.g. phone formatting)
  MISMATCH               - key found in source(s), field present, but no
                            source value matches the destination value
  MISSING_IN_DESTINATION - source has a value for this field, destination
                            does not
  FIELD_NOT_IN_SOURCE    - key found in source(s) but none of them carry
                            this field at all
  KEY_NOT_FOUND_IN_SOURCE- destination record's key wasn't found in ANY
                            source (possible fabricated/orphan record)

Some destination fields aren't a straight copy from one source -- they're
COMPUTED by combining fields that each came from a DIFFERENT source (e.g.
TotalCompensation = TotalSalary [from the salary sheet] + TotalBonus [from
the bonus file]). Those are declared in config.json under "computed_fields",
processed IN ORDER so a later entry can use an earlier one as an input:

    {"output_field": "TotalCompensation", "op": "sum",
     "sum_of": ["TotalSalary", "TotalBonus", "PerformanceBonus"]}

    {"output_field": "PerformanceBonus", "op": "tier_percentage",
     "base_field": "TotalSalary", "tier_field": "Rating",
     "tiers": {"A": 0.15, "B": 0.10, "C": 0.05}, "default_rate": 0}

"sum" adds up the resolved values of sum_of. "tier_percentage" looks up
tier_field's value in tiers and multiplies base_field by that percentage
(falling back to default_rate for an unrecognized/missing rating). Either
way, reconcile() resolves each input from whichever source carried it
(using the per-field results already produced) and compares the computed
total to the destination the same way as any other field.

Record matching across sources tolerates ID FORMAT drift (leading zeros,
dashes, case) via config["key_transform"] (e.g. "normalize_id"), applied
to every source's key AND the destination's key before matching -- so
'E007', 'e-007', and '007' are recognized as the same employee.
"""

from collections import defaultdict
from transforms import apply_transform


def index_by_key(records: list, key_field: str, key_transform: str) -> dict:
    idx = defaultdict(list)
    for r in records:
        k = r.get(key_field)
        if k is not None:
            idx[apply_transform(key_transform, str(k).strip())].append(r)
    return idx


def reconcile(sources_records: dict, destination_records: list, config: dict) -> list:
    """
    sources_records: {source_name: [records...]}
    destination_records: [records...]
    config: parsed config.json

    Returns a flat list of result rows, one per (destination_record, field).
    """
    key_field = config["key_field"]
    fields_to_validate = config["fields_to_validate"]
    field_transforms = config.get("field_transforms", {})
    key_transform = config.get("key_transform", "none")

    # Build an index per source: normalized key -> list of matching records
    source_indexes = {
        name: index_by_key(recs, key_field, key_transform) for name, recs in sources_records.items()
    }

    results = []

    for dest_rec in destination_records:
        dest_key = dest_rec.get(key_field)
        dest_key_str = apply_transform(key_transform, str(dest_key).strip()) if dest_key is not None else None

        # which sources contain this key at all?
        matching_sources = {
            name: idx.get(dest_key_str, [])
            for name, idx in source_indexes.items()
            if dest_key_str in idx
        }

        if not matching_sources:
            for field in fields_to_validate:
                results.append({
                    "key": dest_key_str,
                    "field": field,
                    "destination_value": dest_rec.get(field),
                    "source_values": {},
                    "status": "KEY_NOT_FOUND_IN_SOURCE",
                })
            continue

        for field in fields_to_validate:
            transform_name = field_transforms.get(field, "none")
            dest_raw = dest_rec.get(field)
            dest_norm = apply_transform(transform_name, dest_raw)

            # collect every source value for this field, across every source
            # record that shares this key (there may be >1 per source)
            source_values = {}  # source_name -> list of raw values
            for sname, recs in matching_sources.items():
                vals = [r.get(field) for r in recs if r.get(field) not in (None, "")]
                if vals:
                    source_values[sname] = vals

            if not source_values:
                status = "FIELD_NOT_IN_SOURCE" if dest_raw not in (None, "") else "MATCH"
                # (if dest also has nothing, and no source has it, treat as
                #  trivially consistent rather than flagging noise)
                if dest_raw in (None, "") and not source_values:
                    status = "MATCH"
                results.append({
                    "key": dest_key_str, "field": field,
                    "destination_value": dest_raw,
                    "source_values": source_values,
                    "status": status,
                })
                continue

            if dest_raw in (None, ""):
                results.append({
                    "key": dest_key_str, "field": field,
                    "destination_value": dest_raw,
                    "source_values": source_values,
                    "status": "MISSING_IN_DESTINATION",
                })
                continue

            # compare
            exact_match = False
            transformed_match = False
            for sname, vals in source_values.items():
                for v in vals:
                    if v == dest_raw:
                        exact_match = True
                    if apply_transform(transform_name, v) == dest_norm:
                        transformed_match = True

            if exact_match:
                status = "MATCH"
            elif transformed_match:
                status = "MATCH_AFTER_TRANSFORM"
            else:
                status = "MISMATCH"

            results.append({
                "key": dest_key_str, "field": field,
                "destination_value": dest_raw,
                "source_values": source_values,
                "status": status,
            })

    computed_fields = config.get("computed_fields", [])
    for spec in computed_fields:
        results += _resolve_one_computed_field(results, destination_records, config, spec, source_indexes)

    return results


def _resolve_field_value(results: list, source_indexes: dict, key: str, field: str):
    """Resolves a field's value for a key, in priority order:
      1. A result already produced above (a validated field, OR an earlier
         computed field's output -- this is what lets computed_fields chain).
      2. Falling back to the raw source records directly, for fields that
         were never added to fields_to_validate (e.g. a rating used only to
         drive a tiered bonus, not reconciled against the destination
         itself)."""
    for r in results:
        if r["key"] == key and r["field"] == field:
            if r["source_values"]:
                first_vals = next(iter(r["source_values"].values()))
                return first_vals[0] if first_vals else None
            return None
    for idx in source_indexes.values():
        for rec in idx.get(key, []):
            v = rec.get(field)
            if v not in (None, ""):
                return v
    return None


def _resolve_one_computed_field(results: list, destination_records: list, config: dict, spec: dict,
                                 source_indexes: dict) -> list:
    key_field = config["key_field"]
    field_transforms = config.get("field_transforms", {})
    key_transform = config.get("key_transform", "none")
    out_field = spec["output_field"]
    op = spec.get("op", "sum")
    transform_name = field_transforms.get(out_field, "numeric")
    computed_results = []

    for dest_rec in destination_records:
        dest_key = dest_rec.get(key_field)
        dest_key_str = apply_transform(key_transform, str(dest_key).strip()) if dest_key is not None else None
        dest_raw = dest_rec.get(out_field)

        if op == "tier_percentage":
            base_field = spec["base_field"]
            tier_field = spec["tier_field"]
            tiers = spec["tiers"]
            default_rate = spec.get("default_rate", 0)

            base_val = apply_transform("numeric", _resolve_field_value(results, source_indexes, dest_key_str, base_field))
            rating_raw = _resolve_field_value(results, source_indexes, dest_key_str, tier_field)
            rating = str(rating_raw).strip().upper() if rating_raw not in (None, "") else None
            have_all_inputs = base_val is not None

            if have_all_inputs:
                rate = tiers.get(rating, default_rate)
                computed_total = round(base_val * rate, 2)
                label = f"Computed ({base_field} x {tier_field}[{rating or '?'}]={rate})"
            else:
                computed_total = None
                label = f"Computed ({base_field} x {tier_field})"
        else:  # op == "sum"
            input_fields = spec["sum_of"]
            numeric_components = {f: apply_transform("numeric", _resolve_field_value(results, source_indexes, dest_key_str, f)) for f in input_fields}
            have_all_inputs = all(v is not None for v in numeric_components.values())
            computed_total = round(sum(numeric_components.values()), 2) if have_all_inputs else None
            label = "Computed (" + " + ".join(input_fields) + ")"

        source_values = {label: [computed_total]} if have_all_inputs else {}

        if not have_all_inputs:
            status = "FIELD_NOT_IN_SOURCE" if dest_raw not in (None, "") else "MATCH"
        elif dest_raw in (None, ""):
            status = "MISSING_IN_DESTINATION"
        else:
            dest_norm = apply_transform(transform_name, dest_raw)
            status = "MATCH" if apply_transform(transform_name, computed_total) == dest_norm else "MISMATCH"

        computed_results.append({
            "key": dest_key_str, "field": out_field,
            "destination_value": dest_raw,
            "source_values": source_values,
            "status": status,
        })

    return computed_results


def summarize(results: list) -> dict:
    summary = defaultdict(int)
    for r in results:
        summary[r["status"]] += 1
    summary["TOTAL_CHECKS"] = len(results)
    return dict(summary)
