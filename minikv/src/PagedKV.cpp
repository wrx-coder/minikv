#include "PagedKV.h"
#include <iostream>
using namespace std;

namespace {
unsigned hashID(const string& id, int size) {
    unsigned h = 0;
    for (char ch : id) h = h * 131u + static_cast<unsigned char>(ch);
    return h % size;
}
}
PagedKV::PagedKV(int n, int s) : n_(n), s_(s), memory_(new Block[n]),
    buckets_(new Request*[4093]()), bucketCount_(4093) {
    for (int i=0;i<n_;++i) memory_[i].used=0;
}
PagedKV::~PagedKV() {
    for(int i=0;i<bucketCount_;++i) {
        Request* r=buckets_[i];
        while(r) {
            Request* next=r->hashNext;
            BlockNode* p=r->head;
            while(p) { BlockNode* q=p->next; delete p; p=q; }
            delete r; r=next;
        }
    }
    delete[] buckets_; delete[] memory_;
}
const Request* PagedKV::lookup(const string& id) const {
    for(Request* r=buckets_[hashID(id,bucketCount_)];r;r=r->hashNext)
        if(r->id==id) return r;
    return nullptr;
}
bool PagedKV::allocate(const string& id, int tokenCount) {
    if(tokenCount<=0 || lookup(id)) return false;
    int need=(tokenCount-1)/s_+1;
    if(need>n_) return false;
    int available=0;
    for(int i=0;i<n_;++i) if(memory_[i].owner.empty()) ++available;
    if(available<need) return false;
    Request* r=new Request{id,tokenCount,nullptr,nullptr,nullptr};
    int remaining=tokenCount;
    for(int i=0,added=0;i<n_ && added<need;++i) {
        if(!memory_[i].owner.empty()) continue;
        memory_[i].owner=id;
        memory_[i].used=remaining<s_?remaining:s_;
        remaining-=memory_[i].used;
        BlockNode* node=new BlockNode{i,nullptr};
        if(r->tail) r->tail->next=node; else r->head=node;
        r->tail=node; ++added;
    }
    unsigned h=hashID(id,bucketCount_);
    r->hashNext=buckets_[h]; buckets_[h]=r;
    return true;
}
bool PagedKV::append(const string& id, int newTokenCount) {
    Request* r=const_cast<Request*>(lookup(id));
    if(!r || newTokenCount<=0) return false;
    int last=r->tail->index;
    int room=s_-memory_[last].used;
    int extra=newTokenCount>room?newTokenCount-room:0;
    int need=extra?(extra-1)/s_+1:0;
    int available=0;
    for(int i=0;i<n_;++i) if(memory_[i].owner.empty()) ++available;
    if(available<need) return false;
    int filled=newTokenCount<room?newTokenCount:room;
    memory_[last].used+=filled;
    int remaining=newTokenCount-filled;
    for(int i=0,added=0;i<n_ && added<need;++i) {
        if(!memory_[i].owner.empty()) continue;
        memory_[i].owner=id;
        memory_[i].used=remaining<s_?remaining:s_;
        remaining-=memory_[i].used;
        BlockNode* node=new BlockNode{i,nullptr};
        r->tail->next=node; r->tail=node; ++added;
    }
    r->tokenCount+=newTokenCount;
    return true;
}
bool PagedKV::free(const string& id) {
    unsigned h=hashID(id,bucketCount_);
    Request** link=&buckets_[h];
    while(*link && (*link)->id!=id) link=&(*link)->hashNext;
    if(!*link) return false;
    Request* r=*link; *link=r->hashNext;
    BlockNode* p=r->head;
    while(p) {
        memory_[p->index].owner.clear(); memory_[p->index].used=0;
        BlockNode* next=p->next; delete p; p=next;
    }
    delete r; return true;
}
void PagedKV::displayMemory() const {
    for(int i=0;i<n_;++i) {
        if(i) cout << ' ';
        cout << (memory_[i].owner.empty()?"-":memory_[i].owner);
    }
}
void PagedKV::displayRequest(const string& id) const {
    const Request* r=lookup(id);
    if(!r) { cout << "NOT FOUND"; return; }
    int count=0;
    for(const BlockNode* p=r->head;p;p=p->next) ++count;
    cout << r->tokenCount << ' ' << count;
    for(const BlockNode* p=r->head;p;p=p->next) cout << ' ' << p->index;
}
