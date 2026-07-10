#!/bin/bash
# fetch_mimiciv.sh  —  Download full MIMIC-IV v3.1 (hosp + icu) for the Task C follow-on.
#
# WHY: the cardiac-ext subset on disk lacks mortality, demographics (age/sex), ICU stays,
# vitals, and meds. Full MIMIC-IV restores them -> enables true mortality outcomes, age/sex
# confounder adjustment, and anchoring to published PCI RCT effect sizes.
#
# RUN THIS ON THE DTN, NOT THE LOGIN NODE (per cluster policy for large transfers):
#     ssh dtn.sherlock.stanford.edu
#     cd /scratch/users/karun09/CAUSAL_BENCHMARK && bash jobs/fetch_mimiciv.sh
#
# REQUIRES: a PhysioNet account that is (a) credentialed and (b) has signed the DUA for
# the "MIMIC-IV" project specifically (separate from the cardiac-ext module). Set your
# PhysioNet username below or via env PN_USER; you'll be prompted for the password.
#
# SIZE: hosp+icu gzipped CSVs ≈ 7 GB (expands larger). Goes to $OAK if available (persistent,
# reusable), else $SCRATCH (90-day purge — re-touch or move to $OAK to keep).

set -euo pipefail

PN_USER="${PN_USER:-CHANGE_ME_physionet_username}"
if [ "$PN_USER" = "CHANGE_ME_physionet_username" ]; then
  echo "ERROR: set your PhysioNet username:  PN_USER=yourname bash jobs/fetch_mimiciv.sh" >&2
  exit 1
fi

# Prefer Oak (persistent) for a reusable dataset; fall back to Scratch.
DEST_ROOT="${MIMIC_DEST:-${OAK:-$SCRATCH}}"
DEST="$DEST_ROOT/physionet.org/files/mimiciv/3.1"
mkdir -p "$DEST"
echo "Downloading MIMIC-IV v3.1 (hosp+icu) to: $DEST"
echo "Host: $(hostname)  (this should be the DTN)"

BASE="https://physionet.org/files/mimiciv/3.1"
# -r recursive, -N timestamp (resume-friendly), -c continue, -np stay under the path,
# --cut-dirs keeps the layout tidy. Modules: hospital (hosp) + ICU (icu).
for MOD in hosp icu; do
  echo "=== module: $MOD ==="
  wget -r -N -c -np --user "$PN_USER" --ask-password \
       -e robots=off --reject "index.html*" \
       -nH --cut-dirs=2 -P "$DEST_ROOT/physionet.org/files" \
       "$BASE/$MOD/"
done

echo "=== Done. Key tables for the follow-on: ==="
echo "  $DEST/hosp/admissions.csv.gz   (deathtime, hospital_expire_flag, admit/dischtime)"
echo "  $DEST/hosp/patients.csv.gz     (anchor_age, gender, dod)"
echo "  $DEST/icu/icustays.csv.gz      (intime, outtime, los)"
echo "Next: link to the cardiac cohort by subject_id/hadm_id to add mortality/14d-mortality/"
echo "ICU-LOS outcomes + age/sex covariates, then re-run select_outcome / matching / scoring."
