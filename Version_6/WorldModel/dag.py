#!/usr/bin/env python3
"""
The SIMR causal DAG -- created formally (nodes, edges, adjustment sets), and the
multi-treatment confounder analysis (#2 extended to all 6 treatments).

DAG structure (single decision point):
    every CONFOUNDER (baseline state)  ->  every TREATMENT   (indication)
    every CONFOUNDER                   ->  OUTCOME           (prognosis)
    every TREATMENT                    ->  OUTCOME           (effect)   <-- what we want
Backdoor rule => to estimate treatment_k -> outcome, adjust for the CONFOUNDERS
(baseline, pre-treatment). Never adjust for another treatment's downstream state
(that's a mediator). For the LONGITUDINAL multi-treatment case the confounders are
time-varying (treatment_t -> state_{t+1} -> treatment_{t+1}) -> requires g-methods.

Deliverables: prints the DAG + per-treatment adjustment set, and fits a propensity
model per treatment to show (a) how strong the confounding is and (b) which baseline
factors drive each treatment decision (= the confounders you must adjust for).
"""
import json, os
import numpy as np
import networkx as nx
import wm_data as D
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
CONF_LABS = D.TARGET_LABS
COMORB = D.COMORBID
TREATMENTS = ["diuretic", "vasodilator", "inotrope", "vasopressor", "dialysis", "ventilation"]


def build_dag():
    g = nx.DiGraph()
    conf = [f"base_{l.split()[0]}" for l in CONF_LABS] + COMORB + ["age", "sex"]
    for c in conf:
        g.add_node(c, kind="confounder")
        for t in TREATMENTS:
            g.add_edge(c, t)               # indication
        g.add_edge(c, "OUTCOME")           # prognosis
    for t in TREATMENTS:
        g.add_node(t, kind="treatment")
        g.add_edge(t, "OUTCOME")           # effect (the arrow we want)
    g.add_node("OUTCOME", kind="outcome")
    return g, conf


def confounders(e, scaler):
    z = []
    for j, l in enumerate(CONF_LABS):
        m, s = scaler["lab"][l]; v = e["bval"][j]
        z.append(((v - m) / s) if v is not None else 0.0)
    return np.array(z + list(D.static_vec(e, scaler)), np.float32)


def main():
    g, conf = build_dag()
    print(f"DAG created: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    print(f"  confounders ({len(conf)}): {', '.join(conf)}")
    print(f"  treatments  ({len(TREATMENTS)}): {', '.join(TREATMENTS)}")
    print(f"  outcome     : post labs")
    # backdoor adjustment set for any single treatment = the confounders (parents of T
    # that also affect OUTCOME); mediators/colliders (none here at one time point) excluded.
    print(f"\n  adjustment set for treatment_k -> OUTCOME (backdoor): ALL {len(conf)} confounders")
    print("  (longitudinal/multi-treatment: confounders become TIME-VARYING -> g-methods)")

    # ---- #2 per-treatment: propensity + confounding strength + drivers ----
    tr, va, te, ch, ci, scaler, meta = D.build(seed=20260714)
    allx = tr + va + te
    C = np.stack([confounders(e, scaler) for e in allx])
    act = json.load(open(os.path.join(HERE, "action_space.json")))
    tidx = {t: i for i, t in enumerate(TREATMENTS)}
    # multi-hot label per patient (from action_space, joined by hadm)
    have = [e for e in allx if e["hadm"] in act]
    Ch = np.stack([confounders(e, scaler) for e in have])
    Y = np.array([act[e["hadm"]] for e in have])
    print(f"\nper-treatment confounder analysis (n={len(have)} patients w/ baseline + action):")
    print(f"  {'treatment':12s} {'n_treated':>9} {'propensity AUC':>15}  top baseline drivers")
    for t in TREATMENTS:
        y = Y[:, tidx[t]]
        if y.sum() < 20 or y.sum() > len(y) - 20:
            print(f"  {t:12s} {int(y.sum()):9d} {'--':>15}  (too few/many to model here)")
            continue
        m = LogisticRegression(max_iter=1000).fit(Ch, y)
        auc = roc_auc_score(y, m.predict_proba(Ch)[:, 1])
        drivers = sorted(zip(conf, m.coef_[0]), key=lambda x: -abs(x[1]))[:4]
        ds = ", ".join(f"{n}{'+' if c > 0 else ''}{c:.2f}" for n, c in drivers)
        print(f"  {t:12s} {int(y.sum()):9d} {auc:15.3f}  {ds}")
    print("\n(AUC = how confounded that treatment is; drivers = the confounders to adjust for it.)")
    print("Each treatment has its OWN adjustment set -> that's #2 for multiple treatments.")


if __name__ == "__main__":
    main()
