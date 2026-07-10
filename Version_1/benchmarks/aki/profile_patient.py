import meds_reader
from pathlib import Path
from collections import Counter

EHRSHOT_PATH = Path(__file__).parent.parent / "EHRSHOT Hackathon Project" / "meds_reader_omop_ehrshot"

# The 20 cardiac nextlab benchmark patients
CASE_SUBJECTS = [
    115967110, 115967114, 115967119, 115967125, 115967128,
    115967129, 115967133, 115967134, 115967140, 115967142,
    115967149, 115967161, 115967163, 115967164, 115967167,
    115967180, 115967189, 115967190, 115967192, 115967227,
]

def estimate_tokens(n_chars):
    return n_chars // 4  # rough estimate: 4 chars per token

def profile_patient(db, subject_id):
    subject = db[subject_id]
    events  = list(subject.events)

    table_counts   = Counter(e.table for e in events)
    table_codes    = {}
    for e in events:
        table_codes.setdefault(e.table, set()).add(e.code)

    # Estimate tokens if we rendered every event as a text row
    # Format: "YYYY-MM-DD HH:MM | table | code | value | unit"
    total_chars = sum(
        len(f"{e.time} | {e.table} | {e.code} | {e.numeric_value or e.text_value or ''} | {e.unit or ''}")
        for e in events
    )
    total_tokens = estimate_tokens(total_chars)

    return {
        "subject_id":   subject_id,
        "total_events": len(events),
        "total_tokens": total_tokens,
        "by_table":     dict(table_counts),
        "unique_codes": {t: len(codes) for t, codes in table_codes.items()},
    }

def main():
    print(f"Loading EHRSHOT from {EHRSHOT_PATH}...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))

    profiles = []
    for sid in CASE_SUBJECTS:
        p = profile_patient(db, sid)
        profiles.append(p)

    # Print per-patient summary
    print(f"\n{'Subject':<14} {'Events':>8} {'Est.Tokens':>12} {'measurement':>13} {'condition':>11} {'procedure':>11} {'drug':>8} {'visit':>8}")
    print("-" * 90)
    for p in profiles:
        bt = p["by_table"]
        print(
            f"{p['subject_id']:<14} "
            f"{p['total_events']:>8,} "
            f"{p['total_tokens']:>12,} "
            f"{bt.get('measurement', 0):>13,} "
            f"{bt.get('condition', 0):>11,} "
            f"{bt.get('procedure', 0):>11,} "
            f"{bt.get('drug_exposure', bt.get('drug', 0)):>8,} "
            f"{bt.get('visit', 0):>8,}"
        )

    # Aggregate stats
    print("\n--- Aggregate across 20 patients ---")
    total_events = [p["total_events"] for p in profiles]
    total_tokens = [p["total_tokens"] for p in profiles]
    print(f"  Events  — min: {min(total_events):,}  max: {max(total_events):,}  median: {sorted(total_events)[10]:,}")
    print(f"  Tokens  — min: {min(total_tokens):,}  max: {max(total_tokens):,}  median: {sorted(total_tokens)[10]:,}")

    # Print all unique table names seen
    all_tables = set()
    for p in profiles:
        all_tables.update(p["by_table"].keys())
    print(f"\n  All tables present: {sorted(all_tables)}")

    # Deep-dive one patient: show unique code prefixes per table
    print(f"\n--- Deep dive: subject {CASE_SUBJECTS[0]} ---")
    subject = db[CASE_SUBJECTS[0]]
    events  = list(subject.events)
    by_table = {}
    for e in events:
        by_table.setdefault(e.table, []).append(e)

    for table, evts in sorted(by_table.items()):
        code_prefixes = Counter(e.code.split("/")[0] for e in evts)
        sample_codes  = list({e.code for e in evts})[:5]
        print(f"  {table}: {len(evts)} events | code systems: {dict(code_prefixes)} | sample: {sample_codes}")

if __name__ == "__main__":
    main()
