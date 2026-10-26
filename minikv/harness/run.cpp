#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>
#include <chrono>
#include "ContiguousKV.h"
#include "PagedKV.h"
using namespace std;
int main(int argc,char**argv){
 if(argc<5){cerr<<"usage: run strategy N S trace [sample_every]\n";return 2;}
 string kind=argv[1];int n=stoi(argv[2]),s=stoi(argv[3]),every=argc>5?stoi(argv[5]):1;
 MiniKV* kv=kind=="contig"?static_cast<MiniKV*>(new ContiguousKV(n,s)):static_cast<MiniKV*>(new PagedKV(n,s));
 ifstream f(argv[4]);string line,op,id;int count,step=0;unordered_set<string> live;
 cout<<"step,op,id,count,ok,fail_reason,active_reqs,used_blocks,free_blocks,tokens_stored,largest_free_run,ext_frag,utilization,internal_waste_tokens,occupancy,needed_blocks,pre_free_blocks,pre_largest_free_run,ns\n";
 while(getline(f,line)){
  if(line.empty()||line[0]=='#')continue;
  istringstream in(line);in>>op>>id;count=0;if(op!="FREE")in>>count;
  if(op!="ALLOC"&&op!="APPEND"&&op!="FREE")continue;
  bool exists=live.count(id);const Request* req=exists?kv->lookup(id):nullptr;
  int need=op=="ALLOC"&&count>0?(count-1)/s+1:op=="APPEND"&&req&&count>0?((req->tokenCount+count-1)/s-(req->tokenCount-1)/s):0;
  // pre-state measured separately, outside timed section
  auto scan=[&](){ostringstream buf;streambuf* old=cout.rdbuf(buf.rdbuf());kv->displayMemory();cout.rdbuf(old);
    istringstream m(buf.str());string x;int used=0,run=0,best=0;while(m>>x){if(x=="-"){++run;best=max(best,run);}else{++used;run=0;}}return pair<int,int>(used,best);};
  int prefree=-1,prebest=-1;if(every>0){auto p=scan();prefree=n-p.first;prebest=p.second;}
  auto begin=chrono::steady_clock::now();bool ok=op=="ALLOC"?kv->allocate(id,count):op=="APPEND"?kv->append(id,count):kv->free(id);
  auto elapsed=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-begin).count();
  string reason="";if(!ok)reason=op=="FREE"||op=="APPEND"&&!exists?"not_found":op=="ALLOC"&&exists?"dup_id":count<=0?"bad_count":"no_space";
  if(ok){if(op=="FREE")live.erase(id);else if(op=="ALLOC")live.insert(id);}
  ++step;if(every<=0||step%every)continue;
  auto [used,best]=scan();long long tokens=0;for(auto& key:live)tokens+=kv->lookup(key)->tokenCount;
  int free=n-used,waste=used*s-tokens;
  cout<<step<<','<<op<<','<<id<<','<<count<<','<<ok<<','<<reason<<','<<live.size()<<','<<used<<','<<free<<','<<tokens<<','<<best<<','<<(free?1.0-double(best)/free:0)<<',';
  if(used)cout<<double(tokens)/(used*s);cout<<','<<waste<<','<<double(used)/n<<','<<need<<','<<prefree<<','<<prebest<<','<<elapsed<<'\n';
 }
 delete kv;
}
