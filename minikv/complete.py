"""Supplementary validation and experiments; invoked by run_all.py.
Feedback traces are decided by independently tested Python model then fully replayed
through actual C++ harness, checking every success bit (not simulated C++ results).
"""
import csv,io,json,math,random,subprocess,sys
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'workloads')]
from ref import Model,execute
from gen import save

def table(df,name):
    df.to_csv(ROOT/f'results/tables/{name}.csv',index=False)
    (ROOT/f'results/tables/{name}.md').write_text(df.round(5).to_markdown(index=False),encoding='utf-8')
def fig(name):
    plt.tight_layout()
    for ext in ['png','pdf']:plt.savefig(ROOT/f'results/figs/{name}.{ext}',dpi=300)
    plt.close()
def replay(kind,n,s,ops,tag,expected=None):
    path=ROOT/f'workloads/{tag}.trace';save(path,tag,0,ops)
    text=subprocess.check_output([str(ROOT/'harness.exe'),kind,str(n),str(s),str(path)],text=True)
    df=pd.read_csv(io.StringIO(text))
    if expected is not None:assert df.ok.tolist()==expected,tag
    df.to_csv(ROOT/f'results/raw/{tag}.csv',index=False)
    return df

def validations():
    import run_all
    # Preserve official generator body, stripping only its surrounding comment.
    import re
    generator=ROOT/'tests/gen.cpp'
    if not generator.exists():
        raise FileNotFoundError('Missing archived official generator: tests/gen.cpp')
    gcc='C:/tools/msys64/ucrt64/bin/g++.exe'
    import os
    env=os.environ.copy();env['PATH']=str(Path(gcc).parent)+os.pathsep+env['PATH']
    subprocess.run([gcc,'-std=c++17','-O2','-static',str(ROOT/'tests/gen.cpp'),'-o',str(ROOT/'gen.exe')],check=True,env=env)
    folder=ROOT/'tests/official_inputs';folder.mkdir(exist_ok=True)
    for seed in range(2000):
        path=folder/f'{seed:04d}.in'
        # Official generator uses random_device: preserve complete inputs for reproducibility.
        if not path.exists():path.write_bytes(subprocess.check_output([str(ROOT/'gen.exe')]))
        data=path.read_text(encoding='ascii')
        for kind in ['contig','paged']:assert run_all.call(kind,data)==execute(data,kind),(kind,path)
        if seed%500==0:print('official gen validated',seed,flush=True)
    # Actual 131-wrap-then-mod collision search, rather than anagram assumption.
    def h(x):
        a=0
        for c in x.encode():a=(a*131+c)&0xffffffff
        return a%4093
    buckets={};ids=None
    for i in range(100000):
        id=f'C{i}';bucket=buckets.setdefault(h(id),[]);bucket.append(id)
        if len(bucket)==4:ids=bucket;break
    cases=[(8,4,['ALLOC A 3','APPEND A 1','APPEND A 1','ALLOC B 4','APPEND A 5']),
           (4,4,['ALLOC A 12','ALLOC B 4','APPEND B 1','FREE B','APPEND A 5']),
           (6,4,['ALLOC X 4','ALLOC A 4','ALLOC B 4','FREE X','APPEND A 4']),
           (20,100000,['ALLOC A 1000000','APPEND A 1000000','APPEND A 1']),
           (12,4,[*(f'ALLOC {id} 1' for id in ids),f'FREE {ids[3]}',f'FREE {ids[1]}',f'FREE {ids[0]}',f'LOOKUP {ids[2]}',f'ALLOC {ids[0]} 1','ALLOC A 0','APPEND Z -1','FREE Z'])]
    for j,(n,s,ops) in enumerate(cases):
        # state inspected after EVERY mutation, including failures
        checked=[]
        for op in ops:
            checked.append(op);checked.append('MEMORY')
            for id in ['A','B','X',*ids]:checked.append('REQUEST '+id)
        data=run_all.oj(n,s,checked);(ROOT/f'tests/edge_{j}.in').write_text(data,encoding='ascii')
        for kind in ['contig','paged']:assert run_all.call(kind,data)==execute(data,kind)
    (ROOT/'tests/supplementary.json').write_text(json.dumps({'official_generator_cases_per_strategy':2000,'explicit_edge_cases_per_strategy':len(cases),'actual_collision_bucket':h(ids[0]),'collision_ids':ids},indent=2))

def arrivals(seed,steps,pressure):
    # Prompt median 32, capped lognormal. Fixed output 40 tokens for exact demand calibration.
    r=random.Random(seed);sigma=.8
    # Integrate discrete clipped prompt distribution numerically with a fixed independent seed.
    er=random.Random(8841);mean_prompt=np.mean([min(350,max(1,round(er.lognormvariate(math.log(32),sigma)))) for _ in range(50000)])
    # Sum of expected token occupancy over lifetime: 40*P+0+...+39.
    demand=40*mean_prompt+40*39/2
    rate=pressure*4096/demand
    events=[];serial=0
    nr=np.random.default_rng(seed+50000)
    for t in range(steps):
        for _ in range(int(nr.poisson(rate))):
            events.append((t,f'Q{serial}',min(350,max(1,round(r.lognormvariate(math.log(32),sigma)))),40));serial+=1
    return events,rate,float(mean_prompt)

def feedback(events,kind,s,steps,chunk,policy):
    m=Model(4096//s,s,kind);ops=[];bits=[];live={};completed=rejected=preempted=0;peak=0;tokens=[];perstep=[]
    def do(op,id,count=0):
        result=m.run(f'{op} {id}'+(f' {count}' if op!='FREE' else ''));ops.append((op,id,count));bits.append(int(result=='OK'));return result=='OK'
    at={}
    for t,id,p,l in events:at.setdefault(t,[]).append((id,p,l))
    # Arrival stream stops at steps; drain afterwards so all accepted requests reach an outcome.
    for t in range(steps+240):
        for id,state in list(live.items()):
            amount=min(chunk,state[0])
            if do('APPEND',id,amount):
                state[0]-=amount;state[1]=0
                if state[0]==0:do('FREE',id);del live[id];completed+=1
            else:
                state[1]+=1
                if policy=='preempt' or state[1]>=5:do('FREE',id);del live[id];preempted+=1
        for id,p,l in at.get(t,[]):
            if do('ALLOC',id,p):live[id]=[l,0]
            else:rejected+=1
        peak=max(peak,len(live));tokens.append(sum(v[0] for v in m.req.values()));perstep.append((t,len(live),tokens[-1],completed,rejected,preempted))
        if t>=steps and not live:break
    assert not live
    assert completed+rejected+preempted==len(events)
    return ops,bits,dict(completed=completed,rejected=rejected,preempted=preempted,arrivals=len(events),peak_concurrency=peak,avg_tokens_per_step=np.mean(tokens[:steps]),throughput_per_step=completed/steps),perstep

def dynamic_experiments():
    records=[]
    configs=[('W4_feedback',.8,c,p) for c,p in [(1,'preempt'),(4,'preempt'),(8,'preempt'),(1,'wait5')]]+ [('W5_feedback',p,1,'preempt') for p in [.3,.5,.7,.9,1.1,1.3,1.5]]
    for workload,pressure,chunk,policy in configs:
        for seed in range(10):
            events,rate,meanp=arrivals(seed,350,pressure)
            tagbase=f'{workload}_p{pressure}_chunk{chunk}_{policy}_seed{seed}'
            # Save external events once; identical across strategies and block sizes.
            eventpath=ROOT/f'workloads/{tagbase}_arrivals.csv'
            pd.DataFrame(events,columns=['step','id','prompt','output']).to_csv(eventpath,index=False)
            for s in [2,4,8,16]:
                for kind in ['contig','paged']:
                    ops,bits,stats,time=feedback(events,kind,s,350,chunk,policy)
                    tag=f'{tagbase}_S{s}_{kind}';d=replay(kind,4096//s,s,ops,tag,bits)
                    pd.DataFrame(time,columns=['step','concurrency','tokens','completed','rejected','preempted']).to_csv(ROOT/f'results/raw/{tag}_time.csv',index=False)
                    a=d[d.op=='ALLOC'];b=d[d.op=='APPEND'];f=d[d.fail_reason=='no_space']
                    stats.update(workload=workload,pressure=pressure,chunk=chunk,policy=policy,seed=seed,S=s,strategy=kind,arrival_rate=rate,mean_prompt=meanp,alloc_fail_rate=(a.fail_reason=='no_space').mean(),append_fail_rate=(b.fail_reason=='no_space').mean(),no_space=len(f),pure_frag_fail=int(((f.pre_free_blocks>=f.needed_blocks)&(f.needed_blocks>0)).sum()),utilization=d.utilization.mean(),unused=d.internal_waste_tokens.mean(),max_unused=d.internal_waste_tokens.max(),waste_per_request=(d.internal_waste_tokens/d.active_reqs.replace(0,np.nan)).mean(),ext_frag=d.ext_frag.mean(),occupancy=d.occupancy.mean())
                    records.append(stats)
        print('feedback done',workload,pressure,chunk,policy,flush=True)
    data=pd.DataFrame(records);table(data,'feedback_summary')
    metrics=['completed','rejected','preempted','alloc_fail_rate','append_fail_rate','utilization','unused','ext_frag','pure_frag_fail','avg_tokens_per_step','peak_concurrency']
    groups=data.groupby(['workload','pressure','chunk','policy','strategy','S'])[metrics].agg(['mean','std']);groups.columns=['_'.join(c) for c in groups.columns];table(groups.reset_index(),'feedback_mean_sd')
    for workload in ['W4_feedback','W5_feedback']:table(groups.reset_index().query('workload==@workload'),workload+'_main')
    scan=data[data.workload=='W5_feedback'];fig_,axes=plt.subplots(1,3,figsize=(16,4))
    for ax,metric in zip(axes,['completed','alloc_fail_rate','preempted']):
        for kind in ['contig','paged']:
            for s in [4,16]:
                g=scan[(scan.strategy==kind)&(scan.S==s)].groupby('pressure')[metric].agg(['mean','std']);ax.errorbar(g.index,g['mean'],yerr=g['std'],marker='o',label=f'{kind} S={s}')
        ax.set(xlabel='Expected demand / C (chunk=1, no losses)',ylabel=metric);ax.legend(fontsize=7)
    fig('fig6_pressure_feedback')
    thresholds=[]
    for (kind,s),part in scan.groupby(['strategy','S']):
        g=part.groupby('pressure').apply(lambda d:((d.rejected+d.preempted)/d.arrivals).mean(),include_groups=False)
        hit=g[g>=.1];thresholds.append(dict(strategy=kind,S=s,loss_threshold=.1,first_tested_pressure=float(hit.index[0]) if len(hit) else np.nan,note='grid threshold, not exact transition'))
    table(pd.DataFrame(thresholds),'pressure_thresholds')
    base=data[(data.workload=='W4_feedback')&(data.chunk==1)&(data.policy=='preempt')]
    fig_,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,metric in zip(axes,['alloc_fail_rate','append_fail_rate']):
        for j,kind in enumerate(['contig','paged']):
            g=base[base.strategy==kind].groupby('S')[metric].agg(['mean','std']);ax.bar(np.arange(4)+j*.38,g['mean'],.38,yerr=g['std'],label=kind)
        ax.set_xticks(np.arange(4)+.19,[2,4,8,16]);ax.set(xlabel='S (tokens/block)',ylabel=metric);ax.legend()
    fig('fig2_W4_feedback')

def supplementary_capacity():
    from gen import generate
    rows=[]
    # fixed-N bias and exact constant C across all extended block sizes
    for mode in ['fixed_N256','fixed_C4096']:
        for seed in range(10):
            ops=generate('W2',seed)
            for s in [1,2,4,8,16,32,64]:
                n=256 if mode=='fixed_N256' else 4096//s
                for kind in ['contig','paged']:
                    d=replay(kind,n,s,ops,f'{mode}_seed{seed}_S{s}_{kind}')
                    rows.append(dict(mode=mode,seed=seed,strategy=kind,S=s,N=n,C=n*s,alloc_fail_rate=(d[d.op=='ALLOC'].fail_reason=='no_space').mean(),utilization=d.utilization.mean(),unused=d.internal_waste_tokens.mean(),waste_per_request=(d.internal_waste_tokens/d.active_reqs.replace(0,np.nan)).mean(),metadata_bytes=d.used_blocks.mean()*16+n*40+4093*8))
    x=pd.DataFrame(rows);table(x,'capacity_control')
    fig_,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,mode in zip(axes,['fixed_N256','fixed_C4096']):
        for kind in ['contig','paged']:
            g=x[(x['mode']==mode)&(x.strategy==kind)].groupby('S').alloc_fail_rate.agg(['mean','std']);ax.errorbar(g.index,g['mean'],yerr=g['std'],marker='o',label=kind)
        ax.set(xlabel='S (tokens/block)',ylabel='Allocation failure fraction',title=mode,xscale='log');ax.legend()
    fig('fixed_N_vs_fixed_C')
    fig_,axes=plt.subplots(1,3,figsize=(15,4))
    for ax,metric in zip(axes,['utilization','unused','waste_per_request']):
        for kind in ['contig','paged']:
            g=x[(x['mode']=='fixed_C4096')&(x.strategy==kind)].groupby('S')[metric].agg(['mean','std']);ax.errorbar(g.index,g['mean'],yerr=g['std'],marker='o',label=kind)
        if metric=='waste_per_request':ax.plot([1,2,4,8,16,32,64],[(s-1)/2 for s in [1,2,4,8,16,32,64]],'k--',label='(S-1)/2')
        ax.set(xlabel='S (tokens/block)',ylabel=metric,xscale='log');ax.legend()
    fig('fig3_exact_capacity')
    fig_,ax=plt.subplots(figsize=(9,4));bx=ax.twinx()
    for kind in ['contig','paged']:
        g=x[(x['mode']=='fixed_C4096')&(x.strategy==kind)].groupby('S')[['unused','metadata_bytes']].mean();ax.plot(g.index,g.unused,marker='o',label=kind+' unused');bx.plot(g.index,g.metadata_bytes,'--',label=kind+' metadata')
    ax.set(xscale='log',xlabel='S (tokens/block)',ylabel='Mean unused tokens');bx.set_ylabel('Estimated metadata bytes');ax.legend(loc='upper left');bx.legend(loc='upper right');fig('fig7_exact_capacity')
    adverse=[]
    for s in [2,4,8,16]:
        n=64;ops=[('ALLOC',f'R{i}',s) for i in range(n)]+[('FREE',f'R{i}',0) for i in range(0,n,2)]+[('ALLOC','BIG',16*s)]
        for kind in ['contig','paged']:
            d=replay(kind,n,s,ops,f'W6_corrected_S{s}_{kind}');last=d.iloc[-1];adverse.append(dict(strategy=kind,S=s,ok=int(last.ok),pre_free_blocks=last.pre_free_blocks,pre_largest_free_run=last.pre_largest_free_run,needed_blocks=last.needed_blocks))
    table(pd.DataFrame(adverse),'W6_corrected')

def hash_experiments():
    class poisson:
        @staticmethod
        def pmf(k,lam):
            return np.exp(-lam+np.asarray(k)*math.log(lam)-np.vectorize(math.lgamma)(np.asarray(k)+1))
    r=random.Random(9142)
    datasets={'sequential':[f'R{i}' for i in range(10000)],'random':[''.join(r.choices('abcdefghijklmnopqrstuvwxyz0123456789',k=12)) for _ in range(10000)]}
    import itertools
    datasets['anagrams']=[''.join(p) for p in itertools.islice(itertools.permutations('abcdefgh'),10000)]
    def hashed(id,fn):
        h=2166136261 if fn=='fnv1a32' else 0
        for c in id.encode():
            if fn=='ascii_sum':h+=c
            elif fn=='fnv1a32':h=((h^c)*16777619)&0xffffffff
            else:h=(h*(131 if fn=='actual131' else 31)+c)&0xffffffff
        return h
    rows=[];distribution=[]
    for name,ids in datasets.items():
        for m in [1009,1024]:
            for fn in ['actual131','ascii_sum','poly31','fnv1a32']:
                counts=np.bincount([hashed(id,fn)%m for id in ids],minlength=m);lam=len(ids)/m
                observed=np.bincount(counts);expected=poisson.pmf(np.arange(max(len(observed),50)),lam)*m
                # Merge adjacent sparse categories to get expected frequencies >=5.
                obs=[];exp=[];a=b=0.
                for k in range(len(expected)):
                    a+=observed[k] if k<len(observed) else 0;b+=expected[k]
                    if b>=5:obs.append(a);exp.append(b);a=b=0.
                if b and exp:obs[-1]+=a;exp[-1]+=b
                stat=sum((o-e)**2/e for o,e in zip(obs,exp));df=max(1,len(exp)-1)
                rows.append(dict(dataset=name,M=m,hash=fn,max_chain=int(counts.max()),mean_success_comparisons=float(sum(counts*(counts+1)/2)/len(ids)),bucket_occupancy=float((counts>0).mean()),chi_square=stat,chi_df=df,chi_square_per_df=stat/df))
                for k,c in enumerate(observed):distribution.append(dict(dataset=name,M=m,hash=fn,chain_length=k,buckets=int(c),poisson_expected=float(poisson.pmf(k,lam)*m)))
    table(pd.DataFrame(rows),'hash_comparison');pd.DataFrame(distribution).to_csv(ROOT/'results/raw/hash_distribution.csv',index=False)
    dist=pd.DataFrame(distribution);fig_,axes=plt.subplots(1,3,figsize=(15,4))
    for ax,name in zip(axes,datasets):
        for fn in ['actual131','ascii_sum','poly31','fnv1a32']:
            g=dist[(dist.dataset==name)&(dist.M==1009)&(dist.hash==fn)];ax.plot(g.chain_length,g.buckets,marker='.',label=fn)
        ax.set(xscale='symlog',yscale='symlog',xlabel='Chain length',ylabel='Number of buckets',title=name);ax.legend(fontsize=7)
    fig('fig9_hash_distribution')

def finish():
    # Read main summary and export per-workload report-sized tables.
    x=pd.read_csv(ROOT/'results/tables/summary.csv')
    for name in ['W0','W1','W2','W3']:
        part=x[(x.workload==name)&x.S.isin([2,4,8,16])]
        metrics=['alloc_fail_rate','append_fail_rate','utilization','unused','ext_frag','no_space','pure_frag_fail']
        g=part.groupby(['strategy','S'])[metrics].agg(['mean','std']);g.columns=['_'.join(c) for c in g.columns];table(g.reset_index(),name+'_main')
    metrics=pd.DataFrame([
      ['Allocation failure','no_space / attempted ALLOC or APPEND','Separates capacity failures from API validation'],
      ['Utilization','stored tokens / (used blocks * S)','Allocated capacity actually filled'],
      ['Unused space','used blocks * S - stored tokens','Internal fragmentation cost'],
      ['External fragmentation','1-largest free run/free blocks','Physical distribution, not necessarily harmful for paged'],
      ['Pure fragmentation failure','no_space AND pre_free_blocks>=needed_blocks','Failure despite sufficient total free blocks'],
      ['Occupancy','used blocks/N','Physical block pressure'],
      ['Completed requests','successful generation of entire target output','Real decoded throughput in feedback model'],
      ['Rejected / preempted','failed arrival / termination after failed append','Admission versus growth failure'],
      ['Metadata estimate','N*sizeof(Block)+used*sizeof(BlockNode)+4093*sizeof(pointer)','Small blocks incur more metadata'],
      ['Operation time','median of five warm benchmark repetitions','Empirical scale dependence'],
    ],columns=['metric','definition','reason']);table(metrics,'table3_metrics')
    b=pd.read_csv(ROOT/'results/tables/benchmark_median.csv')
    notes=[]
    for (kind,op,scenario),g in b.groupby(['strategy','operation','scenario']):
        g=g.sort_values('scale');lo=g.iloc[0];hi=g.iloc[-1]
        theory='expected O(L*(1+R/4093))' if op=='lookup' else ('Theta(N)' if kind=='paged' or scenario=='high_end' and op=='allocate' else 'O(1) for tested constant-size operation')
        notes.append(dict(strategy=kind,operation=op,scenario=scenario,theory=theory,min_scale=lo['scale'],max_scale=hi['scale'],min_ns=lo.ns_per_op,max_ns=hi.ns_per_op,time_ratio=hi.ns_per_op/lo.ns_per_op))
    table(pd.DataFrame(notes),'table2_theory_vs_measurement')
    (ROOT/'results/DELIVERY_INDEX.md').write_text('''# Final artifact index
Primary static workload tables: W0_main, W1_main, W2_main, W3_main.
Primary dynamic workload tables: W4_feedback_main, W5_feedback_main; feedback_summary contains all ten seeds.
Pressure thresholds: pressure_thresholds (first sampled pressure with >=10% total request loss).
Capacity fairness: capacity_control, figures fixed_N_vs_fixed_C, fig3_exact_capacity, fig7_exact_capacity.
Adversarial: W6_corrected. Hashes: hash_comparison and fig9_hash_distribution.
Controlled timing: benchmark_median and table2_theory_vs_measurement.
Metric definitions: table3_metrics.
Use fig2_W4_feedback and fig6_pressure_feedback instead of the older exogenous W4/W5 plots.
Old exogenous W4/W5 data are retained as supplemental fixed-trace experiments, not real inference throughput.
All figures are PNG/PDF; editable structure source is results/structure.dot.
''',encoding='utf-8')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--skip-validation',action='store_true');a=p.parse_args()
    if not a.skip_validation:validations()
    dynamic_experiments();supplementary_capacity();hash_experiments();finish()
