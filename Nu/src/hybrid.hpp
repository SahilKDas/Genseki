#pragma once
#include "genseki/core/board.hpp"
#include <algorithm>
#include <array>
#include <bit>

namespace nu {
struct Coordination {int coverage=0, pinned_defenders=0, single_defender=0, fragile_attacks=0;};
inline Coordination joint_threat(const genseki::Board& board,genseki::Color side) {
    using namespace genseki;
    Coordination out;const Stack* queen=nullptr;
    for(const auto& stack:board.stacks())for(auto p:stack.pieces)
        if(p.color==other(side)&&p.bug==Bug::queen)queen=&stack;
    if(!queen)return out;
    std::vector<Hex> liberties;
    for(auto d:directions) {
        auto cell=add(queen->cell,d);
        if(std::ranges::none_of(board.stacks(),[&](const Stack& s){return s.cell==cell;}))liberties.push_back(cell);
    }
    if(liberties.size()>3||liberties.empty())return out;
    // Legal movement includes One Hive, covered pieces, gates and Queen placement.
    const auto attackers=board.movement_moves(side),defenders=board.movement_moves(other(side));
    std::array<bool,64> reachable{};reachable[0]=true;
    unsigned mobile_defenders=0;
    for(const auto& stack:board.stacks()) {
        const auto piece=stack.pieces.back();
        bool mobile=std::ranges::any_of(defenders,[&](const Move& m){return m.piece==piece;});
        if(piece.color==other(side)&&piece.bug!=Bug::queen&&adjacent(stack.cell,queen->cell)) {
            if(mobile)++mobile_defenders;else ++out.pinned_defenders;
        }
        if(piece.color!=side)continue;
        unsigned mask=0;
        for(const auto& move:attackers)if(move.piece==piece) {
            for(unsigned i=0;i<liberties.size();++i)if(move.to==liberties[i]) {
                // Do not count a move which opens a different surround cell.
                if(stack.pieces.size()==1&&adjacent(stack.cell,queen->cell))++out.fragile_attacks;
                else mask|=1u<<i;
            }
        }
        auto previous=reachable;
        for(unsigned occupied=0;occupied<64;++occupied)if(previous[occupied])
            for(unsigned i=0;i<liberties.size();++i)if((mask&(1u<<i))&&!(occupied&(1u<<i)))reachable[occupied|(1u<<i)]=true;
    }
    for(unsigned mask=0;mask<64;++mask)if(reachable[mask])out.coverage=std::max(out.coverage,int(std::popcount(mask)));
    out.single_defender=mobile_defenders==1;
    return out;
}
inline int coordination_white(const genseki::Board& board) {
    auto score=[](Coordination c){return c.coverage*24+c.pinned_defenders*8+c.single_defender*12-std::min(c.fragile_attacks,4)*4;};
    return score(joint_threat(board,genseki::Color::white))-score(joint_threat(board,genseki::Color::black));
}
// Independent, inexpensive position weights; no move generation or teacher calls.
struct HybridWeights {
    static constexpr int neighbor=18, friendly_surround=12, queen_control=90;
    static constexpr int nearby_beetle=14, queen_exit=4, last_liberty=140, two_liberties=50;
};
inline int handcrafted_white(const genseki::Board& board,unsigned terms=63) {
    using namespace genseki;
    std::array<const Stack*,2> queens{};
    for(const auto& stack:board.stacks())for(auto piece:stack.pieces)
        if(piece.bug==Bug::queen)queens[unsigned(piece.color)]=&stack;
    auto occupied=[&](Hex cell) {
        return std::ranges::any_of(board.stacks(),[&](const Stack& stack){return stack.cell==cell;});
    };
    auto attack=[&](Color side) {
        int score=0;auto enemy=queens[unsigned(other(side))];auto own=queens[unsigned(side)];
        if(enemy) {
            unsigned liberties=6;
            for(const auto& stack:board.stacks()) {
                if(!adjacent(enemy->cell,stack.cell))continue;
                --liberties;if(terms&1)score+=HybridWeights::neighbor;
                if(stack.pieces.back().color==side) {
                    if(terms&2)score+=HybridWeights::friendly_surround;
                    if((terms&8)&&stack.pieces.back().bug==Bug::beetle)score+=HybridWeights::nearby_beetle;
                }
            }
            if((terms&4)&&enemy->pieces.size()>1&&enemy->pieces.back().color==side)score+=HybridWeights::queen_control;
            if(terms&32) {
                if(liberties==1)score+=HybridWeights::last_liberty;
                else if(liberties==2)score+=HybridWeights::two_liberties;
            }
        }
        if((terms&16)&&own&&own->pieces.size()==1) {
            for(unsigned d=0;d<6;++d) {
                bool empty=!occupied(add(own->cell,directions[d]));
                bool gate=occupied(add(own->cell,directions[(d+5)%6]))&&occupied(add(own->cell,directions[(d+1)%6]));
                if(empty&&!gate)score+=HybridWeights::queen_exit;
            }
        }
        return score;
    };
    return std::clamp(attack(Color::white)-attack(Color::black)+((terms&64)?coordination_white(board):0),-900,900);
}
}
