import stats as S
ROLE=['melee','ranged','summon','ult']

class Bot:
    name='base'
    ult_after=5     # non-ult buildings before saving for ult
    weights=(0.4,0.35,0.25)
    def __init__(s, jitter=0.15): s.jitter=jitter; s.plan=None
    def want_ult(s, me, c, t):
        return c[3]<S.MAX_ULT and sum(c[:3])>=s.ult_after + 3*c[3]
    def pick(s, me, en, t, rng):
        c=me.counts(); tot=sum(c[:3])+1
        best=None;bv=-1e9
        for k in range(3):
            v=s.weights[k]*tot-c[k]+rng.uniform(-s.jitter,s.jitter)*2
            if v>bv: bv=v;best=k
        return best
    def choose(s, me, en, t, rng):
        if len(me.blds)>=S.SLOTS: return None
        c=me.counts()
        if s.plan is None:
            s.plan = 3 if s.want_ult(me,c,t) else s.pick(me,en,t,rng)
        k=s.plan
        if me.gold>=me.defs[k]['cost']:
            s.plan=None; return k
        return None

class Mixed(Bot): name='mixed'

class Rush(Bot):
    name='rush'; weights=(0.55,0.35,0.10); ult_after=9

class Greedy(Bot):
    name='greedy'; ult_after=2; weights=(0.35,0.35,0.30)

class Swarm(Bot):
    name='swarm'; weights=(0.3,0.25,0.45); ult_after=6

class Counter(Bot):
    name='counter'
    def pick(s, me, en, t, rng):
        # enemy armor mix from their buildings (what they will keep spawning) + alive units
        mix={'L':0.0,'M':0.0,'H':0.0,'S':0.0,'R':0.0}
        for b in en.blds:
            d=en.defs[b[0]]; w=d['hp']/d['spawn']
            mix[d['armor']]+=w
            if 'minion' in d:
                m=d['minion']; mix[m['armor']]+=m['hp']/d['every']*0.7
        tot=sum(mix.values()) or 1.0
        c=me.counts(); n=sum(c[:3])+1
        best=None;bv=-1e9
        for k in range(3):
            d=me.defs[k]
            eff=sum(mix[a]/tot*S.MULT[d['dtype']][a] for a in mix) if sum(mix.values())>0 else 1.0
            if 'minion' in d: eff=0.5*eff+0.5*sum(mix[a]/tot*S.MULT[d['minion']['dtype']][a] for a in mix) if sum(mix.values())>0 else 1.0
            share=c[k]/n
            v=eff - 1.2*max(0,share-0.5) + (0.4 if k==0 and c[0]<max(1,n*0.3) else 0) + rng.uniform(-s.jitter,s.jitter)
            if v>bv: bv=v;best=k
        return best

class Mono(Bot):
    def __init__(s,k,jitter=0): super().__init__(jitter); s.k=k; s.name=f'mono{k}'
    def want_ult(s,me,c,t): return s.k==3
    def pick(s,me,en,t,rng): return s.k
    def choose(s, me, en, t, rng):
        if s.k==3 and me.counts()[3]>=S.MAX_ULT: s.done=True; return None
        return super().choose(me,en,t,rng)

POOL=[Mixed,Counter,Rush,Greedy,Swarm]
