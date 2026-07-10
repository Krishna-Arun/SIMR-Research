"""Benchmark B Evaluator-Optimizer loop: draft -> (evaluate -> refine)*<=3 -> accept/discard.

Samples ICU PROCEDURES (proc_uid) from the pool, each used at most once; rejected-after-3 procedures
are discarded and a new one sampled. Resumable from questions.jsonl. No question-type quota (B is a
single task type).

Concurrency: when generation.concurrency > 1, up to that many questions run in flight via a thread
pool (optimizer/evaluator overlap across GPUs + PubMed I/O overlap). Shared state is lock-guarded so
the run stops at exactly target_n and never reuses a procedure.
"""
from __future__ import annotations

import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from qgen.context_builder import ContextStore
from qgen.dedupe import DedupeState
from qgen.schema import build_record, intent_fingerprint, is_valid_candidate, stem_leaks
from qgen.writer import Writer


class Orchestrator:
    def __init__(self, cfg, store: ContextStore, optimizer, evaluator, dispatcher, writer: Writer):
        self.cfg, self.store = cfg, store
        self.optimizer, self.evaluator, self.dispatcher, self.writer = optimizer, evaluator, dispatcher, writer
        self.max_iters = int(cfg["generation"]["max_iterations"])

    def run_one(self, context: dict):
        import time
        t0 = time.time()
        # Single-shot generation (no evaluator agent) + deterministic leak guard: redraft up to 3x
        # if the stem leaks the trajectory directions. Quality otherwise enforced by the system prompt.
        cand = None
        for attempt in range(1, 4):
            cand = self.optimizer.draft(context)
            ok = is_valid_candidate(cand)
            leaked = stem_leaks(cand, context) if ok else []
            print(f"    draft#{attempt} {time.time()-t0:.0f}s valid={ok} leak={leaked}", flush=True)
            if ok and not leaked:
                return True, cand, {}, attempt
        return False, cand, {}, 0

    def generate(self, target_n: int, diagnosis_frac: float, seed: int, max_attempts: int | None = None):
        records, _used_hadm, fps, _tc = self.writer.load_resume()
        used_proc = {r.get("proc_uid") for r in records if r.get("proc_uid")}
        dd = DedupeState(seed, set(), fps)
        pool = list(self.store.pool)
        max_attempts = max_attempts or (target_n * 60)   # B has a low yield/attempt (intermittent empty drafts)
        concurrency = max(1, int(self.cfg["generation"].get("concurrency", 1)))

        lock = threading.Lock()
        state = {"count": self.writer.count(), "attempts": 0}

        def reserve():
            with lock:
                if state["count"] >= target_n or state["attempts"] >= max_attempts:
                    return None
                puid = self._sample(pool, used_proc, dd)
                if puid is None:
                    print("WARN: procedure pool exhausted before target")
                    return None
                used_proc.add(puid)
                state["attempts"] += 1
                return puid

        def work(puid):
            try:
                context = self.store.build_context(puid)
            except Exception as e:
                print(f"  skip {puid}: context error {e}")
                return
            if not context.get("trajectories"):
                return
            accepted, cand, verdict, n_iter = self.run_one(context)
            if not accepted:
                print(f"  reject {puid} ({context['procedure']['label']})")
                return
            cand["procedure"] = context["procedure"]      # so fingerprint includes the procedure
            fp = intent_fingerprint(cand)
            with lock:
                if state["count"] >= target_n:
                    return
                if fp in dd.fingerprints:
                    print(f"  dup fingerprint {puid}; discard")
                    return
                qid = f"qb_{state['count']:05d}"
                provenance = {"optimizer_model": self.cfg["models"]["optimizer"]["model_id"],
                              "evaluator_model": self.cfg["models"]["evaluator"]["model_id"],
                              "seed": seed, "intent_fingerprint": fp}
                rec = build_record(qid, context, cand, verdict, n_iter, provenance)
                self.writer.append(rec)
                dd.fingerprints.add(fp)
                state["count"] += 1
                print(f"  ACCEPT {qid} {puid} proc={context['procedure']['label']} "
                      f"labs={len(rec['target_labs_detail'])} iters={n_iter} [{state['count']}/{target_n}]")

        self._drive(work, reserve, concurrency, state, target_n)

        n = self.writer.count()
        self.writer.write_manifest(self.cfg, {"trajectory": n}, n, extra={"attempts": state["attempts"]})
        if n >= target_n:
            self.writer.mark_complete()
        return n, {"trajectory": n}

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

    @staticmethod
    def _sample(pool, used, dd: DedupeState):
        for _ in range(500):
            p = pool[int(dd.rng.integers(0, len(pool)))]
            if p not in used:
                return p
        for p in pool:
            if p not in used:
                return p
        return None
