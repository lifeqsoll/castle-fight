"""Матрица винрейтов 6×6 как в balance_sim/evalb.py."""

from __future__ import annotations

import statistics as st
import sys
from multiprocessing import Pool

from castlefight.ai.bots import POOL, MonoBot
from castlefight.core.game import simulate
from castlefight.data.factions import FACTION_NAMES

CL = list(FACTION_NAMES)


def _job(args):
    a, b, ba, bb, mode, seed = args
    ba_cls = POOL[ba] if isinstance(ba, int) else ba
    bb_cls = POOL[bb] if isinstance(bb, int) else bb

    def mk(x):
        if isinstance(x, type):
            return x()
        return MonoBot(x)

    r = simulate(a, b, mk(ba_cls), mk(bb_cls), mode=mode, seed=seed)
    return (a, b, r["winner"], r["t"], r["timeout"], r["fu"])


def matrix(n: int = 6, mode: str = "normal", procs: int = 8, seed0: int = 0):
    jobs = []
    s = seed0
    for a in CL:
        for b in CL:
            if a == b:
                continue
            for i in range(n):
                for ba in range(len(POOL)):
                    s += 1
                    jobs.append((a, b, ba, (ba + i) % len(POOL), mode, s))
    with Pool(procs) as pool:
        res = pool.map(_job, jobs, chunksize=8)
    wins = {(a, b): [0, 0] for a in CL for b in CL}
    times = []
    timeouts = 0
    first_ults = []
    for a, b, w, t, tmo, fu in res:
        wins[(a, b)][0] += w == 0
        wins[(a, b)][1] += 1
        wins[(b, a)][0] += w == 1
        wins[(b, a)][1] += 1
        times.append(t)
        timeouts += tmo
        first_ults.extend(x for x in fu if x is not None)
    return wins, times, timeouts, first_ults, len(res)


def report(wins, times, timeouts, first_ults, n_games):
    print("%-12s" % "" + "".join("%7s" % c[:6] for c in CL) + "   ИТОГ")
    for a in CL:
        row = "%-12s" % a[:12]
        ws = ns = 0
        for b in CL:
            if a == b:
                row += "%7s" % "-"
                continue
            w, n = wins[(a, b)]
            ws += w
            ns += n
            row += "%7.0f" % (100 * w / n)
        print(row + "%7.1f" % (100 * ws / ns))
    times = sorted(times)
    n = n_games
    fu_med = st.median(first_ults) / 60 if first_ults else -1
    print(
        "games %d mean %.1f min, median %.1f, p10 %.1f p90 %.1f, timeouts %d, first ult median %.1f min"
        % (
            n,
            st.mean(times) / 60,
            times[len(times) // 2] / 60,
            times[n // 10] / 60,
            times[n * 9 // 10] / 60,
            timeouts,
            fu_med,
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    report(*matrix(n, mode))
