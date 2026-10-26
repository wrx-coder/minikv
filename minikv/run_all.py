"""Run from C:/work/minikv; --stage test | experiment | all."""
import argparse,csv,io,os,pathlib,random,statistics,subprocess,sys,platform
ROOT=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'workloads')]
from ref import execute
from gen import generate,save

def build():
    import shutil
    gcc=os.environ.get('CXX') or shutil.which('g++') or 'C:/tools/msys64/ucrt64/bin/g++.exe'
    print('compiler:',subprocess.check_output([gcc,'--version'],text=True).splitlines()[0],flush=True)
    env=os.environ.copy();env['PATH']=str(pathlib.Path(gcc).parent)+os.pathsep+env['PATH']
    for name,files in [('contig',['src/main_contig.cpp','src/ContiguousKV.cpp']),('paged',['src/main_paged.cpp','src/PagedKV.cpp']),('harness',['harness/run.cpp','src/ContiguousKV.cpp','src/PagedKV.cpp']),('bench',['harness/bench.cpp','src/ContiguousKV.cpp','src/PagedKV.cpp'])]:
        subprocess.run([gcc,'-std=c++17','-O2','-static','-Isrc','-o',str(ROOT/(name+'.exe')),*[str(ROOT/x) for x in files]],check=True,env=env)

def call(exe,data):
    return subprocess.run([str(ROOT/(exe+'.exe'))],input=data.encode('ascii'),capture_output=True,check=True).stdout.decode().splitlines()
def oj(n,s,ops):return f'{n} {s} {len(ops)}\n'+'\n'.join(ops)+'\n'
def test():
    samples=[('contig','8 4 15\nALLOC A 8\nALLOC B 8\nLOOKUP A\nAPPEND A 1\nREQUEST A\nMEMORY\nFREE B\nAPPEND A 1\nREQUEST A\nMEMORY\nFREE A\nLOOKUP A\nLOOKUP B\nALLOC C 12\nMEMORY\n','OK\nOK\nFOUND 8 2\nFAIL\n8 2 0 1\nA A B B - - - -\nOK\nOK\n9 3 0 1 2\nA A A - - - - -\nOK\nNOT FOUND\nNOT FOUND\nOK\nC C C - - - - -'),('paged','8 4 15\nALLOC A 8\nALLOC B 8\nLOOKUP A\nAPPEND A 1\nREQUEST A\nMEMORY\nFREE B\nAPPEND A 1\nREQUEST A\nMEMORY\nFREE A\nLOOKUP A\nLOOKUP B\nALLOC C 12\nMEMORY\n','OK\nOK\nFOUND 8 2\nOK\n9 3 0 1 4\nA A B B A - - -\nOK\nOK\n10 3 0 1 4\nA A - - A - - -\nOK\nNOT FOUND\nNOT FOUND\nOK\nC C C - - - - -')]
    for kind,data,expected in samples:assert call(kind,data)==expected.splitlines(),kind
    cases=[];r=random.Random(53001)
    edge=['ALLOC R12 1','ALLOC R21 1','ALLOC ab 1','ALLOC ba 1','FREE R12','LOOKUP R21','FREE ab','REQUEST ba','ALLOC R12 4','APPEND R12 0','APPEND R12 -1','MEMORY','REQUEST R12','FREE R12','FREE R12','ALLOC R12 1','APPEND R12 1000000','MEMORY']
    cases.append(oj(8,4,edge))
    for mode in ('small','official'):
        for seed in range(2000):
            rng=random.Random(seed+ (0 if mode=='small' else 100000));n=rng.randint(1,20 if mode=='small' else 2000);s=rng.randint(1,8 if mode=='small' else 100000)
            q=rng.randint(1,30 if mode=='small' else 65);ids=[f'R{i}' for i in range(3 if mode=='small' else 12)]+['R12','R21','ab','ba']
            ops=[]
            for _ in range(q):
                op=rng.choices(['ALLOC','APPEND','FREE','LOOKUP','REQUEST','MEMORY'],[3,3,2,1,1,1])[0];id=rng.choice(ids)
                count=rng.choice([0,1,s,s+1,1000000,rng.randint(1,30 if mode=='small' else 1000000)])
                ops.append(op+((' '+id) if op!='MEMORY' else '')+((' '+str(count)) if op in ('ALLOC','APPEND') else ''))
            cases.append(oj(n,s,ops))
    for index,data in enumerate(cases):
        for kind in ('contig','paged'):
            got=call(kind,data);want=execute(data,kind)
            if got!=want:
                (ROOT/'tests/failing.in').write_text(data);raise AssertionError(f'{kind} case {index} line {next((i for i,(a,b) in enumerate(zip(got,want)) if a!=b),"length")}')
        if index%500==0:print('tested',index,flush=True)
    print('PASS',len(cases),'cases per strategy',flush=True)
    return len(cases)

def experiment():
    import pandas as pd,numpy as np,matplotlib
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    raw=ROOT/'results/raw';tables=ROOT/'results/tables';figs=ROOT/'results/figs';traces=ROOT/'workloads'
    rows=[];w0=[]
    for workload in ['W0','W1','W2','W3','W4','W5','W6']:
        seeds=range(10) if workload not in ('W0','W6') else range(1)
        pressures=[.3,.5,.7,.9,1.1,1.3,1.5] if workload=='W5' else [.8]
        for pressure in pressures:
            for seed in seeds:
                ops=generate(workload,seed,450,pressure)
                tag=f'{workload}_p{pressure:.1f}_seed{seed}'
                trace=traces/(tag+'.trace');save(trace,workload,seed,ops)
                for s in ([1,2,4,8,16,32,64] if workload not in ('W0','W6') else [2,4,8,16]):
                    n=(32 if workload=='W0' else 4000)//s
                    for kind in ('contig','paged'):
                        run=subprocess.run([str(ROOT/'harness.exe'),kind,str(n),str(s),str(trace)],capture_output=True,text=True,check=True)
                        df=pd.read_csv(io.StringIO(run.stdout));df.to_csv(raw/f'{tag}_S{s}_{kind}.csv',index=False)
                        alloc=df[df.op=='ALLOC'];append=df[df.op=='APPEND'];fail=df[df.fail_reason=='no_space']
                        pure=fail[(fail.pre_free_blocks>=fail.needed_blocks)&(fail.needed_blocks>0)]
                        rows.append(dict(workload=workload,pressure=pressure,seed=seed,S=s,N=n,strategy=kind,alloc_fail=int((alloc.fail_reason=='no_space').sum()),alloc_attempts=len(alloc),append_fail=int((append.fail_reason=='no_space').sum()),append_attempts=len(append),alloc_fail_rate=(alloc.fail_reason=='no_space').mean(),append_fail_rate=(append.fail_reason=='no_space').mean(),utilization=df.utilization.mean(),unused=df.internal_waste_tokens.mean(),max_unused=df.internal_waste_tokens.max(),waste_per_request=(df.internal_waste_tokens/df.active_reqs.replace(0,np.nan)).mean(),ext_frag=df.ext_frag.mean(),max_ext_frag=df.ext_frag.max(),pure_frag_fail=len(pure),no_space=len(fail),occupancy=df.occupancy.mean(),effective_capacity=df.tokens_stored.max()/(n*s),metadata_bytes=df.used_blocks.mean()*16+n*40+4093*8,successful_free=int(((df.op=='FREE')&(df.ok==1)).sum()),rejected=int(((alloc.ok==0)&(alloc.fail_reason=='no_space')).sum()),failed_append_events=int(((append.ok==0)&(append.fail_reason=='no_space')).sum()),peak_concurrency=df.active_reqs.max(),avg_tokens=df.tokens_stored.mean(),avg_ns=df.ns.mean()))
                        if workload=='W0' and s==4:
                            # display state reconstructed from reference for layout chart
                            from ref import Model
                            m=Model(n,s,kind)
                            for i,(op,id,count) in enumerate(ops):
                                m.run(f'{op} {id}'+(f' {count}' if op!='FREE' else ''))
                                w0.append(dict(strategy=kind,step=i+1,op=op,id=id,layout=m.owner.copy()))
            print('finished',workload,pressure,flush=True)
    df=pd.DataFrame(rows);df.to_csv(tables/'summary.csv',index=False)
    group=df.groupby(['workload','pressure','strategy','S'],as_index=False).agg({x:['mean','std'] for x in ['alloc_fail_rate','append_fail_rate','utilization','unused','ext_frag','successful_free','pure_frag_fail','metadata_bytes']})
    group.columns=['_'.join(x).strip('_') for x in group.columns];group.to_csv(tables/'main.csv',index=False)
    (tables/'main.md').write_text(group.round(3).to_markdown(index=False),encoding='utf-8')
    plt.rcParams.update({'font.size':10,'figure.dpi':120})
    def export(name):plt.tight_layout();plt.savefig(figs/(name+'.png'),dpi=300);plt.savefig(figs/(name+'.pdf'));plt.close()
    for workload in ['W2','W3','W4']:
        sub=df[(df.workload==workload)&df.S.isin([2,4,8,16])];fig,axes=plt.subplots(1,2,figsize=(11,4))
        for ax,metric in zip(axes,['alloc_fail_rate','append_fail_rate']):
            for j,kind in enumerate(['contig','paged']):
                g=sub[sub.strategy==kind].groupby('S')[metric].agg(['mean','std']);ax.bar(np.arange(4)+j*.36,g['mean'],.36,yerr=g['std'],label=kind)
            ax.set_xticks(np.arange(4)+.18,[2,4,8,16]);ax.set_xlabel('Block size S (tokens)');ax.set_ylabel(metric+' (fraction)');ax.legend()
        export('fig2_'+workload)
    sub=df[df.workload=='W2'];fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,metric in zip(axes,['utilization','waste_per_request']):
        for kind in ['contig','paged']:
            g=sub[sub.strategy==kind].groupby('S')[metric].agg(['mean','std']);ax.errorbar(g.index,g['mean'],yerr=g['std'],marker='o',label=kind)
        if metric=='waste_per_request':ax.plot([1,2,4,8,16,32,64],[(s-1)/2 for s in [1,2,4,8,16,32,64]],'k--',label='(S-1)/2')
        ax.set_xlabel('S (tokens/block)');ax.set_ylabel(metric);ax.legend()
    export('fig3_util_waste')
    fig,ax=plt.subplots(figsize=(9,4))
    for kind in ['contig','paged']:
        trace=pd.read_csv(raw/f'W3_p0.8_seed0_S4_{kind}.csv');ax.plot(trace.step,trace.ext_frag,label=kind)
    ax.set(xlabel='Operation step',ylabel='External fragmentation');ax.legend();export('fig4_fragmentation')
    g=df[(df.strategy=='contig')&df.workload.isin(['W2','W3','W4'])&df.S.isin([2,4,8,16])].groupby(['workload','S'])[['pure_frag_fail','no_space']].sum();g=(g.pure_frag_fail/g.no_space.replace(0,np.nan)).unstack(0);g.plot.bar(figsize=(8,4));plt.ylabel('Pure fragmentation failures / no-space failures');export('fig5_pure_fragmentation')
    sub=df[df.workload=='W5'];fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,metric in zip(axes,['successful_free','alloc_fail_rate']):
        for kind in ['contig','paged']:
            for s in [4,16]:
                g=sub[(sub.strategy==kind)&(sub.S==s)].groupby('pressure')[metric].mean();ax.plot(g.index,g.values,marker='o',label=f'{kind} S={s}')
        ax.set(xlabel='Arrival multiplier (not normalized demand/C)',ylabel=metric);ax.legend()
    export('fig6_pressure')
    sub=df[df.workload=='W2'];fig,ax=plt.subplots(figsize=(8,4));bx=ax.twinx()
    for kind in ['contig','paged']:
        g=sub[sub.strategy==kind].groupby('S')[['waste_per_request','metadata_bytes']].mean();ax.plot(g.index,g.waste_per_request,marker='o',label=kind+' waste');bx.plot(g.index,g.metadata_bytes,'--',label=kind+' metadata')
    ax.set(xscale='log',xlabel='S (tokens/block)',ylabel='Waste (tokens/request)');bx.set_ylabel('Metadata estimate (bytes)');ax.legend(loc='upper left');bx.legend(loc='upper right');export('fig7_tradeoff')
    fig,ax=plt.subplots(figsize=(8,4))
    for kind in ['contig','paged']:
        g=df[(df.workload=='W2')&(df.strategy==kind)].groupby('S').avg_ns.mean();ax.plot(4000/g.index,g.values,marker='o',label=kind)
    ax.set(xlabel='N (blocks)',ylabel='Mean operation time incl. free (ns)',xscale='log',yscale='log');ax.legend();export('fig8_operation_time_proxy')
    fig,axes=plt.subplots(2,1,figsize=(12,4),sharex=True)
    for ax,kind in zip(axes,['contig','paged']):
        for row in [x for x in w0 if x['strategy']==kind]:
            for i,owner in enumerate(row['layout']):ax.barh(row['step'],1,left=i,color={'':'#eeeeee','A':'#4e79a7','B':'#f28e2b','C':'#e15759','D':'#76b7b2','E':'#59a14f'}[owner],edgecolor='white',height=.85)
        ax.set(ylabel=kind+' step',yticks=range(1,9));ax.invert_yaxis()
    axes[-1].set_xlabel('Physical block index (S=4, C=32 tokens)');export('fig1_layout')
    benchmark()
    print('rows:',len(df),'figures:',len(list(figs.glob('*.png'))))

def benchmark():
    import pandas as pd
    import matplotlib.pyplot as plt
    data=subprocess.check_output([str(ROOT/'bench.exe')],text=True)
    (ROOT/'results/raw/benchmark.csv').write_text(data,encoding='ascii')
    b=pd.read_csv(io.StringIO(data));g=b.groupby(['strategy','operation','scenario','scale'],as_index=False).ns_per_op.median()
    g.to_csv(ROOT/'results/tables/benchmark_median.csv',index=False)
    (ROOT/'results/tables/benchmark_median.md').write_text(g.round(2).to_markdown(index=False),encoding='utf-8')
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    for ax,op in zip(axes,['lookup','allocate','append']):
        for (kind,scenario),part in g[g.operation==op].groupby(['strategy','scenario']):
            ax.plot(part.scale,part.ns_per_op,marker='o',label=f'{kind} {scenario}')
        ax.set(xscale='log',yscale='log',xlabel='Active requests R' if op=='lookup' else 'Physical blocks N',ylabel='Median time (ns/op)',title=op);ax.legend(fontsize=7)
    fig.tight_layout()
    for ext in ['png','pdf']:fig.savefig(ROOT/f'results/figs/fig8_controlled_benchmark.{ext}',dpi=300)
    plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['all','test','experiment','supplement'],default='all');args=p.parse_args()
    os.chdir(ROOT);build()
    if args.stage in ('all','test'):test()
    if args.stage in ('all','experiment'):experiment()
    if args.stage in ('all','supplement'):
        import complete
        complete.validations();complete.dynamic_experiments();complete.supplementary_capacity();complete.hash_experiments();complete.finish()
