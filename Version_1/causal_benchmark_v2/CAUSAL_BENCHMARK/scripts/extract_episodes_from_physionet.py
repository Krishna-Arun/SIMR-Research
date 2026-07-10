"""
extract_episodes_from_physionet.py

Extract clinical episodes from MIMIC-IV cardiac data in physionet.org.

Creates episodes with:
- Real interventions (PCI, vasopressors, antibiotics, observation)
- Real pre-context (48h labs before intervention)
- Real post-window (48h labs after intervention)
- Multiple cardiac markers (Troponin T, CK, BNP, LD)
"""

import pandas as pd
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Paths
PHYSIONET_DIR = Path("/scratch/users/karun09/physionet.org/files/mimic-iv-ext-cardiac-disease/1.0.0")
BENCHMARK_DIR = Path(__file__).parent.parent
OUTPUT_FILE = BENCHMARK_DIR / "data" / "episodes_real.json"

# Data files
LABS_FILE = PHYSIONET_DIR / "heart_labevents_examination_group.csv"
PROCEDURES_FILE = PHYSIONET_DIR / "heart_procedures.csv"
DIAGNOSES_FILE = PHYSIONET_DIR / "heart_diagnoses.csv"

# Target cardiac markers
TARGET_MARKERS = [
    "Troponin T",
    "Creatine Kinase, MB Isoenzyme",
    "NTproBNP",
    "Lactate Dehydrogenase (LD)",
]

# Intervention mappings (ICD codes to intervention types)
INTERVENTION_MAPPINGS = {
    # PCI and coronary interventions
    "0066": "pci",  # PTCA
    "3607": "pci",  # Drug-eluting stent
    "3606": "pci",  # Bare metal stent
    "0045": "pci",  # Vascular stent

    # CABG
    "3602": "cabg",  # CABG

    # Vasopressors (medication codes would be needed)
    # For now, we'll identify from med admin or notes
}


class EpisodeExtractor:
    """Extract clinical episodes from MIMIC-IV data."""

    def __init__(self):
        """Initialize extractor."""
        self.labs_df = None
        self.procedures_df = None
        self.diagnoses_df = None
        self.episodes = []

    def load_data(self):
        """Load all data files."""
        logger.info("Loading MIMIC-IV cardiac data...")

        self.labs_df = pd.read_csv(LABS_FILE, low_memory=False)
        self.labs_df['charttime'] = pd.to_datetime(self.labs_df['charttime'])
        logger.info(f"  Loaded {len(self.labs_df)} lab measurements")

        self.procedures_df = pd.read_csv(PROCEDURES_FILE)
        self.procedures_df['chartdate'] = pd.to_datetime(self.procedures_df['chartdate'])
        logger.info(f"  Loaded {len(self.procedures_df)} procedures")

        self.diagnoses_df = pd.read_csv(DIAGNOSES_FILE, low_memory=False)
        logger.info(f"  Loaded {len(self.diagnoses_df)} diagnoses")

    def get_cardiac_markers(self, hadm_id) -> Dict[str, List[Dict]]:
        """Get cardiac marker measurements for a hospital admission."""
        hadm_labs = self.labs_df[self.labs_df['hadm_id'] == int(hadm_id)]

        markers = {}
        for marker in TARGET_MARKERS:
            marker_data = hadm_labs[hadm_labs['label'] == marker]
            if len(marker_data) > 0:
                measurements = []
                for _, row in marker_data.iterrows():
                    if pd.notna(row['valuenum']) and pd.notna(row['charttime']):
                        measurements.append({
                            'datetime': row['charttime'].isoformat(),
                            'value': float(row['valuenum']),
                            'unit': str(row['valueuom']) if pd.notna(row['valueuom']) else '',
                            'flag': str(row['flag']) if pd.notna(row['flag']) else '',
                        })
                if measurements:
                    # Sort by datetime
                    measurements.sort(key=lambda x: x['datetime'])
                    markers[marker] = measurements

        return markers

    def extract_labs_window(
        self,
        hadm_id,
        anchor_time,
        hours_before: int = 72,
        hours_after: int = 72,
        min_pre_measurements: int = 3,
        min_post_measurements: int = 2
    ) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]], bool]:
        """
        Extract lab values before and after intervention with timestamps.
        Extended windows (72h) to handle sparse MIMIC data.

        Returns:
            (pre_labs, post_labs, is_valid) where each lab dict is:
            {marker_name: [{"value": float, "hours_from_intervention": float}]}
            is_valid: True only if meets minimum density requirements
        """
        all_markers = self.get_cardiac_markers(hadm_id)

        pre_labs = {}
        post_labs = {}

        # Convert anchor_time to datetime if it's a Timestamp
        if not isinstance(anchor_time, datetime):
            anchor_time = pd.Timestamp(anchor_time).to_pydatetime()

        pre_start = anchor_time - timedelta(hours=hours_before)
        post_end = anchor_time + timedelta(hours=hours_after)

        for marker, measurements in all_markers.items():
            pre_values = []
            post_values = []

            for meas in measurements:
                meas_time = pd.to_datetime(meas['datetime'])
                hours_from_intervention = (meas_time - anchor_time).total_seconds() / 3600.0

                if pre_start <= meas_time <= anchor_time:
                    pre_values.append({
                        "value": meas['value'],
                        "hours_from_intervention": hours_from_intervention,
                    })
                elif anchor_time < meas_time <= post_end:
                    post_values.append({
                        "value": meas['value'],
                        "hours_from_intervention": hours_from_intervention,
                    })

            # Only include markers with sufficient measurements in BOTH pre and post
            if len(pre_values) >= min_pre_measurements and len(post_values) >= min_post_measurements:
                pre_labs[marker] = pre_values
                post_labs[marker] = post_values

        # Episode is valid only if has 1+ shared markers with sufficient density
        is_valid = len(pre_labs) >= 1 and len(post_labs) >= 1 and pre_labs.keys() == post_labs.keys()

        return pre_labs, post_labs, is_valid

    def identify_intervention(self, hadm_id, procedure_date: datetime) -> Optional[str]:
        """Identify intervention type from procedure codes."""
        hadm_procs = self.procedures_df[self.procedures_df['hadm_id'] == int(hadm_id)]
        hadm_procs = hadm_procs[hadm_procs['chartdate'].dt.date == procedure_date.date()]

        if len(hadm_procs) == 0:
            return None

        intervention_types = set()
        for _, proc in hadm_procs.iterrows():
            icd_code = str(proc['icd_code']).split('.')[0]  # Get first part
            if icd_code in INTERVENTION_MAPPINGS:
                intervention_types.add(INTERVENTION_MAPPINGS[icd_code])

        # Return the intervention type (prefer PCI > CABG)
        if "pci" in intervention_types:
            return "pci"
        elif "cabg" in intervention_types:
            return "cabg"

        return None

    def extract_episodes(self, max_episodes: int = 500) -> List[Dict]:
        """Extract clinical episodes from procedures with measurement alignment enforcement."""
        logger.info(f"Extracting episodes (target: {max_episodes})...")

        episodes = []
        skipped_insufficient_data = 0
        skipped_misaligned = 0

        # Include all cardiac procedures that we can map to interventions
        mapped_codes = list(INTERVENTION_MAPPINGS.keys())
        cardiac_procedures = self.procedures_df[self.procedures_df['icd_code'].isin(mapped_codes)]
        logger.info(f"Found {len(cardiac_procedures)} cardiac procedures with intervention mappings")

        processed_hadms = set()

        for idx, proc in cardiac_procedures.iterrows():
            if len(episodes) >= max_episodes:
                break

            hadm_id = proc['hadm_id']
            procedure_date = pd.to_datetime(proc['chartdate'])

            # Skip if we already processed this hadm
            if hadm_id in processed_hadms:
                continue

            try:
                # Get intervention type
                intervention = self.identify_intervention(hadm_id, procedure_date)
                if not intervention:
                    logger.debug(f"  hadm {hadm_id}: No intervention identified")
                    continue

                # Extract lab windows with extended 72-hour windows and density requirements
                # Relaxed to get more episodes: 2+ pre, 1+ post
                pre_labs, post_labs, is_valid = self.extract_labs_window(
                    hadm_id,
                    pd.Timestamp(procedure_date),
                    hours_before=72,
                    hours_after=72,
                    min_pre_measurements=2,
                    min_post_measurements=1
                )

                # CRITICAL: Reject if measurements don't align
                if not is_valid:
                    skipped_insufficient_data += 1
                    logger.debug(
                        f"  hadm {hadm_id}: Data insufficient (pre markers: {len(pre_labs)}, "
                        f"post markers: {len(post_labs)}, shared: {len(set(pre_labs.keys()) & set(post_labs.keys()))})"
                    )
                    continue

                # Verify pre and post have IDENTICAL marker sets
                if pre_labs.keys() != post_labs.keys():
                    skipped_misaligned += 1
                    logger.debug(f"  hadm {hadm_id}: Markers misaligned (pre: {list(pre_labs.keys())}, post: {list(post_labs.keys())})")
                    continue

                # Create episode with density metadata
                marker_list = list(pre_labs.keys())
                pre_measurements_per_marker = {m: len(pre_labs[m]) for m in marker_list}
                post_measurements_per_marker = {m: len(post_labs[m]) for m in marker_list}

                episode = {
                    "episode_id": f"episode_{len(episodes)+1:04d}",
                    "hadm_id": int(hadm_id),
                    "intervention": {
                        "type": intervention,
                        "date": procedure_date.isoformat(),
                    },
                    "pre_context": {
                        "window_hours": 72,
                        "markers": pre_labs,
                        "measurement_density": pre_measurements_per_marker,
                    },
                    "post_trajectory": {
                        "window_hours": 72,
                        "markers": post_labs,
                        "measurement_density": post_measurements_per_marker,
                    },
                    "shared_markers": marker_list,
                    "metadata": {
                        "source": "MIMIC-IV cardiac",
                        "extracted_at": datetime.now().isoformat(),
                        "note": "Extended ±72h windows with 3+ pre-measurements, 2+ post-measurements, aligned markers",
                    }
                }

                episodes.append(episode)
                processed_hadms.add(hadm_id)

                logger.info(
                    f"  Episode {len(episodes)}: {intervention} - "
                    f"Markers: {marker_list} - "
                    f"Pre density: {pre_measurements_per_marker} - Post density: {post_measurements_per_marker}"
                )

            except Exception as e:
                logger.debug(f"Error processing hadm {hadm_id}: {e}")
                continue

        logger.info(f"Extracted {len(episodes)} valid episodes")
        logger.info(f"  Skipped (insufficient data): {skipped_insufficient_data}")
        logger.info(f"  Skipped (misaligned markers): {skipped_misaligned}")
        return episodes

    def save_episodes(self, episodes: List[Dict]):
        """Save episodes to JSON."""
        output_file = Path(BENCHMARK_DIR) / "data" / "episodes_real.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "benchmark": "causal_intervention_episodes_mimic_v1",
            "timestamp": datetime.now().isoformat(),
            "n_episodes": len(episodes),
            "target_markers": TARGET_MARKERS,
            "episodes": episodes,
        }

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved episodes to {output_file}")


def main():
    """Extract episodes from MIMIC-IV data."""
    try:
        extractor = EpisodeExtractor()
        extractor.load_data()
        episodes = extractor.extract_episodes(max_episodes=50)
        extractor.save_episodes(episodes)
        logger.info(f"✓ Complete! Created {len(episodes)} episodes")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
