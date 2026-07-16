#!/usr/bin/env bash
#
# reduce_to_icu_acute_hf.sh
# ------------------------------------------------------------------
# Reduces the existing acute-HF cohort IN PLACE to only those patients
# who had an ICU stay DURING their acute-HF admission (i.e. an icustay
# whose hadm_id carries an acute-HF ICD code). Their complete record is
# retained; all other patients are removed from every table.
#
#   before: 17,463 patients
#   after :  9,236 patients (had ICU stay during acute-HF admission)
#
# Safe overwrite: each table is filtered to a temp file, then swapped in.
# ------------------------------------------------------------------
set -euo pipefail

REPO="/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
ROOT="$REPO/Version_6/acute_hf_cohort"
MIRROR="$ROOT/files/mimiciv/3.1"
COHORT_DIR="$ROOT/cohort"
KEEP="$COHORT_DIR/cohort_subject_ids.txt"   # will be overwritten with the reduced set

ACUTE_HF_CODES="I5021 I5023 I5031 I5033 I5041 I5043 I50811 I50813 42821 42823 42831 42833 42841 42843"

echo "=================================================================="
echo " Reducing acute-HF cohort to ICU-during-acute-HF-admission patients"
echo "=================================================================="

# ---- Step 1: acute-HF admissions (hadm_id) ----
echo "[1/4] Finding acute-HF admissions ..."
TMP_HADM=$(mktemp)
zcat < "$MIRROR/hosp/diagnoses_icd.csv.gz" | awk -F, -v codes="$ACUTE_HF_CODES" '
  BEGIN { n = split(codes, a, " "); for (i=1;i<=n;i++) hf[a[i]]=1 }
  FNR>1 && ($4 in hf) { print $2 }
' | sort -u > "$TMP_HADM"
echo "      -> $(wc -l < "$TMP_HADM" | tr -d ' ') acute-HF admissions"

# ---- Step 2: keep-set = patients with an ICU stay on an acute-HF admission ----
# icustays cols: subject_id(1),hadm_id(2),stay_id(3)
echo "[2/4] Deriving keep-set (patients w/ ICU stay during acute-HF admission) ..."
TMP_KEEP=$(mktemp)
zcat < "$MIRROR/icu/icustays.csv.gz" | awk -F, '
  FNR==NR { h[$1]=1; next }
  FNR>1 && ($2 in h) { print $1 }
' "$TMP_HADM" - | sort -u > "$TMP_KEEP"
N_KEEP=$(wc -l < "$TMP_KEEP" | tr -d ' ')
echo "      -> $N_KEEP patients kept"

# ---- Step 3: re-filter every table in place by the keep-set ----
echo "[3/4] Re-filtering tables in place ..."
reduce_table() {
  local f="$1"
  local header col
  IFS= read -r header < <(zcat < "$f")
  col=$(awk -F, -v h="$header" 'BEGIN{
          n=split(h,x,","); for(i=1;i<=n;i++){gsub(/\r/,"",x[i]); if(x[i]=="subject_id"){print i; exit}}
        }')
  if [ -z "$col" ]; then
    printf "      keep   %-28s (dictionary, unchanged)\n" "$(basename "$f")"
    return
  fi
  local tmp="$f.tmp"
  awk -F, -v col="$col" '
    FNR==NR { ids[$1]=1; next }
    FNR==1  { print; next }
    ($col in ids)
  ' "$TMP_KEEP" <(zcat < "$f") | gzip -c > "$tmp"
  mv "$tmp" "$f"          # atomic swap
  printf "      reduce %-28s (subject_id col %s)\n" "$(basename "$f")" "$col"
}

for module in hosp icu; do
  echo "  -- $module --"
  for f in "$MIRROR/$module"/*.csv.gz; do
    [ -e "$f" ] || continue
    reduce_table "$f"
  done
done

# ---- Step 4: refresh cohort id lists + README ----
echo "[4/4] Refreshing manifest ..."
cp "$TMP_KEEP" "$KEEP"
zcat < "$MIRROR/hosp/diagnoses_icd.csv.gz" | awk -F, 'FNR>1{print $2}' | sort -u > "$COHORT_DIR/cohort_hadm_ids.txt"
N_HADM=$(wc -l < "$COHORT_DIR/cohort_hadm_ids.txt" | tr -d ' ')

cat > "$ROOT/README.md" <<EOF
# Acute Heart Failure + ICU Cohort (derived from MIMIC-IV v3.1)

Patient-level cohort, reduced to patients who had an ICU stay DURING their
acute-HF admission. Each kept patient's COMPLETE record is retained across
all tables.

- Unique patients (subject_id): $N_KEEP
- Unique admissions (hadm_id) : $N_HADM
- Selection: >=1 acute-HF ICD code AND an icustay on that same hadm_id
- Source: datasets/2physionet.org/files/mimiciv/3.1

## Cohort ICD codes (dot-less, as stored in MIMIC)
ICD-10: I5021 I5023 I5031 I5033 I5041 I5043 I50811 I50813
ICD-9 : 42821 42823 42831 42833 42841 42843

## Layout
files/mimiciv/3.1/hosp/*.csv.gz   (filtered to cohort patients)
files/mimiciv/3.1/icu/*.csv.gz    (filtered to cohort patients)
Dictionary tables (d_*, provider, caregiver) are unchanged.
cohort/cohort_subject_ids.txt     (one subject_id per line)
cohort/cohort_hadm_ids.txt        (one hadm_id per line)
EOF

rm -f "$TMP_HADM" "$TMP_KEEP"

echo "=================================================================="
echo " DONE. Patients: $N_KEEP  Admissions: $N_HADM"
echo "=================================================================="
