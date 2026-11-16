Castle Fight balance sim (1 lane).
stats.py      - damage table, castle, economy, slots, upgrades, sudden death
classes.py    - all 24 units + summons (final tuned numbers)
sim.py        - simulation (tick 0.2s)
bots.py       - bots: mixed, counter, rush, greedy(ult), swarm, mono-spam
evalb.py      - 6x6 matrix:   python3 evalb.py normal 10 | python3 evalb.py turbo 6
mono.py       - mono-spam test: python3 mono.py normal 2
tune2.py/bake2.py - auto-tuner (per class/role power factors) and baker into classes.py
final_*.txt   - final verification outputs
