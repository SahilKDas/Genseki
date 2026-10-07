#include "../src/review/alpha_process.hpp"
#include <windows.h>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <filesystem>
using namespace genseki;
using namespace genseki::review;
void require(bool value,const char* message){if(!value){std::cerr<<message<<'\n';std::exit(1);}}
int main(int argc,char** argv){
    require(argc==2,"fake executable required");
    for(const auto* mode:{L"normal",L"options",L"illegal",L"malformed",L"exit",L"hang"}){
        SetEnvironmentVariableW(L"GENSEKI_REVIEW_FAKE_MODE",mode);
        AlphaProcess engine;auto started=engine.start(argv[1],{});
        if(std::wstring_view(mode)==L"options"){require(!started,"ineffective options rejected");continue;}
        require(bool(started),"test process starts");
        std::stop_source stop;
        auto begin=std::chrono::steady_clock::now();
        std::jthread cancel([&](std::stop_token token){
            if(std::wstring_view(mode)!=L"hang")return;
            for(int i=0;i<10&&!token.stop_requested();++i)std::this_thread::sleep_for(std::chrono::milliseconds(10));
            if(!token.stop_requested())stop.request_stop();
        });
        auto reply=engine.search(Board{},1000,stop.get_token());
        cancel.request_stop();
        if(std::wstring_view(mode)==L"normal")require(reply&&reply->score==17,"valid reply accepted");
        else require(!reply,"invalid or interrupted transport rejected");
        require(std::chrono::steady_clock::now()-begin<std::chrono::seconds(2),"bounded shutdown and cancellation");
    }
    SetEnvironmentVariableW(L"GENSEKI_REVIEW_FAKE_MODE",nullptr);
    require(resources_available(),"native resource guard preflight headroom");
    SetEnvironmentVariableW(L"GENSEKI_REVIEW_FAKE_MODE",L"burn");
    auto path=std::filesystem::absolute(argv[1]);auto command=L"\""+path.wstring()+L"\"";
    STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION process{};
    require(CreateProcessW(path.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,path.parent_path().c_str(),&startup,&process),"native heavy fixture launched");
    SetEnvironmentVariableW(L"GENSEKI_REVIEW_FAKE_MODE",nullptr);
    Sleep(150);(void)resources_available();Sleep(250);
    bool blocked=!resources_available();bool owned_allowed=resources_available(process.dwProcessId);
    TerminateProcess(process.hProcess,0);WaitForSingleObject(process.hProcess,1000);CloseHandle(process.hThread);CloseHandle(process.hProcess);
    require(blocked,"real CPU-heavy project exe blocks review");
    require(owned_allowed,"owned exe does not falsely block its own review");
    std::cout<<"Review transport tests passed\n";
}
