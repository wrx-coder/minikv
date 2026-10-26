#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>
#include "ContiguousKV.h"
#include "PagedKV.h"
using namespace std;
volatile unsigned long long sink=0;
MiniKV* create(string kind,int n,int s){return kind=="contig"?static_cast<MiniKV*>(new ContiguousKV(n,s)):static_cast<MiniKV*>(new PagedKV(n,s));}
template<class F> double timing(int count,F fn){auto t=chrono::steady_clock::now();for(int j=0;j<count;++j)fn(j);return double(chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-t).count())/count;}
int main(){
 { ofstream sizes("results/tables/sizeof.json"); sizes<<"{\"Block\":"<<sizeof(Block)<<",\"BlockNode\":"<<sizeof(BlockNode)<<",\"Request\":"<<sizeof(Request)<<",\"pointer\":"<<sizeof(Request*)<<"}"; }
 cout<<"strategy,operation,scenario,scale,repeat,ns_per_op\n";
 for(string kind:{"contig","paged"}){
  for(int r:{10,100,1000,10000}){
   MiniKV* kv=create(kind,20000,1);vector<string> ids;
   for(int i=0;i<r;++i){string id="X"+to_string(i*2654435761ULL);ids.push_back(id);kv->allocate(id,1);}
   vector<string> queries;for(int i=0;i<20000;++i)queries.push_back(i%2?ids[i%r]:"MISS"+to_string(i));
   for(int rep=-1;rep<5;++rep){double ns=timing(1000000,[&](int j){sink+=kv->lookup(queries[j%queries.size()])!=nullptr;});if(rep>=0)cout<<kind<<",lookup,half_hit,"<<r<<','<<rep<<','<<ns<<'\n';}
   delete kv;
  }
  for(int n:{500,1000,2000,4000,8000})for(string scenario:{"empty","high_end"})for(string op:{"allocate","append","append_new"}){
   MiniKV* kv=create(kind,n,8);
   if(op!="allocate")kv->allocate("TARGET",op=="append_new"?8:7);
   if(scenario=="high_end")kv->allocate("FILL",(n-3)*8);
   for(int rep=-1;rep<5;++rep){
    double ns=0;const int loops=3000;
    if(op=="allocate"){
     // Each sample times only allocation; cleanup is excluded from timer.
     for(int j=0;j<loops;++j){auto t=chrono::steady_clock::now();bool ok=kv->allocate("TEST",8);auto end=chrono::steady_clock::now();sink+=ok;ns+=chrono::duration_cast<chrono::nanoseconds>(end-t).count();kv->free("TEST");}
    }else{
     // Controlled append with room: rebuild target outside timer to keep state identical.
     for(int j=0;j<loops;++j){auto t=chrono::steady_clock::now();bool ok=kv->append("TARGET",1);auto end=chrono::steady_clock::now();sink+=ok;ns+=chrono::duration_cast<chrono::nanoseconds>(end-t).count();kv->free("TARGET");kv->allocate("TARGET",op=="append_new"?8:7);}
    }
    if(rep>=0)cout<<kind<<','<<op<<','<<scenario<<','<<n<<','<<rep<<','<<ns/loops<<'\n';
   }
   delete kv;
  }
 }
}
