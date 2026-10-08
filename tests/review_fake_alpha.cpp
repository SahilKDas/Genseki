#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <atomic>

int main() {
    const char* env=std::getenv("GENSEKI_REVIEW_FAKE_MODE");
    const std::string mode=env?env:"normal";
    if(mode=="burn"){std::atomic_uint counter{0};for(;;)counter.fetch_add(1,std::memory_order_relaxed);}
    std::cout<<"id Review test process\nok\n"<<std::flush;
    std::string command;
    while(std::getline(std::cin,command)) {
        if(command.starts_with("options get ")) {
            auto name=command.substr(12);
            auto value=name=="NumThreads"?"1":name=="TableSizeMiB"?"32":name=="Evaluator"?"gen1":"False";
            std::cout<<name<<";string;"<<(mode=="options"?"wrong":value)<<"\n";
        }else if(command.starts_with("newgame ")) {
            std::cout<<command.substr(8)<<'\n';
        }else if(command.starts_with("alpha-search ")) {
            if(mode=="exit")return 0;
            if(mode=="hang")std::this_thread::sleep_for(std::chrono::seconds(30));
            if(mode=="illegal")std::cout<<"score 0 static 0 move wQ missing\n";
            else if(mode=="malformed")std::cout<<"score nonsense\n";
            else std::cout<<"score 17 static 0 move wS1\n";
        }
        std::cout<<"ok\n"<<std::flush;
    }
}
