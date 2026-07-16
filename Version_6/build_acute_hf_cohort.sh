#!/usr/bin/env bash
#
# build_acute_hf_cohort.sh
# ------------------------------------------------------------------
# Builds a patient-level "acute heart failure" cohort from the full raw
# MIMIC-IV v3.1 database, mirroring the original folder structure exactly
# but containing ONLY patients who carry at least one acute-HF ICD code
# on any admission (their entire longitudinal record is kept).
#
# Cohort definition (ICD-9-CM + ICD-10-CM, stored dot-less as in MIMIC):
#   ICD-10:  I5021 I5023 I5031 I5033 I5041 I5043 I50811 I50813
#   ICD-9 :  42821 42823 42831 42833 42841 42843
# (includes acute-on-chronic variants; excludes chronic/unspecified HF)
#
# Method:
#   1. Scan hosp/diagnoses_icd.csv.gz -> set of qualifying subject_id.
#   2. For every data table, auto-detect the subject_id column from its
#      header and stream-filter rows whose subject_id is in the cohort.
#   3. Dictionary/reference tables (no subject_id) are copied verbatim.
#   Output preserves the exact MIMIC layout: files/mimiciv/3.1/{hosp,icu}.
# ------------------------------------------------------------------
set -euo pipefail

# ---- paths ----
REPO="/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research"
SRC="$REPO/datasets/2physionet.org/files/mimiciv/3.1"
OUT_ROOT="$REPO/Version_6/acute_hf_cohort"
MIRROR="$OUT_ROOT/files/mimiciv/3.1"
COHORT_DIR="$OUT_ROOT/cohort"
IDS="$COHORT_DIR/cohort_subject_ids.txt"

# ---- acute-HF ICD codes ----
ACUTE_HF_CODES="I5021 I5023 I5031 I5033 I5041 I5043 I50811 I50813 42821 42823 42831 42833 42841 42843"

mkdir -p "$MIRROR/hosp" "$MIRROR/icu" "$COHORT_DIR"

echo "=================================================================="
echo " Acute-HF cohort builder"
echo " Source : $SRC"
echo " Output : $OUT_ROOT"
echo "=================================================================="

# ------------------------------------------------------------------
# Step 1: derive the cohort (qualifying subject_ids)
# diagnoses_icd columns: subject_id(1),hadm_id(2),seq_num(3),icd_code(4),icd_version(5)
# ------------------------------------------------------------------
echo "[1/3] Scanning diagnoses_icd for acute-HF patients ..."
zcat < "$SRC/hosp/diagnoses_icd.csv.gz" | awk -F, -v codes="$ACUTE_HF_CODES" '
  BEGIN { n = split(codes, a, " "); for (i = 1; i <= n; i++) hf[a[i]] = 1 }
  FNR == 1 { next }
  ($4 in hf) { print $1 }
' | sort -u > "$IDS"

N_PATIENTS=$(wc -l < "$IDS" | tr -d ' ')
echo "      -> $N_PATIENTS unique acute-HF patients"

if [ "$N_PATIENTS" -eq 0 ]; then
  echo "ERROR: cohort is empty; aborting." >&2
  exit 1
fi

# ------------------------------------------------------------------
# Step 2 helper: filter one gzipped table by subject_id membership.
#   - auto-detects the subject_id column from the header
#   - copies verbatim if there is no subject_id column
# ------------------------------------------------------------------
filter_table() {
  local src="$1" dst="$2"
  local header col
  # read only the first line; process-substitution avoids a pipe that would
  # SIGPIPE zcat and trip `set -o pipefail`/`set -e`
  IFS= read -r header < <(zcat < "$src")

  # find 1-based index of the "subject_id" column
  col=$(awk -F, -v h="$header" 'BEGIN{
           n=split(h,f,","); for(i=1;i<=n;i++){ gsub(/\r/,"",f[i]); if(f[i]=="subject_id"){print i; exit} }
        }')

  if [ -z "$col" ]; then
    # no subject_id -> dictionary/reference table, copy whole
    cp "$src" "$dst"
    printf "      copy   %-28s (no subject_id)\n" "$(basename "$src")"
    return
  fi

  # stream-filter: keep header + rows whose subject_id is in the cohort
  awk -F, -v col="$col" '
    FNR == NR { ids[$1] = 1; next }   # first file: cohort ids
    FNR == 1  { print; next }         # data header
    ($col in ids)                     # keep cohort rows
  ' "$IDS" <(zcat < "$src") | gzip -c > "$dst"

  printf "      filter %-28s (subject_id col %s)\n" "$(basename "$src")" "$col"
}

# ------------------------------------------------------------------
# Step 2: filter every table in hosp/ and icu/
# ------------------------------------------------------------------
echo "[2/3] Filtering tables ..."
for module in hosp icu; do
  echo "  -- $module --"
  for src in "$SRC/$module"/*.csv.gz; do
    [ -e "$src" ] || continue
    filter_table "$src" "$MIRROR/$module/$(basename "$src")"
  done
done

# ------------------------------------------------------------------
# Step 3: copy distribution metadata + write a cohort manifest
# ------------------------------------------------------------------
echo "[3/3] Copying metadata + writing manifest ..."
for meta in CHANGELOG.txt LICENSE.txt; do
  [ -e "$SRC/$meta" ] && cp "$SRC/$meta" "$MIRROR/$meta"
done

# hadm_id list for the cohort (handy for admission-level joins later)
zcat < "$MIRROR/hosp/diagnoses_icd.csv.gz" | awk -F, 'FNR>1{print $2}' | sort -u > "$COHORT_DIR/cohort_hadm_ids.txt"
N_HADM=$(wc -l < "$COHORT_DIR/cohort_hadm_ids.txt" | tr -d ' ')

cat > "$OUT_ROOT/README.md" <<EOF
# Acute Heart Failure Cohort (derived from MIMIC-IV v3.1)

Patient-level cohort: every patient with >=1 acute-HF ICD code on any
admission, with their COMPLETE record retained across all tables.

- Unique patients (subject_id): $N_PATIENTS
- Unique admissions (hadm_id) : $N_HADM
- Source: datasets/2physionet.org/files/mimiciv/3.1

## Cohort ICD codes (dot-less, as stored in MIMIC)
ICD-10: I5021 I5023 I5031 I5033 I5041 I5043 I50811 I50813
ICD-9 : 42821 42823 42831 42833 42841 42843

## Layout
files/mimiciv/3.1/hosp/*.csv.gz   (filtered to cohort patients)
files/mimiciv/3.1/icu/*.csv.gz    (filtered to cohort patients)
Dictionary tables (d_*, provider, caregiver) are copied unchanged.
cohort/cohort_subject_ids.txt     (one subject_id per line)
cohort/cohort_hadm_ids.txt        (one hadm_id per line)

NOTE: SHA256SUMS.txt from the source is intentionally NOT copied, since
the filtered files differ from the originals.
EOF

echo "=================================================================="
echo " DONE."
echo "   Patients   : $N_PATIENTS"
echo "   Admissions : $N_HADM"
echo "   Output     : $OUT_ROOT"
echo "=================================================================="
