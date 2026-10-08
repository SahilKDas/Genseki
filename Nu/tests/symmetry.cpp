#include "state.hpp"
#include <iostream>
#include <random>
#include <sstream>

void require(bool value){if(!value)throw std::runtime_error("symmetry regression");}

genseki::Board transformed(const genseki::Board& board,unsigned symmetry,int dq,int dr,bool swap_colors=false) {
    auto original=board.position_string();
    std::size_t end=0;
    for(unsigned field=0;field<5;++field)end=original.find('|',end)+1;
    std::ostringstream text;text<<original.substr(0,end);
    bool first=true;
    for(const auto& stack:board.stacks()) {
        int q=stack.cell.q,r=stack.cell.r;
        if(symmetry>=6)std::swap(q,r);
        for(unsigned i=0;i<symmetry%6;++i){int old=q;q=-r;r=old+r;}
        if(!first)text<<';';
        first=false;
        text<<q+dq<<','<<r+dr<<'=';
        for(unsigned h=0;h<stack.pieces.size();++h) {
            auto piece=stack.pieces[h];
            if(swap_colors)piece.color=genseki::other(piece.color);
            if(h)text<<',';
            text<<(piece.color==genseki::Color::white?'w':'b')<<"QSBGA"[unsigned(piece.bug)];
            if(piece.bug!=genseki::Bug::queen)text<<unsigned(piece.id)+1;
        }
    }
    auto result=genseki::Board::from_position_string(text.str());
    require(bool(result));return *result;
}

void verify(const genseki::Board& board,const nu::Model& model) {
    auto expected=nu::features(board,model.feature_schema);
    nu::State state(model,board);
    for(unsigned symmetry=0;symmetry<12;++symmetry)for(auto offset:std::array<std::array<int,2>,3>{{{0,0},{19,-11},{-23,17}}}) {
        auto rotated=transformed(board,symmetry,offset[0],offset[1]);
        require(nu::features(rotated,model.feature_schema)==expected);
        nu::State equivalent(model,rotated);
        require(equivalent.evaluate()==state.evaluate()&&equivalent.accumulator.sums==state.accumulator.sums);
        auto colors=transformed(board,symmetry,offset[0],offset[1],true);
        auto swapped=nu::features(colors,model.feature_schema);
        require(swapped[0]==expected[1]&&swapped[1]==expected[0]);
    }
}

int main() {
    for(unsigned version:{6u,7u})for(unsigned width:{64u,128u}) {
        nu::Model model(width);model.feature_schema=version;
        for(const auto& position:{"G1|w|0|0|0|",
                "G1|w|2|1|1|0,0=wA1;1,0=bS1",
                "G1|b|3|2|1|0,0=wA1;1,0=bS1;-1,1=wQ",
                "G1|w|8|4|4|0,0=wQ;1,0=wA1,bB1;2,0=bQ",
                "G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ"}) {
            auto board=genseki::Board::from_position_string(position);require(bool(board));verify(*board,model);
        }
        genseki::Board board;std::mt19937 rng(731);
        for(unsigned ply=0;ply<50&&!board.is_terminal();++ply) {
            verify(board,model);
            auto moves=board.legal_moves();(void)board.make_generated_move(moves[rng()%moves.size()]);
        }
        model.head=32;model.head_weights.resize(64*width);model.head_bias.resize(32);model.output.resize(32);
        for(auto& value:model.head_weights)value=std::int16_t(int(rng()%31)-15);
        for(auto& value:model.output)value=std::int16_t(int(rng()%41)-20);
        verify(board,model);
    }
    bool rejected=false;
    try{(void)nu::features(genseki::Board{},8);}catch(const std::runtime_error&){rejected=true;}
    require(rejected);
    std::cout<<"Nu D6 symmetry, translation, color-perspective and inference tests passed\n";
}
