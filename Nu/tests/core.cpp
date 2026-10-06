#include "search.hpp"
#include <iostream>
#include <random>
void check(bool value){if(!value)throw std::runtime_error("test failure");}
int brute(nu::State& state,int depth,int ply=0) {
    auto result=state.board.result();
    if(result!=nu::GameResult::ongoing) {
        if(result==nu::GameResult::draw)return 0;
        return ((result==nu::GameResult::white_win)==(state.board.side_to_move()==nu::Color::white))?100000-ply:-100000+ply;
    }
    if(!depth)return state.evaluate();
    int best=-100001;
    for(auto move:state.board.legal_moves()){nu::Applied apply(state,move);best=std::max(best,-brute(state,depth-1,ply+1));}
    return best;
}
int main(){
    for(unsigned width:{64u,128u})for(unsigned version:{3u,4u}) {
        nu::Model model(width);model.feature_schema=version;nu::State state(model);std::mt19937 rng(123);
        for(unsigned game=0;game<12;++game) {
            state=nu::State(model);std::vector<nu::State::Undo> undo;
            for(unsigned ply=0;ply<100&&!state.board.is_terminal();++ply){auto moves=state.board.legal_moves();auto move=moves[rng()%moves.size()];
                auto checked=state.board;auto checked_undo=checked.make_move(move);check(bool(checked_undo));
                undo.push_back(state.make(move,true));check(state.board.position_string()==checked.position_string());check(state.equivalent());
#if defined(__GNUC__) && defined(__x86_64__)
                if(__builtin_cpu_supports("sse4.1"))check(state.accumulator.vectorized(model,state.board.side_to_move())==state.accumulator.scalar(model,state.board.side_to_move()));
#endif
            }
            while(!undo.empty()){state.unmake(undo.back());undo.pop_back();check(state.equivalent());}
            check(state.board.position_string()==nu::Board{}.position_string());
        }
        nu::Search search(1);auto first=search.run(state,2,10000);auto second=search.run(state,2,10000);
        check(first.move==second.move&&first.score==second.score);check(state.board.is_legal(first.move));
        auto fallback=search.run(state,64,0,12);check(state.board.is_legal(fallback.move));check(fallback.depth==0);
        auto parallel=search.run(state,2,10000,4);check(parallel.score==first.score);check(state.equivalent());
        for(unsigned ply=0;ply<8;++ply){auto moves=state.board.legal_moves();state.make(moves[rng()%moves.size()]);}
        auto before=state.board.position_string();int exact=brute(state,2);
        nu::Search fresh(1);auto pvs=fresh.run(state,2,60000);check(pvs.depth==2&&pvs.score==exact);
        nu::Search collisions(1,1);auto collided=collisions.run(state,2,60000);check(collided.depth==2&&collided.score==exact);
        check(state.board.position_string()==before&&state.equivalent());
    }
    nu::Board board;check(board.perft(0)==1);check(board.perft(1)==4);check(board.perft(2)==96);check(board.perft(3)==1440);
    std::vector<std::uint64_t> repetitions(12,13);repetitions.back()=41;
    repetitions[3]=41;repetitions[7]=41;check(nu::match_repetition(repetitions));
    repetitions.pop_back();check(!nu::match_repetition(repetitions));
    repetitions.resize(12,41);repetitions[7]=13;repetitions[9]=41;check(!nu::match_repetition(repetitions));
    for(unsigned width:{64u,128u}) {
        nu::Model nonlinear(width);nonlinear.head=32;nonlinear.head_weights.resize(64*width);nonlinear.head_bias.resize(32);nonlinear.output.resize(32);
        for(unsigned i=0;i<nonlinear.head_weights.size();++i)nonlinear.head_weights[i]=std::int16_t(int(i%31)-15);
        for(unsigned i=0;i<32;++i){nonlinear.head_bias[i]=int(i)-16;nonlinear.output[i]=std::int16_t(3*int(i)-48);}
        nu::Accumulator accumulator(nonlinear);
        for(unsigned i=0;i<width;++i){accumulator.sums[0][i]=int(i*7)-20;accumulator.sums[1][i]=int(i*11)-90;}
        check(accumulator.scalar(nonlinear,nu::Color::white)==-accumulator.scalar(nonlinear,nu::Color::black));
#if defined(__GNUC__) && defined(__x86_64__)
        if(__builtin_cpu_supports("sse4.1"))check(accumulator.vectorized(nonlinear,nu::Color::white)==accumulator.scalar(nonlinear,nu::Color::white));
#endif
        check(accumulator.score(nonlinear,nu::Color::white)==-accumulator.score(nonlinear,nu::Color::black));
        for(unsigned j=0;j<32;++j)for(unsigned k=0;k<2*width;++k)nonlinear.head_weights[j*2*width+k]=k<width?32767:-32768;
        accumulator.sums[0].assign(width,256);accumulator.sums[1].assign(width,0);
#if defined(__GNUC__) && defined(__x86_64__)
        if(__builtin_cpu_supports("sse4.1"))check(accumulator.vectorized(nonlinear,nu::Color::white)==accumulator.scalar(nonlinear,nu::Color::white));
#endif
    }
    nu::Model exact_model;exact_model.feature_schema=4;nu::State exact_state(exact_model);std::mt19937 exact_rng(197);
    for(unsigned ply=0;ply<12;++ply){auto moves=exact_state.legal();exact_state.make(moves[exact_rng()%moves.size()],true);check(exact_state.equivalent());}
    auto exact_before=exact_state.board.position_string();auto generated=exact_state.legal().front();
    genseki::nu_generation_check=[](void*){throw std::runtime_error("test cancellation");};
    bool cancelled=false;
    try{exact_state.make(generated,true);}catch(const std::runtime_error&){cancelled=true;}
    genseki::nu_generation_check=nullptr;genseki::nu_generation_context=nullptr;
    check(cancelled&&exact_state.board.position_string()==exact_before&&exact_state.equivalent());
    auto bridge=nu::Board::from_position_string("G1|w|8|4|4|0,0=wQ;1,0=wA1;2,0=bQ");check(bool(bridge));
    auto bridge_features=nu::features(*bridge,3);
    check(std::binary_search(bridge_features[0].begin(),bridge_features[0].end(),6213));
    check(std::binary_search(bridge_features[0].begin(),bridge_features[0].end(),6468));
    check(std::binary_search(bridge_features[0].begin(),bridge_features[0].end(),6805));
    auto stack_bridge=nu::Board::from_position_string("G1|w|8|4|4|0,0=wQ;1,0=wA1,bB1;2,0=bQ");check(bool(stack_bridge));
    auto stack_features=nu::features(*stack_bridge,3);
    check(std::binary_search(stack_features[0].begin(),stack_features[0].end(),6305));
    check(std::binary_search(stack_features[0].begin(),stack_features[0].end(),6471));
    auto tactical=nu::Board::from_position_string("G1|w|46|23|23|-2,3=bA2;-2,4=wA2;-2,5=bS2;-1,2=bG3;0,-3=wA3;0,-2=bA3;0,-1=wG1,bB1;0,0=bG2;0,1=bS1;1,-2=bQ;1,-1=wG2;1,0=wQ;2,-4=wB2;2,-3=wS2;2,-2=wA1;2,0=bA1;3,0=bG1,bB2;4,0=wS1;5,-1=wB1");
    check(bool(tactical));nu::Model model;nu::State mate(model,*tactical);nu::Search search(1);
    auto win=search.run(mate,2,10000);check(win.score==99999);
    auto undo=mate.make(win.move);check(mate.board.result()==nu::GameResult::white_win);
    mate.unmake(undo);check(mate.equivalent());
    auto defense_string=tactical->position_string();auto leaf=defense_string.find("0,-3=wA3;");check(leaf!=std::string::npos);
    defense_string.replace(leaf,std::string("0,-3=wA3;").size(),"5,-2=wA3;");
    auto defense_position=nu::Board::from_position_string(defense_string);check(bool(defense_position));
    auto defender=defense_position->with_side_to_move(nu::Color::black);nu::State defensive(model,defender);
    std::vector<nu::Move> safe;
    for(auto move:defender.legal_moves()) {
        auto candidate=defender;(void)candidate.make_generated_move(move);
        bool loses=candidate.result()==nu::GameResult::white_win;
        if(!candidate.is_terminal())for(auto reply:candidate.legal_moves()) {
            auto response=candidate;(void)response.make_generated_move(reply);loses|=response.result()==nu::GameResult::white_win;
        }
        if(!loses)safe.push_back(move);
    }
    check(!safe.empty());nu::Search defensive_search(1);nu::SearchOptions threat_options;threat_options.threat_plies=2;
    auto defense=defensive_search.run(defensive,1,10000,1,nullptr,threat_options);
    check(std::find(safe.begin(),safe.end(),defense.move)!=safe.end());check(defensive.equivalent());
    nu::SearchOptions reduced;reduced.lmr=true;
    auto reduced_win=search.run(mate,2,10000,1,nullptr,reduced);check(reduced_win.score==99999);
    auto restored=search.run(mate,2,10000);check(restored.score==99999);
    nu::Board pv_board=defender;
    for(auto move:defense.pv){check(pv_board.is_legal(move));(void)pv_board.make_generated_move(move);}
    auto pass_board=nu::Board::from_position_string("G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ");check(bool(pass_board));
    check(pass_board->legal_moves().size()==1&&pass_board->legal_moves().front().kind==nu::MoveKind::pass);
    nu::State pass_state(model,*pass_board);nu::Search pass_search(1);
    auto pass=pass_search.run(pass_state,3,10000);check(pass.move.kind==nu::MoveKind::pass&&pass.score==brute(pass_state,3));
    std::atomic<bool> entered{false};nu::SearchResult interrupted;
    std::jthread worker([&]{interrupted=search.run(mate,64,1000,1,&entered);});
    while(!entered.load())std::this_thread::yield();
    search.cancel();worker.join();
    check(mate.board.is_legal(interrupted.move));check(mate.equivalent());
    std::cout<<"Nu state/search/perft tests passed\n";
}
