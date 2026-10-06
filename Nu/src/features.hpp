#pragma once
#include "genseki/core/board.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <vector>
#include <functional>

namespace nu {
using namespace genseki;
constexpr unsigned feature_count = 8192;
constexpr unsigned schema = 3;
inline std::uint64_t mix(std::uint64_t x) {
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
inline unsigned slot(Piece p) {
    constexpr unsigned offsets[]{0,1,3,5,8};
    return unsigned(p.color)*11 + offsets[unsigned(p.bug)] + p.id;
}
using Features = std::array<std::vector<unsigned>,2>;
using Mobility = std::array<unsigned,22>;
inline Mobility movement_counts(const Board& board) {
    Mobility counts{};
    for(unsigned color=0;color<2;++color)for(auto move:board.movement_moves(Color(color)))++counts[slot(move.piece)];
    return counts;
}
inline Mobility update_movement_counts(const Board& board,const Mobility& previous,const Move& move,bool unchanged_occupancy) {
    if(!unchanged_occupancy)return movement_counts(board);
    auto next=previous;
    // Ground movement depends on occupied geometry, which an occupied-to-occupied
    // Beetle move leaves unchanged. Refresh exposed/covered stones and all Beetles.
    for(unsigned color=0;color<2;++color)for(unsigned id=0;id<2;++id)next[slot(Piece{Color(color),Bug::beetle,std::uint8_t(id)})]=0;
    for(const auto& stack:board.stacks()) {
        bool changed=stack.cell==move.to||(move.from&&stack.cell==*move.from);
        if(changed)for(auto piece:stack.pieces)next[slot(piece)]=0;
        if(changed||stack.pieces.back().bug==Bug::beetle) {
            auto piece=stack.pieces.back();
            next[slot(piece)]=unsigned(board.movement_moves(piece.color,stack.cell).size());
        }
    }
    return next;
}
inline Features features(const Board& b,unsigned version=schema,const Mobility* cached_mobility=nullptr) {
    std::array<Hex,2> anchors{};
    std::array<bool,2> queen_present{};
    for (const auto& s:b.stacks()) for (auto p:s.pieces)
        if(p.bug==Bug::queen) {anchors[unsigned(p.color)]=s.cell;queen_present[unsigned(p.color)]=true;}
    const auto& stacks=b.stacks();
    std::array<bool,22> articulation{};std::array<unsigned,22> access{};
    auto height=[&](Hex cell){for(const auto& stack:stacks)if(stack.cell==cell)return unsigned(stack.pieces.size());return 0u;};
    constexpr std::array<Hex,6> adjacent{{{1,0},{0,1},{-1,1},{-1,0},{0,-1},{1,-1}}};
    if(version>=3) {
        std::array<std::array<unsigned,6>,22> edges{};std::array<unsigned,22> degree{};
        for(unsigned i=0;i<stacks.size();++i)for(unsigned j=i+1;j<stacks.size();++j) {
            int q=int(stacks[i].cell.q)-stacks[j].cell.q,r=int(stacks[i].cell.r)-stacks[j].cell.r;
            if(std::max({std::abs(q),std::abs(r),std::abs(q+r)})==1){edges[i][degree[i]++]=j;edges[j][degree[j]++]=i;}
        }
        std::array<int,22> entered{},low{};entered.fill(-1);int clock=0;
        auto visit=[&](auto&& self,unsigned v,int parent)->void {
            entered[v]=low[v]=clock++;unsigned children=0;
            for(unsigned i=0;i<degree[v];++i) {
                auto next=edges[v][i];
                if(entered[next]<0) {
                    ++children;self(self,next,int(v));low[v]=std::min(low[v],low[next]);
                    if(parent>=0&&low[next]>=entered[v])articulation[v]=true;
                }else if(int(next)!=parent)low[v]=std::min(low[v],entered[next]);
            }
            if(parent<0&&children>1)articulation[v]=true;
        };
        for(unsigned i=0;i<stacks.size();++i)if(entered[i]<0)visit(visit,i,-1);
        for(unsigned i=0;i<stacks.size();++i)for(unsigned d=0;d<6;++d) {
            auto from=stacks[i].cell,to=add(from,adjacent[d]);if(height(to))continue;
            auto level=unsigned(stacks[i].pieces.size());
            if(height(add(from,adjacent[(d+5)%6]))>=level&&height(add(from,adjacent[(d+1)%6]))>=level)continue;
            bool touches=false;
            for(auto direction:adjacent) {auto cell=add(to,direction);if(cell==from&&level==1)continue;touches|=height(cell)>0;}
            access[i]+=touches;
        }
    }
    Features out;
    Mobility mobility{};
    if(version==4)mobility=cached_mobility?*cached_mobility:movement_counts(b);
    for(unsigned perspective=0;perspective<2;++perspective) {
        out[perspective].reserve(5*22+2);
        for(unsigned cell_index=0;cell_index<stacks.size();++cell_index) {
          const auto& s=stacks[cell_index];for(unsigned h=0;h<s.pieces.size();++h) {
            auto p=s.pieces[h];
            unsigned identity=slot(p);
            if(perspective) identity=(identity+11)%22;
            // Hash full signed relative coordinates; never clip the hive to a window.
            auto q=std::uint32_t(int(s.cell.q)-int(anchors[perspective].q));
            auto r=std::uint32_t(int(s.cell.r)-int(anchors[perspective].r));
            auto v=mix((std::uint64_t(q)<<32)|r);
            v^=mix(0x91e10da5c79e7b1dULL+identity+32*h+1024*(h+1==s.pieces.size()));
            out[perspective].push_back(unsigned(mix(v)%(version==1?feature_count:version==2?4096:2048)));
            if(version>=2) {
                unsigned role=unsigned(p.color)^perspective;
                auto coordinates=mix((std::uint64_t(q)<<32)|r);
                auto shared=coordinates^mix(unsigned(p.bug)+8*role+32*h+1024*(h+1==s.pieces.size()));
                out[perspective].push_back((version==2?4096:2048)+unsigned(mix(shared)%2048));
                if(h+1==s.pieces.size()) {
                    int local=-1,index=0;
                    for(int dq=-2;dq<=2;++dq)for(int dr=-2;dr<=2;++dr) {
                        if(std::max({std::abs(dq),std::abs(dr),std::abs(dq+dr)})>2)continue;
                        if(int(s.cell.q)-int(anchors[perspective].q)==dq&&int(s.cell.r)-int(anchors[perspective].r)==dr)local=index;
                        ++index;
                    }
                    unsigned base=version==2?6144:4096;
                    out[perspective].push_back(local>=0?base+role*19+unsigned(local):base+64+unsigned(mix(coordinates^mix(role+77))%1984));
                }
                if(version>=3) {
                    bool covered=h+1!=s.pieces.size();
                    unsigned flags=unsigned(queen_present[unsigned(p.color)])+2*covered
                        +4*(s.pieces.size()==1&&articulation[cell_index])+8*(access[cell_index]==0);
                    out[perspective].push_back(6144+role*128+unsigned(p.bug)*16+flags);
                    out[perspective].push_back(6400+role*128+unsigned(p.bug)*16+(covered?7:access[cell_index]));
                    if(version==4) {
                        out[perspective].push_back(7000+role*128+unsigned(p.bug)*16+std::min(15u,mobility[slot(p)]));
                        if(p.bug==Bug::queen) {
                            unsigned control=unsigned(covered)+2*unsigned(s.pieces.back().color!=p.color);
                            out[perspective].push_back(7400+role*16+control);
                        }
                    }
                }
            }
          }
        }
        if(version>=3)for(unsigned color=0;color<2;++color) {
            unsigned liberties=7;
            if(queen_present[color]) {liberties=0;for(auto direction:adjacent)liberties+=height(add(anchors[color],direction))==0;}
            out[perspective].push_back(6800+(color^perspective)*16+liberties);
        }
        std::sort(out[perspective].begin(),out[perspective].end());
    }
    return out;
}
inline std::uint64_t piece_hash(Piece piece,Hex cell,unsigned height) {
    auto coords=(std::uint64_t(std::uint16_t(cell.q))<<16)|std::uint16_t(cell.r);
    return mix(coords^(std::uint64_t(slot(piece)+1)<<40)^(std::uint64_t(height)<<48));
}
inline std::uint64_t position_hash(const Board& b) {
    std::uint64_t hash=mix(unsigned(b.side_to_move())+17);
    // Opening legality depends on the turn count until the queen deadline.
    hash^=mix(std::min<std::size_t>(b.ply(),8)+987);
    for(const auto& s:b.stacks()) for(unsigned h=0;h<s.pieces.size();++h) {
        hash^=piece_hash(s.pieces[h],s.cell,h);
    }
    return hash;
}
inline std::uint64_t repetition_hash(const Board& board) {
    auto hash=mix(unsigned(board.side_to_move())+17)^mix(std::min<std::size_t>(board.ply(),8)+987);
    for(const auto& stack:board.stacks())for(unsigned h=0;h<stack.pieces.size();++h) {
        auto piece=stack.pieces[h];piece.id=0;hash^=piece_hash(piece,stack.cell,h);
    }
    return hash;
}
inline bool match_repetition(const std::vector<std::uint64_t>& history) {
    // Entry zero is the initial state, not part of Nokamute's post-move history.
    if(history.size()<=11)return false;
    unsigned matches=0;
    for(unsigned offset=4;offset<=32&&offset<history.size()-1;offset+=4)
        matches+=history[history.size()-1-offset]==history.back();
    return matches>=2;
}
}
