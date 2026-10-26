#include <algorithm>

#include <climits>

#include <iostream>

#include <random>

#include <string>



int main() {

    std::random_device rd;

    std::mt19937 rng(rd());



    const int n = std::uniform_int_distribution<int>(1, 2000)(rng);

    const int blockSize =

        std::uniform_int_distribution<int>(1, 100000)(rng);

    const int q = std::uniform_int_distribution<int>(1, 3000)(rng);



    std::uniform_int_distribution<int> operationDist(0, 7);

    std::uniform_int_distribution<int> idDist(0, 11);



    const std::string operations[] = {

        "ALLOC", "ALLOC", "APPEND", "APPEND",

        "FREE", "LOOKUP", "REQUEST", "MEMORY"

    };



    std::cout << n << ' ' << blockSize << ' ' << q << '\n';



    long long tokenBudget = INT_MAX;



    for (int i = 0; i < q; ++i) {

        const std::string op = operations[operationDist(rng)];

        const std::string id = "R" + std::to_string(idDist(rng));



        if (op == "ALLOC" || op == "APPEND") {

            const int upper = static_cast<int>(

                std::min(1000000LL, tokenBudget)

            );

            const int count =

                std::uniform_int_distribution<int>(0, upper)(rng);



            tokenBudget -= count;

            std::cout << op << ' ' << id << ' ' << count << '\n';

        } else if (op == "FREE" || op == "REQUEST" || op == "LOOKUP") {

            std::cout << op << ' ' << id << '\n';

        } else {

            std::cout << op << '\n';

        }

    }



    return 0;

}
