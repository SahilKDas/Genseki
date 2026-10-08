#include "search.hpp"
#include <iostream>
#include <random>
#include <sstream>

void check(bool value){if(!value)throw std::runtime_error("hybrid test failure");}
int brute(nu::State& state,int depth,nu::SearchOptions options,unsigned ply=0) {
    auto result=state.board.result();
    if(result!=nu::GameResult::ongoing) {
        if(result==nu::GameResult::draw)return 0;
        return ((result==nu::GameResult::white_win)==(state.board.side_to_move()==nu::Color::white))?100000-int(ply):-100000+int(ply);
    }
    if(state.repetition())return 0;
    if(!depth)return nu::Search::evaluate(state,options);
    int best=-100001;
    for(auto move:state.legal()){nu::Applied applied(state,move);best=std::max(best,-brute(state,depth-1,options,ply+1));}
    return best;
}
int main() {
    nu::Model model;nu::State state(model);nu::SearchOptions on;on.hybrid=true;
    auto control=nu::Board::from_position_string("G1|w|8|4|4|0,0=wQ;1,0=wA1;2,0=bQ,wB1;2,-1=bA1");
    auto lost=nu::Board::from_position_string("G1|w|8|4|4|0,0=wQ;1,0=wA1;2,0=bQ,wB1,bB1;2,-1=bA1");
    check(bool(control)&&bool(lost));check(nu::handcrafted_white(*control)>nu::handcrafted_white(*lost));
    check(nu::handcrafted_white(*control,64)==nu::coordination_white(*control));
    const std::array<genseki::Hex,4> cells{{{0,0},{1,0},{2,0},{2,-1}}};
    const std::array<const char*,4> pieces{{"wQ","wA1","bQ,wB1","bA1"}};
    for(unsigned frame=0;frame<12;++frame) {
        std::ostringstream text;text<<"G1|w|8|4|4|";
        for(unsigned i=0;i<cells.size();++i) {
            auto transformed=nu::orient(cells[i].q,cells[i].r,frame);
            if(i)text<<';';
            text<<transformed[0]+20<<','<<transformed[1]-30<<'='<<pieces[i];
        }
        auto transformed=nu::Board::from_position_string(text.str());check(bool(transformed));
        check(nu::handcrafted_white(*transformed)==nu::handcrafted_white(*control));
        check(nu::coordination_white(*transformed)==nu::coordination_white(*control));
    }
    std::mt19937 rng(1701);
    for(unsigned ply=0;ply<16&&!state.board.is_terminal();++ply) {
        auto before=state.board.position_string();auto base=state.evaluate();
        check(nu::Search::evaluate(state,{})==base);
        auto zero=on;zero.hybrid_weight=0;check(nu::Search::evaluate(state,zero)==base);
        auto empty=on;empty.hybrid_terms=0;check(nu::Search::evaluate(state,empty)==base);
        int bonus=nu::handcrafted_white(state.board),combined=nu::Search::evaluate(state,on);
        check(combined==std::clamp(base+bonus*(state.board.side_to_move()==nu::Color::white?1:-1),-8000,8000));
        auto swapped=state.board.position_string();swapped[3]=swapped[3]=='w'?'b':'w';
        auto inverse=nu::Board::from_position_string(swapped);check(bool(inverse));
        nu::State flipped(model,*inverse);check(nu::Search::evaluate(flipped,on)==-combined);
        nu::Search shared(1);auto plain=shared.run(state,1,10000);
        auto hybrid=shared.run(state,1,10000,1,nullptr,on);check(hybrid.score==brute(state,1,on));
        check(state.board.is_legal(hybrid.move));check(std::abs(hybrid.score)>90000||std::abs(hybrid.score)<=8000);
        auto restored=shared.run(state,1,10000);check(restored.move==plain.move&&restored.score==plain.score);
        if(ply<4) {
            auto deeper=shared.run(state,2,10000,1,nullptr,on);
            check(deeper.depth==2&&deeper.score==brute(state,2,on));
        }
        check(state.board.position_string()==before&&state.equivalent());
        auto coordinated=on;coordinated.hybrid_terms=64;
        auto coordinated_result=shared.run(state,1,10000,1,nullptr,coordinated);
        check(coordinated_result.score==brute(state,1,coordinated));
        check(state.board.position_string()==before);
        auto moves=state.legal();state.make(moves[rng()%moves.size()],true);
    }
    auto mate=nu::Board::from_position_string("G1|w|46|23|23|-2,3=bA2;-2,4=wA2;-2,5=bS2;-1,2=bG3;0,-3=wA3;0,-2=bA3;0,-1=wG1,bB1;0,0=bG2;0,1=bS1;1,-2=bQ;1,-1=wG2;1,0=wQ;2,-4=wB2;2,-3=wS2;2,-2=wA1;2,0=bA1;3,0=bG1,bB2;4,0=wS1;5,-1=wB1");
    check(bool(mate));nu::State tactical(model,*mate);nu::Search search(1);
    auto win=search.run(tactical,1,10000,1,nullptr,on);check(win.score==99999);
    tactical.make(win.move,true);check(tactical.board.result()==nu::GameResult::white_win);
    std::cout<<"Independent hybrid evaluation tests passed\n";
}
