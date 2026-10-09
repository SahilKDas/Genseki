#include "search.hpp"
#include <iostream>

void check(bool value){if(!value)throw std::runtime_error("search challenger regression");}
int main() {
    nu::Model model;model.feature_schema=8;
    nu::State prefix(model);
    auto place=[](nu::State& s,nu::Bug bug,unsigned id,int q,int r) {
        nu::Move move{nu::MoveKind::placement,std::nullopt,{std::int16_t(q),std::int16_t(r)},
                      {s.board.side_to_move(),bug,std::uint8_t(id)}};
        return s.make(move);
    };
    place(prefix,nu::Bug::ant,0,0,0);place(prefix,nu::Bug::ant,0,1,0);
    place(prefix,nu::Bug::queen,0,-1,0);place(prefix,nu::Bug::queen,0,2,0);
    for(auto [bug,q]:{std::pair{nu::Bug::beetle,-2},std::pair{nu::Bug::grasshopper,-3},std::pair{nu::Bug::spider,-4}}) {
        place(prefix,bug,0,q,0);place(prefix,bug,0,1-q,0);
    }
    nu::Move quiet{nu::MoveKind::placement,std::nullopt,{-1,-1},{nu::Color::white,nu::Bug::ant,1}};
    check(prefix.board.is_legal(quiet)&&nu::Search::reduction_safe(prefix.board,quiet));
    auto beetle_placement=quiet;beetle_placement.piece.bug=nu::Bug::beetle;
    check(prefix.board.is_legal(beetle_placement)&&!nu::Search::reduction_safe(prefix.board,beetle_placement));
    auto queen_move=quiet;queen_move.kind=nu::MoveKind::movement;queen_move.from=nu::Hex{-1,0};
    queen_move.piece={nu::Color::white,nu::Bug::queen,0};
    check(!nu::Search::reduction_safe(prefix.board,queen_move));
    auto calm=nu::Board::from_position_string("G1|w|12|6|6|0,0=wQ;1,-1=wS1;1,0=wA1;2,-1=wB1;3,-1=bQ;4,-1=bA1");
    check(bool(calm));auto calm_moves=calm->legal_moves();
    auto departing=std::find_if(calm_moves.begin(),calm_moves.end(),[](auto move){return move.from==nu::Hex{1,0};});
    check(departing!=calm_moves.end()&&!nu::Search::reduction_safe(*calm,*departing));
    auto attacking=quiet;attacking.to={3,-2};
    check(!nu::Search::reduction_safe(*calm,attacking));
    auto first=prefix,second=prefix;
    place(first,nu::Bug::ant,1,-1,-1);place(first,nu::Bug::ant,1,2,1);
    place(first,nu::Bug::spider,1,-2,-1);place(first,nu::Bug::spider,1,3,1);
    place(second,nu::Bug::spider,1,-2,-1);place(second,nu::Bug::spider,1,3,1);
    place(second,nu::Bug::ant,1,-1,-1);place(second,nu::Bug::ant,1,2,1);
    check(first.hash==second.hash&&first.history_key!=second.history_key);
    check(first.context_key()==second.context_key()&&first.equivalent()&&second.equivalent());
    auto loaded_board=nu::Board::from_position_string(first.board.position_string());check(bool(loaded_board));
    nu::State short_history(model,*loaded_board);
    check(short_history.hash==first.hash&&short_history.context_key()!=first.context_key());
    auto before_context=first.context_key();
    auto reversible_move=std::find_if(first.legal().begin(),first.legal().end(),[](auto move){return move.kind==nu::MoveKind::movement;});
    check(reversible_move!=first.legal().end());auto movement=*reversible_move;
    auto context_undo=first.make(movement,true);auto other_undo=second.make(movement);
    check(first.context_key()==second.context_key()&&first.context_key()!=before_context&&first.equivalent());
    first.unmake(context_undo);second.unmake(other_undo);
    check(first.context_key()==before_context&&first.equivalent());
    nu::Search transpositions(1);
    auto first_score=transpositions.run(first,2,10000).score;
    check(transpositions.run(second,2,10000).score==first_score);
    nu::Search full_quiet(1),reduced_quiet(1);nu::SearchOptions quiet_settings;
    quiet_settings.root_pvs=true;quiet_settings.lmr=true;
    auto quiet_reference=full_quiet.run(prefix,4,10000);
    auto quiet_result=reduced_quiet.run(prefix,4,10000,8,nullptr,quiet_settings);
    check(quiet_reference.depth==4&&quiet_result.depth==4&&quiet_reference.score==quiet_result.score&&prefix.equivalent());
    nu::State state(model);std::mt19937 rng(1901);
    for(unsigned ply=0;ply<100&&!state.board.is_terminal();++ply) {
        auto legal=state.legal();
        for(auto move:legal)check(state.board.uhp_move_string(move)==state.board.generated_uhp_move_string(move));
        (void)state.make(legal[rng()%legal.size()],true);
    }
    auto tactical=nu::Board::from_position_string("G1|w|46|23|23|-2,3=bA2;-2,4=wA2;-2,5=bS2;-1,2=bG3;0,-3=wA3;0,-2=bA3;0,-1=wG1,bB1;0,0=bG2;0,1=bS1;1,-2=bQ;1,-1=wG2;1,0=wQ;2,-4=wB2;2,-3=wS2;2,-2=wA1;2,0=bA1;3,0=bG1,bB2;4,0=wS1;5,-1=wB1");
    check(bool(tactical));nu::State mate(model,*tactical);nu::Search search(1);
    for(auto move:tactical->legal_moves())check(!nu::Search::reduction_safe(*tactical,move));
    for(unsigned mask=0;mask<16;++mask) {
        nu::SearchOptions options;options.deadline_guard=true;
        options.threat_plies=(mask&1)?1:0;options.lmr=mask&2;options.cooperative_ordering=mask&4;
        options.root_pvs=mask&8;options.root_pv_first=options.root_pvs;
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
    settings.threat_plies=2;
    defensive=search.run(defense,4,10000,8,nullptr,settings);
    undo=defense.make(defensive.move,true);
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
        for(unsigned threads:{1u,2u,8u})for(bool first:{false,true}) {
            nu::Search accelerated(1);nu::SearchOptions options;options.root_pvs=true;options.deadline_guard=true;
            options.root_pv_first=first;
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
