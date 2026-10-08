#include "genseki/review/review.hpp"
#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
volatile std::sig_atomic_t interrupted=0;
void interrupt(int){interrupted=1;}
}
int main(int argc,char** argv) {
#ifdef _WIN32
    SetPriorityClass(GetCurrentProcess(),IDLE_PRIORITY_CLASS);
#endif
    using namespace genseki::review;
    Settings settings;settings.engine=std::filesystem::path(argv[0]).parent_path()/"genseki.exe";
    std::filesystem::path input,output;bool facts_only=false;
    for(int i=1;i<argc;++i) {
        std::string arg=argv[i];
        if(arg=="--facts-only")facts_only=true;
        else if((arg=="--input"||arg=="--output"||arg=="--engine")&&i+1<argc){
            auto value=std::filesystem::path(argv[++i]);
            if(arg=="--input")input=value;else if(arg=="--output")output=value;else settings.engine=value;
        }else {std::cerr<<"Usage: genseki_review --input game.txt --output review.json [--engine engine.exe] [--facts-only]\n";return 2;}
    }
    if(input.empty()||output.empty()){std::cerr<<"A replay input and JSON output are required.\n";return 2;}
    std::error_code error;
    if(std::filesystem::file_size(input,error)>262144||error){std::cerr<<"Replay unavailable or too large.\n";return 2;}
    std::ifstream file(input,std::ios::binary);std::string replay(std::istreambuf_iterator<char>(file),{});
    while(!replay.empty()&&(replay.back()=='\n'||replay.back()=='\r'))replay.pop_back();
    if(!claim_job()){std::cerr<<"Review deferred: heavy-job slot unavailable.\n";return 1;}
    struct Release{~Release(){release_job();}} release;
    auto report=prepare(replay);if(!report){std::cerr<<report.error()<<'\n';return 2;}
    if(facts_only){report->status="facts_only";report->settings=settings;auto result=save(*report,output);return result?0:2;}
    std::signal(SIGINT,interrupt);std::signal(SIGTERM,interrupt);
    std::stop_source stop;
    std::jthread watcher([&](std::stop_token token){while(!token.stop_requested()){if(interrupted){stop.request_stop();return;}std::this_thread::sleep_for(std::chrono::milliseconds(20));}});
    auto result=analyse(std::move(*report),settings,stop.get_token(),[&](const Report& progress){
        auto written=save(progress,output);if(!written)stop.request_stop();
        std::cerr<<"Reviewed "<<progress.completed<<"/"<<progress.moves.size()<<" moves: "<<progress.status<<'\n';
    });
    watcher.request_stop();auto written=save(result,output);
    return written&&result.status=="complete"?0:1;
}
