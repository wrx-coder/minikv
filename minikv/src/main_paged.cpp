#include "PagedKV.h"

#include "check.h"

#include <iostream>

#include <string>



int main() {

    int n, s, q;

    if (!(std::cin >> n >> s >> q)) return 0;

    PagedKV manager(n, s);

    MiniKV& kv = manager;

    for (int i = 0; i < q; ++i) {

        std::string op, id;

        std::cin >> op;

        if (op == "ALLOC" || op == "APPEND") {

            int count;

            std::cin >> id >> count;

            bool ok = op == "ALLOC" ? kv.allocate(id, count) : kv.append(id, count);

            std::cout << (ok ? "OK" : "FAIL") << '\n';

        } else if (op == "FREE") {

            std::cin >> id;

            std::cout << (kv.free(id) ? "OK" : "FAIL") << '\n';

        } else if (op == "LOOKUP") {

            std::cin >> id;

            const Request* request = kv.lookup(id);

            if (!request) std::cout << "NOT FOUND";

            else {

                int blocks = 0;

                for (const BlockNode* p = request->head; p; p = p->next) ++blocks;

                std::cout << "FOUND " << request->tokenCount << ' ' << blocks;

            }

            std::cout << '\n';

        } else if (op == "REQUEST") {

            std::cin >> id;

            kv.displayRequest(id);

            std::cout << '\n';

        } else if (op == "MEMORY") {

            kv.displayMemory();

            std::cout << '\n';

        }

    }

}
