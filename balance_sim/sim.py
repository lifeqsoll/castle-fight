import random, math
import stats as S

class Unit:
    __slots__=('side','x','hp','maxhp','d','cd','st','owner','nmin','dir','raised','m','made')
    def __init__(s, side, x, d, owner=None, m=1.0):
        s.m=m; s.made=0; s.side=side; s.x=x; s.d=d; s.hp=d['hp']*m; s.maxhp=s.hp; s.cd=0.0
        s.st=d.get('every',0); s.owner=owner; s.nmin=0; s.dir=1 if side==0 else -1; s.raised=0

class Side:
    def __init__(s, cls, bot, econ):
        s.cls=cls; s.defs=S.CLASSES[cls]; s.bot=bot; s.gold=econ['start']
        s.blds=[]   # [defidx, timer]
        s.units=[]; s.chp=econ.get('castle_hp',S.CASTLE['hp']); s.ccd=0.0
        s.lvl=0; s.earned=0; s.kills=0; s.ultspawned=0; s.first_ult=None
    def counts(s):
        c=[0,0,0,0]
        for b in s.blds: c[b[0]]+=1
        return c

def income_rate(t, e):
    return min(e['cap'], e['base']+e['inc']*int(t//e['step']))

def simulate(clsA, clsB, botA, botB, mode='normal', seed=0, dt=0.2, tmax=45*60, log=False):
    rng=random.Random(seed); e=S.ECON[mode]
    sides=[Side(clsA,botA,e), Side(clsB,botB,e)]
    L=S.LANE; cx=[0.0, float(L)]
    C=S.CASTLE; MULT=S.MULT
    t=0.0; decide=0.0
    while t<tmax:
        # economy
        r=income_rate(t,e)/60.0*dt
        for sd in sides: sd.gold+=r
        # bots
        if t>=decide:
            decide+=1.0
            for i,sd in enumerate(sides):
                if (len(sd.blds)>=S.SLOTS or getattr(sd.bot,'done',False)) and sd.lvl<S.UPG_MAX:
                    uc=S.UPG_COST[sd.lvl]
                    if sd.gold>=uc: sd.gold-=uc; sd.lvl+=1
                    continue
                for _ in range(3):
                    k=sd.bot.choose(sd, sides[1-i], t, rng)
                    if k is None: break
                    dd=sd.defs[k]
                    if sd.gold>=dd['cost'] and len(sd.blds)<S.SLOTS and not (dd['role']=='ult' and sum(1 for b in sd.blds if b[0]==3)>=S.MAX_ULT):
                        sd.gold-=dd['cost']; sd.blds.append([k, dd['spawn']*0.5*rng.uniform(0.8,1.2)])
                    else: break
        # spawns
        for i,sd in enumerate(sides):
            for b in sd.blds:
                b[1]-=dt
                if b[1]<=0:
                    dd=sd.defs[b[0]]
                    b[1]+=dd['spawn']*rng.uniform(0.95,1.05)
                    sd.units.append(Unit(i, cx[i]+(30 if i==0 else -30), dd, m=1+S.UPG_BONUS*sd.lvl))
                    if dd['role']=='ult':
                        sd.ultspawned+=1
                        if sd.first_ult is None: sd.first_ult=t
        # order enemies by frontness
        fronts=[]
        for i,sd in enumerate(sides):
            us=sd.units
            # front of side i: for side0 max x, side1 min x
            fronts.append(sorted(us, key=lambda u: -u.x) if i==0 else sorted(us, key=lambda u: u.x))
        newunits=[[],[]]
        for i,sd in enumerate(sides):
            en=sides[1-i]; ef=fronts[1-i]; p=0; ne=len(ef)
            ecx=cx[1-i]
            for u in sd.units:
                if u.hp<=0: continue
                d=u.d
                # abilities
                if 'regen' in d and u.hp<u.maxhp: u.hp=min(u.maxhp,u.hp+d['regen']*dt)
                if 'aura_heal' in d:
                    h=d['aura_heal']*dt
                    for a in sd.units:
                        if a.hp>0 and a.hp<a.maxhp and abs(a.x-u.x)<=150: a.hp=min(a.maxhp,a.hp+h)
                if 'minion' in d:
                    u.st-=dt
                    if u.st<=0:
                        u.st+=d['every']
                        if u.nmin<d['maxmin'] and u.made<d['total']:
                            u.nmin+=1; u.made+=1; newunits[i].append(Unit(i,u.x,d['minion'],owner=u,m=u.m))
                while p<ne and ef[p].hp<=0: p+=1
                tgt=ef[p] if p<ne else None
                rngu=d['rng']
                if u.cd>0: u.cd-=dt
                if tgt is not None and abs(tgt.x-u.x)<=rngu:
                    if u.cd<=0:
                        u.cd+=d['cd']
                        dmg=d['dmg']*u.m*MULT[d['dtype']][tgt.d['armor']]*rng.uniform(0.9,1.1)
                        tgt.hp-=dmg
                        if tgt.hp<=0 and d.get('raise_dead') and u.raised<6:
                            u.raised+=1; newunits[i].append(Unit(i,tgt.x,S.NECRO_RAISE,m=u.m))
                        sp=d.get('splash') or d.get('cleave')
                        if sp:
                            for o in ef:
                                if o is not tgt and o.hp>0 and abs(o.x-tgt.x)<=50:
                                    o.hp-=d['dmg']*u.m*sp*MULT[d['dtype']][o.d['armor']]
                elif abs(ecx-u.x)<=rngu+20:
                    if u.cd<=0:
                        u.cd+=d['cd']
                        en.chp-=d['dmg']*u.m*MULT[d['dtype']]['C']*d.get('siege',1.0)
                else:
                    nx=u.x+u.dir*d['spd']*dt
                    if tgt is not None:
                        # don't walk past enemy front
                        if u.dir>0: nx=min(nx, tgt.x-min(rngu,25)*0.5)
                        else: nx=max(nx, tgt.x+min(rngu,25)*0.5)
                    u.x=nx
            # castle shoots (sudden death: weaker after SD minute)
            sdm=max(S.SD_MIN_MULT, 1-S.SD_RATE*max(0.0,(t-e['sd']*60)/60))
            sd.ccd-=dt
            if sd.ccd<=0:
                while p<ne and ef[p].hp<=0: p+=1
                tgt=ef[p] if p<ne else None
                hit=0; q=p
                while q<ne and hit<C['shots']:
                    o=ef[q]; q+=1
                    if o.hp<=0: continue
                    if abs(o.x-cx[i])>C['rng']: break
                    o.hp-=C['dmg']*sdm; hit+=1
                if hit: sd.ccd=C['cd']
        pass
        # cleanup
        for i,sd in enumerate(sides):
            alive=[]
            en=sides[1-i]
            for u in sd.units:
                if u.hp>0: alive.append(u)
                else:
                    en.gold+=u.d['bounty']; en.earned+=u.d['bounty']; en.kills+=1
                    if u.owner is not None: u.owner.nmin-=1
            sd.units=alive+newunits[i]
        t+=dt
        if sides[0].chp<=0 or sides[1].chp<=0: break
    a,b=sides
    if a.chp<=0 and b.chp<=0: w=rng.randint(0,1)
    elif b.chp<=0: w=0
    elif a.chp<=0: w=1
    else: w=0 if a.chp>b.chp else 1
    return dict(winner=w, t=t, timeout=(a.chp>0 and b.chp>0), chp=(a.chp,b.chp), fu=(a.first_ult,b.first_ult),
                earned=(a.earned,b.earned), lvl=(a.lvl,b.lvl), blds=(a.counts(),b.counts()))
