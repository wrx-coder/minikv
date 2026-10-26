#ifndef MINIKV_H

#define MINIKV_H



#include<iostream>

#include <string>



struct Block {

    std::string owner; // 空字符串表示空闲

    int used;          // 已使用的 Token 数

};



struct BlockNode {

    int index;

    BlockNode* next;

};



struct Request {

    std::string id;

    int tokenCount;

    BlockNode* head;

    BlockNode* tail;

    Request* hashNext;

};



// 两种策略遵守相同的六项操作契约。

class MiniKV {

public:

    virtual ~MiniKV() = default;

    virtual bool allocate(const std::string& id, int tokenCount) = 0;

    virtual bool append(const std::string& id, int newTokenCount) = 0;

    // 返回请求的只读指针；不存在时返回 nullptr。不得由调用方释放。

    virtual const Request* lookup(const std::string& id) const = 0;

    virtual bool free(const std::string& id) = 0;

    virtual void displayMemory() const = 0;

    virtual void displayRequest(const std::string& id) const = 0;

};



#endif
