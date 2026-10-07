#include "alpha_process.hpp"
#include <algorithm>
#include <sstream>
#ifdef _WIN32
#include <windows.h>
#endif
namespace genseki::review {
struct AlphaProcess::Impl {
#ifdef _WIN32
    HANDLE process=nullptr,input=nullptr,output=nullptr;
    ~Impl(){close();}
    void close(){
        if(input){CloseHandle(input);input=nullptr;}
        if(process){if(WaitForSingleObject(process,100)==WAIT_TIMEOUT){TerminateProcess(process,1);WaitForSingleObject(process,1000);}CloseHandle(process);process=nullptr;}
        if(output){CloseHandle(output);output=nullptr;}
    }
    std::expected<std::vector<std::string>,std::string> response(unsigned timeout,std::stop_token stop){
        auto deadline=GetTickCount64()+timeout;std::vector<std::string> lines;std::string line;std::size_t bytes=0;
        while(GetTickCount64()<deadline&&!stop.stop_requested()){
            DWORD available=0;if(!PeekNamedPipe(output,nullptr,0,nullptr,&available,nullptr))break;
            if(!available){if(WaitForSingleObject(process,0)!=WAIT_TIMEOUT)break;Sleep(2);continue;}
            char buffer[4096];DWORD read=0;if(!ReadFile(output,buffer,std::min<DWORD>(available,sizeof(buffer)),&read,nullptr))break;
            bytes+=read;if(bytes>262144)break;
            for(DWORD i=0;i<read;++i){
                if(buffer[i]=='\n'){
                    if(line=="ok")return lines;
                    if(line.starts_with("err ")||line.starts_with("invalidmove ")){close();return std::unexpected("The analysis engine rejected a review request.");}
                    if(!line.empty())lines.push_back(std::move(line));line.clear();
                }else if(buffer[i]!='\r')line+=buffer[i];
            }
        }
        close();return std::unexpected(stop.stop_requested()?"Review cancelled.":"The analysis engine stopped responding within its deadline.");
    }
    std::expected<std::vector<std::string>,std::string> command(const std::string& text,unsigned timeout,std::stop_token stop){
        if(!input||!output)return std::unexpected("The analysis engine is unavailable.");
        if(stop.stop_requested())return std::unexpected("Review cancelled.");
        auto line=text+'\n';DWORD written=0;
        if(line.size()>262144||!WriteFile(input,line.data(),DWORD(line.size()),&written,nullptr)||written!=line.size()){close();return std::unexpected("Could not contact the analysis engine.");}
        return response(timeout,stop);
    }
#endif
};
AlphaProcess::AlphaProcess():impl_(std::make_unique<Impl>()){}
AlphaProcess::~AlphaProcess()=default;
unsigned AlphaProcess::process_id()const {
#ifdef _WIN32
    return impl_->process?GetProcessId(impl_->process):0;
#else
    return 0;
#endif
}
std::expected<void,std::string> AlphaProcess::start(const std::filesystem::path& requested,std::stop_token stop){
#ifdef _WIN32
    std::error_code error;auto path=std::filesystem::absolute(requested,error);
    if(error||!std::filesystem::is_regular_file(path))return std::unexpected("The Alpha executable is unavailable. Board facts remain available.");
    SECURITY_ATTRIBUTES sa{sizeof(sa),nullptr,TRUE};HANDLE r=nullptr,w=nullptr,ir=nullptr,iw=nullptr;
    auto cleanup=[&]{for(auto h:{r,w,ir,iw})if(h)CloseHandle(h);};
    if(!CreatePipe(&r,&w,&sa,0)||!CreatePipe(&ir,&iw,&sa,0)||!SetHandleInformation(r,HANDLE_FLAG_INHERIT,0)||!SetHandleInformation(iw,HANDLE_FLAG_INHERIT,0)){cleanup();return std::unexpected("Could not create the analysis connection.");}
    auto err=CreateFileW(L"NUL",GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(err==INVALID_HANDLE_VALUE){cleanup();return std::unexpected("Could not isolate engine diagnostics.");}
    STARTUPINFOW si{};si.cb=sizeof(si);si.dwFlags=STARTF_USESTDHANDLES|STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;si.hStdInput=ir;si.hStdOutput=w;si.hStdError=err;
    PROCESS_INFORMATION pi{};auto cmd=L"\""+path.wstring()+L"\"";
    bool ok=CreateProcessW(path.c_str(),cmd.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW|BELOW_NORMAL_PRIORITY_CLASS,nullptr,path.parent_path().c_str(),&si,&pi);
    CloseHandle(err);CloseHandle(ir);ir=nullptr;CloseHandle(w);w=nullptr;
    if(!ok){cleanup();return std::unexpected("Could not launch the separate Alpha analysis engine.");}
    CloseHandle(pi.hThread);impl_->process=pi.hProcess;impl_->input=iw;impl_->output=r;
    auto ready=impl_->response(5000,stop);if(!ready)return std::unexpected(ready.error());
    for(auto [name,value]:std::vector<std::pair<std::string,std::string>>{{"BackgroundPondering","False"},{"RandomOpening","False"},{"NumThreads","1"},{"TableSizeMiB","32"}}){
        auto set=impl_->command("options set "+name+" "+value,1000,stop);if(!set)return std::unexpected(set.error());
        auto get=impl_->command("options get "+name,1000,stop);if(!get)return std::unexpected(get.error());
        bool matched=false;for(auto line:*get)if(line.starts_with(name+";")){auto p=line.find(';',name.size()+1);auto end=line.find(';',p+1);matched=p!=std::string::npos&&line.substr(p+1,end-p-1)==value;}
        if(!matched){impl_->close();return std::unexpected("Alpha did not apply the required resource options.");}
    }
    return {};
#else
    (void)requested;(void)stop;return std::unexpected("Alpha review requires Windows.");
#endif
}
std::expected<SearchAnswer,std::string> AlphaProcess::search(const Board& board,unsigned ms,std::stop_token stop){
#ifdef _WIN32
    auto loaded=impl_->command("newgame "+board.game_string(),1000,stop);if(!loaded)return std::unexpected(loaded.error());
    bool verified=false;for(auto line:*loaded)if(line.starts_with("Base;")){auto b=Board::from_game_string(line);verified=b&&b->position_string()==board.position_string();}
    if(!verified)return std::unexpected("Alpha and the rules core disagreed on the review position.");
    auto reply=impl_->command("alpha-search 8 "+std::to_string(std::clamp(ms,1u,2000u)),ms+150,stop);if(!reply)return std::unexpected(reply.error());
    for(auto line:*reply)if(line.starts_with("score ")){
        std::istringstream in(line);std::string a,b,c;int value=0,stat=0;in>>a>>value>>b>>stat>>c;
        if(!in||b!="static"||c!="move")break;
        std::string move;std::getline(in,move);if(!move.empty()&&move.front()==' ')move.erase(0,1);
        if(!board.parse_uhp_move(move))return std::unexpected("Alpha suggested an illegal move.");
        return SearchAnswer{move,value};
    }
    return std::unexpected("Alpha returned an unsupported diagnostic response.");
#else
    (void)board;(void)ms;(void)stop;return std::unexpected("Alpha review requires Windows.");
#endif
}
}
