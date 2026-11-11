import random, itertools, statistics as st, sys
from multiprocessing import Pool
import sim, bots, stats as S
CL=list(S.CLASSES)

def job(args):
    a,b,ba,bb,mode,seed=args
    BA=bots.POOL[ba] if isinstance(ba,int) else ba
    BB=bots.POOL[bb] if isinstance(bb,int) else bb
    mk=lambda X: X() if isinstance(X,type) else bots.Mono(X)
    r=sim.simulate(a,b,mk(BA),mk(BB),mode=mode,seed=seed)
    return (a,b,r['winner'],r['t'],r['timeout'],r['fu'])

def matrix(n=6, mode='normal', procs=8, seed0=0):
    jobs=[]; s=seed0
    for a in CL:
        for b in CL:
            if a==b: continue
            for i in range(n):
                for ba in range(len(bots.POOL)):
                    s+=1; jobs.append((a,b,ba,(ba+i)%len(bots.POOL),mode,s))
    with Pool(procs) as p: res=p.map(job,jobs,chunksize=8)
    W={(a,b):[0,0] for a in CL for b in CL}
    T=[];to=0;fu=[]
    for a,b,w,t,tmo,f in res:
        W[(a,b)][0]+= (w==0); W[(a,b)][1]+=1
        W[(b,a)][0]+= (w==1); W[(b,a)][1]+=1
        T.append(t); to+=tmo; fu+= [x for x in f if x is not None]
    return W,T,to,fu,len(res)

def report(W,T,to,fu,N):
    print('%-12s'%''+''.join('%7s'%c[:6] for c in CL)+'   ИТОГ')
    for a in CL:
        row='%-12s'%a[:12]; ws=0;ns=0
        for b in CL:
            if a==b: row+='%7s'%'-'; continue
            w,n=W[(a,b)]; ws+=w; ns+=n; row+='%7.0f'%(100*w/n)
        print(row+'%7.1f'%(100*ws/ns))
    T=sorted(T)
    print('games %d mean %.1f min, median %.1f, p10 %.1f p90 %.1f, timeouts %d, first ult median %.1f min'%(N,st.mean(T)/60,T[len(T)//2]/60,T[N//10]/60,T[N*9//10]/60,to,(st.median(fu)/60 if fu else -1)))

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'normal'
    n=int(sys.argv[2]) if len(sys.argv)>2 else 4
    report(*matrix(n,mode))
