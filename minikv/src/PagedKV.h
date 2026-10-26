#ifndef PAGEDKV_H

#define PAGEDKV_H



#include "check.h"

#include "MiniKV.h"



class PagedKV : public MiniKV {

public:

    PagedKV(int blockCount, int blockSize);

    ~PagedKV() override;

    PagedKV(const PagedKV&) = delete;

    PagedKV& operator=(const PagedKV&) = delete;



    bool allocate(const std::string& id, int tokenCount) override;

    bool append(const std::string& id, int newTokenCount) override;

    const Request* lookup(const std::string& id) const override;

    bool free(const std::string& id) override;

    void displayMemory() const override;

    void displayRequest(const std::string& id) const override;



private:

    int n_;

    int s_;

    Block* memory_;         // 物理内存数组

    Request** buckets_;     // 哈希表数组，使用链式解决冲突

    int bucketCount_;

};



#endif
