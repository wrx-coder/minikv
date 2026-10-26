"""Deterministic, strategy-independent token traces. W4 uses a fixed lifetime schedule;
completed/preempted are evaluated from replay results, never fed back into traces."""
import random,math

def generate(kind,seed,steps=450,pressure=0.8):
    r=random.Random(seed); ops=[]; live=[]; serial=0
    if kind=='W0':return [('ALLOC','A',10),('ALLOC','B',6),('ALLOC','C',14),('FREE','B',0),('ALLOC','D',8),('APPEND','A',5),('FREE','C',0),('ALLOC','E',12)]
    if kind=='W6':return [('ALLOC',f'R{i}',4) for i in range(32)]+[('FREE',f'R{i}',0) for i in range(0,32,2)]+[('ALLOC','BIG',48)]
    if kind in ('W4','W5'):
        # precomputed arrivals and departures: failed allocations simply cause subsequent APPEND/FREE to fail.
        future=[]
        for t in range(steps):
            for id,death in list(future):
                if death==t:ops.append(('FREE',id,0));future.remove((id,death))
            for id,death in future:ops.append(('APPEND',id,1))
            if r.random()<min(0.98,pressure*0.68):
                id=f'R{serial}';serial+=1
                prompt=max(1,min(350,round(r.lognormvariate(math.log(32),0.85))))
                lifetime=min(100,max(3,round(r.expovariate(1/26))))
                ops.append(('ALLOC',id,prompt));future.append((id,t+lifetime))
        for id,_ in future:ops.append(('FREE',id,0))
        return ops
    for t in range(steps):
        if live and r.random()<(0.48 if kind=='W3' else 0.27):
            id=r.choice(live);live.remove(id);ops.append(('FREE',id,0))
        else:
            id=f'R{serial}';serial+=1;live.append(id)
            length= r.randint(8,64) if kind=='W1' else min(450,max(1,round(r.lognormvariate(math.log(32),1.1 if kind=='W2' else 1.5))))
            ops.append(('ALLOC',id,length))
        if live and t%7==0:ops.append(('APPEND',r.choice(live),r.randint(1,8)))
    return ops

def save(path,kind,seed,ops):
    with open(path,'w',newline='\n',encoding='ascii') as f:
        f.write(f'# workload={kind} seed={seed} operations={len(ops)}\n')
        for op,id,count in ops:f.write(f'{op} {id}'+(f' {count}' if op!='FREE' else '')+'\n')
