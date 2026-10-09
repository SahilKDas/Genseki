#include "search.hpp"
#include <iostream>

void check(bool value){if(!value)throw std::runtime_error("search challenger regression");}
int main() {
    nu::Model model;model.feature_schema=8;
    nu::State state(model);std::mt19937 rng(1901);
    for(unsigned ply=0;ply<100&&!state.board.is_terminal();++ply) {
        auto legal=state.legal();
        for(auto move:legal)check(state.board.uhp_move_string(move)==state.board.generated_uhp_move_string(move));
        (void)state.make(legal[rng()%legal.size()],true);
    }
    auto tactical=nu::Board::from_position_string("G1|w|46|23|23|-2,3=bA2;-2,4=wA2;-2,5=bS2;-1,2=bG3;0,-3=wA3;0,-2=bA3;0,-1=wG1,bB1;0,0=bG2;0,1=bS1;1,-2=bQ;1,-1=wG2;1,0=wQ;2,-4=wB2;2,-3=wS2;2,-2=wA1;2,0=bA1;3,0=bG1,bB2;4,0=wS1;5,-1=wB1");
    check(bool(tactical));nu::State mate(model,*tactical);nu::Search search(1);
    for(unsigned mask=0;mask<16;++mask) {
        nu::SearchOptions options;options.deadline_guard=true;
        options.threat_plies=(mask&1)?1:0;options.lmr=mask&2;options.cooperative_ordering=mask&4;
        options.root_pvs=mask&8;
        auto result=search.run(mate,3,10000,options.root_pvs?8:1,nullptr,options);
        check(result.score==99999);auto undo=mate.make(result.move,true);
        check(mate.board.result()==nu::GameResult::white_win);mate.unmake(undo);check(mate.equivalent());
    }
    auto text=tactical->position_string();auto leaf=text.find("0,-3=wA3;");
    text.replace(leaf,std::string("0,-3=wA3;").size(),"5,-2=wA3;");
    auto defender=nu::Board::from_position_string(text);check(bool(defender));
    nu::State defense(model,defender->with_side_to_move(nu::Color::black));
    nu::SearchOptions settings;settings.deadline_guard=true;settings.cooperative_ordering=true;
    settings.threat_plies=1;settings.lmr=true;
    auto defensive=search.run(defense,2,10000,1,nullptr,settings);
    auto undo=defense.make(defensive.move,true);
    for(auto reply:defense.legal()) {
        auto response=defense.make(reply,true);check(defense.board.result()!=nu::GameResult::white_win);defense.unmake(response);
    }
    defense.unmake(undo);check(defense.equivalent());
    for(unsigned threads:{1u,8u,12u})for(unsigned repeat=0;repeat<8;++repeat) {
        auto result=search.run(defense,64,5,threads,nullptr,settings);
        check(defense.board.is_legal(result.move)&&defense.equivalent());
        check(result.timing.total_ns>=result.timing.setup_ns);
    }
    nu::State ordinary(model);
    for(unsigned ply=0;ply<24&&!ordinary.board.is_terminal();++ply) {
        auto legal=ordinary.legal();(void)ordinary.make(legal[rng()%legal.size()],true);
        if(ply%4!=3)continue;
        nu::Search reference(1);auto expected=reference.run(ordinary,2,10000);
        for(unsigned threads:{1u,2u,8u}) {
            nu::Search accelerated(1);nu::SearchOptions options;options.root_pvs=true;options.deadline_guard=true;
            auto actual=accelerated.run(ordinary,2,10000,threads,nullptr,options);
            check(actual.score==expected.score&&ordinary.board.is_legal(actual.move)&&ordinary.equivalent());
            auto made=ordinary.make(actual.move,true);
            if(!ordinary.board.is_terminal()) {
                nu::Search child_search(1);auto child=child_search.run(ordinary,1,10000).score;
                check(-child==expected.score);
            }
            ordinary.unmake(made);check(ordinary.equivalent());
        }
    }
    std::atomic<bool> entered=false;nu::SearchResult cancelled;
    std::jthread runner([&]{cancelled=search.run(defense,64,1000,8,&entered,settings);});
    while(!entered)std::this_thread::yield();
    search.cancel();runner.join();
    check(defense.board.is_legal(cancelled.move)&&defense.equivalent());
    std::cout<<"search challenger tests passed\n";
}
