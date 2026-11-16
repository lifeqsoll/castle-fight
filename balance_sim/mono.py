# each class: mono-spam of each building (0..2, 3=ults only then nothing) vs every other class using normal bots
import sys
from multiprocessing import Pool
import evalb, bots, stats as S
CL=list(S.CLASSES)
mode=sys.argv[1] if len(sys.argv)>1 else 'normal'
n=int(sys.argv[2]) if len(sys.argv)>2 else 4
def job(a):
    c,k,o,ba,side,seed=a
    import sim
    m=bots.Mono(k); e=bots.POOL[ba]()
    r=sim.simulate(c,o,m,e,mode,seed) if side==0 else sim.simulate(o,c,e,m,mode,seed)
    return c,k,(r['winner']==side)
jobs=[]; s=777
for c in CL:
    for k in range(4):
        for o in CL:
            if o==c: continue
            for ba in range(len(bots.POOL)):
                for side in (0,1):
                    for i in range(n): s+=1; jobs.append((c,k,o,ba,side,s))
with Pool(8) as p: res=p.map(job,jobs,chunksize=16)
from collections import defaultdict
W=defaultdict(lambda:[0,0])
for c,k,w in res: W[(c,k)][0]+=w; W[(c,k)][1]+=1
print('mono-spam winrate vs normal bots (%):')
for c in CL:
    print('%-12s'%c, '  '.join('%s %3.0f'%(S.CLASSES[c][k]['name'][:10],100*W[(c,k)][0]/W[(c,k)][1]) for k in range(4)))
