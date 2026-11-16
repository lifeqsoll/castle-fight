BOUNTY = 0.02
def U(name, role, dtype, armor, hp, dmg, cd, rng, spd, cost, spawn, bounty=None, **kw):
    d = dict(name=name, role=role, dtype=dtype, armor=armor, hp=hp, dmg=dmg, cd=cd, rng=rng,
             spd=spd, cost=cost, spawn=spawn)
    d['bounty'] = bounty if bounty is not None else max(1, round(cost*BOUNTY))
    d.update(kw)
    return d

def M(name, dtype, armor, hp, dmg, cd, rng, spd, bounty=0, **kw):
    d = dict(name=name, role='minion', dtype=dtype, armor=armor, hp=hp, dmg=dmg, cd=cd, rng=rng, spd=spd, bounty=bounty)
    d.update(kw); return d

