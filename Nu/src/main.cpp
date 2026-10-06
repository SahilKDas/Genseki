#include "search.hpp"
#include <iostream>
#include <sstream>
#include <memory>
#include <cmath>
#include <charconv>

static unsigned parse_unsigned(std::string_view text) {
    unsigned value=0;
    const auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),value);
    if(error!=std::errc{}||end!=text.data()+text.size())throw std::runtime_error("invalid unsigned integer");
    return value;
}

int main(int argc,char** argv) {
    try {
        nu::Model model;
        for(int i=1;i<argc;++i)if(std::string(argv[i])=="--model"&&i+1<argc)model.load(argv[++i]);
        for(int i=1;i<argc;++i)if(std::string(argv[i])=="--feature-schema"&&i+1<argc) {
            auto version=parse_unsigned(argv[++i]);if(version<1||version>4)throw std::runtime_error("invalid feature schema");
            if(model.identity!="untrained-seed-1701")throw std::runtime_error("cannot override trained model schema");
            model.feature_schema=unsigned(version);
        }
        if(argc>2&&std::string(argv[1])=="perft") {
            nu::Board board;auto depth=parse_unsigned(argv[2]);if(depth>16)throw std::runtime_error("perft depth exceeds 16");
            if(argc>3&&std::string(argv[3])=="--divide"&&depth) {
                for(auto move:board.legal_moves()) {
                    auto notation=board.uhp_move_string(move);auto undo=board.make_move(move);
                    std::cout<<*notation<<": "<<board.perft(unsigned(depth-1))<<'\n';board.unmake_move(*undo);
                }
            }else std::cout<<board.perft(unsigned(depth))<<'\n';
            return 0;
        }
        if(argc>2&&std::string(argv[1])=="replay") {
            std::ifstream file(argv[2]);if(!file)throw std::runtime_error("cannot open replay");
            nu::Board board;std::string move_text;
            while(std::getline(file,move_text)) {
                if(!move_text.empty()&&move_text.back()=='\r')move_text.pop_back();
                if(move_text.empty())continue;
                auto move=board.parse_uhp_move(move_text);
                if(!move||!board.play(*move)) {
                    std::cerr<<"illegal ply "<<board.ply()+1<<": "<<move_text<<'\n'<<board.position_string()<<'\n';return 1;
                }
            }
            std::cout<<board.game_string()<<'\n';return 0;
        }
        if(argc>2&&std::string(argv[1])=="stress") {
            auto games=parse_unsigned(argv[2]);if(!games||games>10000)throw std::runtime_error("invalid stress count");
            std::mt19937 rng(1701);unsigned plies=0;
            for(unsigned game=0;game<games;++game) {
                nu::State state(model);std::vector<nu::State::Undo> undo;
                for(unsigned ply=0;ply<160&&!state.board.is_terminal();++ply) {
                    auto moves=state.board.legal_moves();undo.push_back(state.make(moves[rng()%moves.size()]));++plies;
                    auto roundtrip=nu::Board::from_position_string(state.board.position_string());
                    if(!state.equivalent()||!roundtrip||roundtrip->position_string()!=state.board.position_string())throw std::runtime_error("state integrity failure");
                }
                while(!undo.empty()){state.unmake(undo.back());undo.pop_back();if(!state.equivalent())throw std::runtime_error("undo integrity failure");}
            }
            std::cout<<"verified "<<plies<<" random plies\n";return 0;
        }
        nu::State state(model);std::vector<nu::State::Undo> history;
        unsigned threads=1,mib=16;auto search=std::make_unique<nu::Search>(mib);nu::SearchResult last;
        nu::SearchOptions search_options;
        (void)state.legal();
        bool pondering=false;std::jthread background;std::atomic<bool> entered{false};
        auto stop_ponder=[&]{if(background.joinable()){search->cancel();background.join();}};
        std::cout<<"id Nu 0.1\n\nok\n"<<std::flush;
        std::string line;
        while(std::getline(std::cin,line)) {
            stop_ponder();
            std::istringstream input(line);std::string command;input>>command;
            std::string argument;std::getline(input,argument);if(!argument.empty())argument.erase(0,1);
            try {
                if(command=="exit")break;
                if(command=="info")std::cout<<"id Nu 0.1\n\n";
                else if(command=="newgame") {
                    auto parsed=nu::Board::from_game_string(argument.empty()?"Base":argument);
                    if(!parsed)throw std::runtime_error(parsed.error());
                    state=nu::State(model);history.clear();
                    for(auto move:parsed->history())history.push_back(state.make(move));
                    (void)state.legal();
                    std::cout<<state.board.game_string()<<'\n';
                }else if(command=="play") {
                    auto move=state.board.parse_uhp_move(argument);if(!move)throw std::runtime_error(move.error());
                    history.push_back(state.make(*move));std::cout<<state.board.game_string()<<'\n';
                    (void)state.legal();
                }else if(command=="undo") {
                    unsigned count=argument.empty()?1:parse_unsigned(argument);
                    if(!count||count>history.size())throw std::runtime_error("invalid undo count");
                    while(count--) {state.unmake(history.back());history.pop_back();}std::cout<<state.board.game_string()<<'\n';
                }else if(command=="validmoves") {
                    bool first=true;for(auto move:state.board.legal_moves()){if(!first)std::cout<<';';first=false;std::cout<<*state.board.uhp_move_string(move);}std::cout<<'\n';
                }else if(command=="bestmove") {
                    std::istringstream args(argument);std::string mode;args>>mode;unsigned depth=64;double ms=230;
                    if(mode=="depth") {if(!(args>>depth)||!depth||depth>64)throw std::runtime_error("invalid depth");ms=60000;}
                    else if(mode=="time") {
                        std::string time;args>>time;std::replace(time.begin(),time.end(),':',' ');std::istringstream t(time);double h,m,s;
                        if(!(t>>h>>m>>s)||h<0||m<0||m>=60||s<0||s>=60)throw std::runtime_error("invalid time");
                        ms=(h*3600+m*60+s)*1000;
                    }else if(mode=="depthorseconds") {double seconds;if(!(args>>depth>>seconds)||!depth||depth>64)throw std::runtime_error("invalid limit");ms=seconds*1000;}
                    else throw std::runtime_error("expected depth or time");
                    if(!std::isfinite(ms)||ms<0||ms>60000)throw std::runtime_error("invalid time budget");
                    last=search->run(state,depth,ms,threads,nullptr,search_options);std::cout<<*state.board.uhp_move_string(last.move)<<'\n';
                }else if(command=="options") {
                    if(argument.empty())std::cout<<"Threads;int;"<<threads<<";1;1;12\nTableMiB;int;"<<mib<<";16;1;256\nBackgroundPondering;bool;"<<(pondering?"True":"False")<<";False\nThreatPlies;int;"<<search_options.threat_plies<<";0;0;4\nLateMoveReductions;bool;"<<(search_options.lmr?"True":"False")<<";False\nProfile;bool;"<<(search_options.profile?"True":"False")<<";False\n";
                    else {std::istringstream a(argument);std::string name;unsigned value;a>>name;
                        if(name=="set")a>>name;
                        if(name=="get") {a>>name;
                            if(name=="Threads")std::cout<<"Threads;int;"<<threads<<";1;1;12\n";
                            else if(name=="TableMiB")std::cout<<"TableMiB;int;"<<mib<<";16;1;256\n";
                            else if(name=="BackgroundPondering")std::cout<<"BackgroundPondering;bool;"<<(pondering?"True":"False")<<";False\n";
                            else if(name=="ThreatPlies")std::cout<<"ThreatPlies;int;"<<search_options.threat_plies<<";0;0;4\n";
                            else if(name=="LateMoveReductions"||name=="Profile")std::cout<<name<<";bool;"<<((name=="Profile"?search_options.profile:search_options.lmr)?"True":"False")<<";False\n";
                            else throw std::runtime_error("unknown option");
                            std::cout<<"ok\n"<<std::flush;continue;
                        }
                        if(name=="BackgroundPondering"||name=="LateMoveReductions"||name=="Profile") {
                            std::string boolean;a>>boolean;
                            if(boolean!="True"&&boolean!="False")throw std::runtime_error("invalid boolean");
                            if(name=="BackgroundPondering")pondering=boolean=="True";
                            else if(name=="Profile")search_options.profile=boolean=="True";
                            else search_options.lmr=boolean=="True";
                            std::cout<<name<<";bool;"<<boolean<<";False\nok\n"<<std::flush;continue;
                        }
                        if(!(a>>value))throw std::runtime_error("invalid option");
                        if(name=="Threads"&&value>=1&&value<=12)threads=value;
                        else if(name=="TableMiB"&&value>=1&&value<=256){mib=value;search=std::make_unique<nu::Search>(mib);}
                        else if(name=="ThreatPlies"&&value<=4)search_options.threat_plies=value;
                        else throw std::runtime_error("unknown option or out of range");
                        if(name=="Threads")std::cout<<"Threads;int;"<<threads<<";1;1;12\n";
                        else if(name=="TableMiB")std::cout<<"TableMiB;int;"<<mib<<";16;1;256\n";
                        else std::cout<<"ThreatPlies;int;"<<search_options.threat_plies<<";0;0;4\n";
                    }
                }else if(command=="nu-feature-schema")std::cout<<model.feature_schema<<'\n';
                else if(command=="nu-moveid") {
                    auto move=state.board.parse_uhp_move(argument);if(!move)throw std::runtime_error(move.error());
                    std::cout<<nu::move_notation(*move)<<'\n';
                }
                else if(command=="nu-matchdraw")std::cout<<(state.repetition()?"True":"False")<<'\n';
                else if(command=="nu-profile")std::cout<<"features_ns "<<last.profile.features_ns<<" generation_ns "<<last.profile.generation_ns<<" ordering_ns "<<last.profile.ordering_ns<<" tt_ns "<<last.profile.tt_ns<<'\n';
                else if(command=="nu-repetition") {
                    auto target=nu::repetition_hash(state.board);nu::Board replay;
                    unsigned count=nu::repetition_hash(replay)==target;
                    for(auto move:state.board.history()) {
                        auto applied=replay.make_generated_move(move);(void)applied;
                        count+=nu::repetition_hash(replay)==target;
                    }
                    std::cout<<std::max(count,1u)<<'\n';
                }else if(command=="nu-loadposition") {
                    auto parsed=nu::Board::from_position_string(argument);if(!parsed)throw std::runtime_error(parsed.error());
                    state=nu::State(model,*parsed);history.clear();std::cout<<state.board.position_string()<<'\n';
                }else if(command=="nu-position")std::cout<<state.board.position_string()<<'\n';
                else if(command=="nu-features") {
                    for(unsigned p=0;p<2;++p){std::cout<<p<<':';for(auto id:state.active[p])std::cout<<' '<<id;std::cout<<'\n';}
                    std::cout<<"score "<<state.evaluate()<<'\n';
                }else if(command=="nu-searchinfo") {
                    std::cout<<"depth "<<last.depth<<" nodes "<<last.nodes<<" score "<<last.score<<'\n';
                    nu::Board replay=state.board;std::cout<<"pv";
                    for(auto move:last.pv) {
                        auto notation=replay.uhp_move_string(move);
                        if(!notation||!replay.is_legal(move))break;
                        std::cout<<';'<<*notation;
                        auto applied=replay.play(move);if(!applied)break;
                    }
                    std::cout<<'\n';
                }
                else throw std::runtime_error("unknown command");
            }catch(const std::exception& error){std::cout<<"err "<<error.what()<<'\n';}
            std::cout<<"ok\n"<<std::flush;
            if(pondering&&!state.board.is_terminal()) {
                entered=false;
                background=std::jthread([&,snapshot=state]{try{search->run(snapshot,64,1000,threads,&entered,search_options);}catch(...){entered=true;}});
                while(!entered.load())std::this_thread::yield();
            }
        }
        stop_ponder();
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
