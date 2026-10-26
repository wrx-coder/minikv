"""Independent, deliberately simple OJ-format reference model."""
import sys

class Model:
    def __init__(self,n,s,kind):
        self.n,self.s,self.kind=n,s,kind
        self.owner=['']*n
        self.req={}
    def run(self,line):
        a=line.split(); op=a[0]; rid=a[1] if len(a)>1 else None
        if op=='MEMORY': return ' '.join(x or '-' for x in self.owner)
        if op=='LOOKUP':
            return ('FOUND %d %d'%(self.req[rid][0],len(self.req[rid][1]))) if rid in self.req else 'NOT FOUND'
        if op=='REQUEST':
            return ('%d %d %s'%(self.req[rid][0],len(self.req[rid][1]),' '.join(map(str,self.req[rid][1])))) if rid in self.req else 'NOT FOUND'
        if op=='FREE':
            if rid not in self.req:return 'FAIL'
            for i in self.req.pop(rid)[1]:self.owner[i]=''
            return 'OK'
        count=int(a[2]); old=self.req.get(rid)
        if count<=0 or (op=='ALLOC' and old is not None) or (op=='APPEND' and old is None):return 'FAIL'
        if op=='ALLOC':
            need=(count-1)//self.s+1
            if self.kind=='contig':
                choices=next((list(range(i,i+need)) for i in range(self.n-need+1) if all(not self.owner[j] for j in range(i,i+need))),[])
            else:choices=[i for i,x in enumerate(self.owner) if not x][:need]
            if len(choices)!=need:return 'FAIL'
            self.req[rid]=[count,choices]
        else:
            tokens,blocks=old; need=(tokens+count-1)//self.s+1-len(blocks)
            if self.kind=='contig':
                last=blocks[-1];choices=list(range(last+1,last+1+need))
                if choices and (choices[-1]>=self.n or any(self.owner[i] for i in choices)):return 'FAIL'
            else:choices=[i for i,x in enumerate(self.owner) if not x][:need]
            if len(choices)!=need:return 'FAIL'
            old[0]+=count;blocks.extend(choices)
        for i in choices:self.owner[i]=rid
        return 'OK'

def execute(text,kind):
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.startswith('#')]
    n,s,q=map(int,lines[0].split());m=Model(n,s,kind)
    return [m.run(line) for line in lines[1:1+q]]
if __name__=='__main__':print('\n'.join(execute(sys.stdin.read(),sys.argv[1])))
