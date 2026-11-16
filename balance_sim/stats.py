# All balance numbers live here.
# armor: L=лёгкая M=средняя H=тяжёлая S=рой ; dmg: slash/pierce/magic
MULT = {
    'slash':  {'L':1.2,'M':1.0,'H':0.85,'S':1.3,'C':0.25,'R':0.8},
    'pierce': {'L':1.25,'M':1.0,'H':0.8,'S':0.85,'C':0.25,'R':1.0},
    'magic':  {'L':1.05,'M':1.1,'H':1.2,'S':0.85,'C':0.25,'R':1.1},
    'castle': {'L':1.0,'M':1.0,'H':1.0,'S':1.0,'C':1.0,'R':1.0},
}
LANE = 2000
BOUNTY = 0.02
CASTLE = dict(hp=6000, dmg=200, cd=0.35, rng=300, shots=1, armor='C')
SLOTS = 12
UPG_BONUS = 0.1
UPG_MAX = 5
SD_RATE = 0.1
SD_MIN_MULT = 0.2
UPG_COST = [100,150,200,250,300]
MAX_ULT = 2

from stats_helpers import U, M
from classes import CLASSES
ECON = {
 'normal': dict(start=60, base=15, inc=5, step=60, cap=55, sd=20, castle_hp=15000),
 'turbo':  dict(start=80, base=30, inc=10, step=60, cap=70, sd=10, castle_hp=6000),
}
NECRO_RAISE = M('Поднятый','slash','S',60,10,1.0,25,70)
