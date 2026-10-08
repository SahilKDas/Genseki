#include "../src/review/job_lock.hpp"
#include <chrono>
#include <iostream>
#include <thread>
int main(int argc,char** argv){
    if(argc!=3)return 2;
    genseki::review::FileJobLock lock;
    if(!lock.acquire(argv[2]))return 75;
    std::cout<<"owned"<<std::endl;
    if(std::string_view(argv[1])=="hold")std::this_thread::sleep_for(std::chrono::seconds(30));
    return 0;
}
