"""Evaluator-Optimizer control loop: draft -> (evaluate -> refine)*<=3 -> accept/discard.

Reaches exactly target_n accepted questions with a ~50/50 diagnosis/intervention quota. Each
admission is used at most once; rejected-after-3 admissions are discarded and a new patient sampled.
Resumable: state is reconstructed from questions.jsonl.

Concurrency: when generation.concurrency > 1, up to that many questions are in flight at once via a
thread pool. The optimizer (one GPU) and evaluator (another GPU) overlap across questions, and PubMed
I/O overlaps too. All shared state (dedupe, quota, writer, counters) is guarded by one lock so the
run still stops at exactly target_n with the 50/50 split and no reused patient.
"""
from __future__ import annotations

import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from qgen.answer_key import build as build_answer_key
from qgen.context_builder import ContextStore
from qgen.dedupe import DedupeState
from qgen.schema import build_record, intent_fingerprint, is_valid_candidate, stem_leaks
from qgen.writer import Writer


class Orchestrator:
    def __init__(self, cfg, store: ContextStore, optimizer, evaluator, dispatcher, writer: Writer):
        self.cfg = cfg
        self.store = store
        self.optimizer = optimizer
        self.evaluator = evaluator
        self.dispatcher = dispatcher
        self.writer = writer
        self.max_iters = int(cfg["generation"]["max_iterations"])

    # ── one patient ──────────────────────────────────────────────────────────
    def run_one(self, context: dict, qtype: str):
        import time
        t0 = time.time()
        # Single-shot generation (no evaluator agent) + deterministic leak guard: redraft up to 3x
        # if the stem leaks lab names / diagnosis. Quality otherwise enforced by the system prompt.
        cand = None
        for attempt in range(1, 4):
            cand = self.optimizer.draft(context, qtype)
            ok = is_valid_candidate(cand)
            leaked = stem_leaks(cand, context) if ok else []
            print(f"    draft#{attempt} {time.time()-t0:.0f}s valid={ok} leak={leaked}", flush=True)
            if ok and not leaked:
                return True, cand, {}, attempt
        return False, cand, {}, 0

    # ── full run ─────────────────────────────────────────────────────────────
    def generate(self, target_n: int, diagnosis_frac: float, seed: int, max_attempts: int | None = None):
        records, used_hadm, fps, type_counts = self.writer.load_resume()
        dd = DedupeState(seed, used_hadm, fps)
        quota = {"diagnosis": round(target_n * diagnosis_frac),
                 "intervention": target_n - round(target_n * diagnosis_frac)}

        all_hadm = list(self.store.pool)   # only admissions with materialized slices
        max_attempts = max_attempts or (target_n * 20)
        concurrency = max(1, int(self.cfg["generation"].get("concurrency", 1)))

        lock = threading.Lock()
        state = {"count": self.writer.count(), "attempts": 0}

        # reserve the next job under the lock: pick type + patient, mark used. None => stop starting.
        def reserve():
            with lock:
                if state["count"] >= target_n or state["attempts"] >= max_attempts:
                    return None
                qtype = self._pick_type(quota, type_counts, dd)
                if qtype is None:
                    return None
                hadm = self._sample(all_hadm, dd)
                if hadm is None:
                    print("WARN: cohort exhausted before reaching target")
                    return None
                dd.mark_used(hadm)
                state["attempts"] += 1
                return hadm, qtype

        # the heavy per-question work (LLM + PubMed) — runs OUTSIDE the lock
        def work(job):
            hadm, qtype = job
            try:
                context = self.store.build_context(hadm)
            except Exception as e:
                print(f"  skip {hadm}: context error {e}")
                return
            context["assigned_type"] = qtype
            accepted, cand, verdict, n_iter = self.run_one(context, qtype)
            if not accepted:
                fails = {d: f"auto={v.get('auto')},model={v.get('model')}"
                         for d, v in (verdict.get("dims") or {}).items() if not v.get("pass")}
                print(f"  reject hadm={hadm} type={qtype} FAILS={fails}")
                print(f"    feedback: {str(verdict.get('actionable_feedback',''))[:300]}")
                return
            final = build_answer_key(context, cand, self.dispatcher)
            with lock:
                if state["count"] >= target_n:
                    return
                if dd.is_dup(cand):
                    print(f"  dup fingerprint hadm={hadm}; discard")
                    return
                qid = f"qa_{state['count']:05d}"
                provenance = {
                    "optimizer_model": self.cfg["models"]["optimizer"]["model_id"],
                    "evaluator_model": self.cfg["models"]["evaluator"]["model_id"],
                    "seed": seed,
                    "intent_fingerprint": intent_fingerprint(cand),
                }
                rec = build_record(qid, context, final, verdict, n_iter, provenance)
                self.writer.append(rec)
                dd.register(hadm, cand)
                type_counts[qtype] += 1
                state["count"] += 1
                print(f"  ACCEPT {qid} hadm={hadm} type={qtype} iters={n_iter} "
                      f"[{type_counts['diagnosis']}D/{type_counts['intervention']}I] "
                      f"[{state['count']}/{target_n}]")

        self._drive(work, reserve, concurrency, state, target_n)

        n = self.writer.count()
        self.writer.write_manifest(self.cfg, type_counts, n, extra={"attempts": state["attempts"]})
        if n >= target_n:
            self.writer.mark_complete()
        return n, type_counts

    # ── concurrency driver (shared shape across A/B/C) ─────────────────────────
    @staticmethod
    def _drive(work, reserve, concurrency, state, target_n):
        if concurrency <= 1:
            while True:
                job = reserve()
                if job is None:
                    break
                work(job)
            return
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = set()

            def fill():
                while len(futures) < concurrency and state["count"] < target_n:
                    job = reserve()
                    if job is None:
                        break
                    futures.add(ex.submit(work, job))

            fill()
            while futures:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for f in done:
                    try:
                        f.result()
                    except Exception as e:
                        print(f"  worker error: {e}")
                fill()

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _pick_type(quota, type_counts, dd: DedupeState):
        remaining = {t: quota[t] - type_counts.get(t, 0) for t in quota}
        choices = [t for t, r in remaining.items() if r > 0]
        if not choices:
            return None
        # bias toward the type with more remaining for a smooth ~50/50
        return max(choices, key=lambda t: remaining[t]) if len(choices) > 1 and remaining[choices[0]] != remaining[choices[-1]] \
            else dd.rng.choice(choices)

    @staticmethod
    def _sample(all_hadm, dd: DedupeState):
        for _ in range(200):
            h = int(dd.rng.choice(all_hadm))
            if h not in dd.used_hadm:
                return h
        # fallback: linear scan
        for h in all_hadm:
            if int(h) not in dd.used_hadm:
                return int(h)
        return None
