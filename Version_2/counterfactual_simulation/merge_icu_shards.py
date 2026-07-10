"""merge_icu_shards.py — concatenate the 4 shard encodings into one data_icu/encoded_states_clmbr.pkl.
Also merges the shard trajectories back into data_icu/trajectories.pkl (downstream reads it)."""
import pickle
from pathlib import Path

OUT = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/data_icu")
NSHARD = 4


def main():
    enc, traj = [], []
    for k in range(NSHARD):
        ep = OUT / f"shard{k}/encoded_states_clmbr.pkl"
        tp = OUT / f"shard{k}/trajectories.pkl"
        assert ep.exists(), f"missing {ep} — shard {k} encode did not finish"
        e = pickle.load(open(ep, "rb")); enc += e
        traj += pickle.load(open(tp, "rb"))
        print(f"shard{k}: {len(e)} encoded patients")
    pickle.dump(enc, open(OUT / "encoded_states_clmbr.pkl", "wb"))
    pickle.dump(traj, open(OUT / "trajectories.pkl", "wb"))
    tp = sum(x["s"].shape[0] for x in enc)
    print(f"merged: {len(enc)} patients, {tp:,} timepoints -> data_icu/encoded_states_clmbr.pkl")


if __name__ == "__main__":
    main()
