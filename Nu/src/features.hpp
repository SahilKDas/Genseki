#pragma once
#include "genseki/core/board.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <vector>
#include <functional>
#include <stdexcept>
#include <memory>

namespace nu {
using namespace genseki;
constexpr unsigned feature_count = 8192;
constexpr unsigned schema = 3;
constexpr unsigned latest_schema = 7;
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
using Coordinates = std::array<std::array<int,2>,22>;
inline std::array<int,2> orient(int q,int r,unsigned symmetry) {
    if(symmetry>=6)std::swap(q,r);
    for(unsigned turn=0;turn<symmetry%6;++turn){int next=-r;r=q+r;q=next;}
    return {q,r};
}
inline Coordinates canonical_coordinates(const Board& board,Hex anchor,unsigned perspective,unsigned* frame=nullptr) {
    Coordinates best{};
    std::vector<std::array<int,4>> best_key;
    // Compare whole labeled stacks, not individual distances: relative geometry
    // must survive normalization, including reflection and covered pieces.
    for(unsigned symmetry=0;symmetry<12;++symmetry) {
        Coordinates candidate{};
        std::vector<std::array<int,4>> key;
        for(const auto& stack:board.stacks())for(unsigned h=0;h<stack.pieces.size();++h) {
            auto identity=slot(stack.pieces[h]);
            auto xy=orient(int(stack.cell.q)-int(anchor.q),int(stack.cell.r)-int(anchor.r),symmetry);
            candidate[identity]=xy;
            key.push_back({int((identity+11*perspective)%22),int(h),xy[0],xy[1]});
        }
        std::sort(key.begin(),key.end());
        if(symmetry==0||key<best_key){best_key=std::move(key);best=candidate;if(frame)*frame=symmetry;}
    }
    return best;
}
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
// Schema 5 is a separate hybrid contract: cheap local features plus prior v1.
// No exact mobility or articulation is embedded in the neural input.
constexpr unsigned fast_schema=5;
inline bool is_fast_schema(unsigned version){return version==5||version==7;}
constexpr unsigned strategic_prior_version=1;
struct FastPiece {
    bool present=false;
    Hex cell{};
    unsigned layer=0,height=0,top_color=0;
    std::array<unsigned,6> neighbors{};
    std::array<Hex,2> anchors{};
    bool canonical=false;
    std::array<std::array<int,2>,2> coordinates{};
    std::array<std::array<unsigned,6>,2> oriented_neighbors{};
    auto operator<=>(const FastPiece&) const = default;
};
struct FastFeatures {
    std::array<FastPiece,22> pieces{};
    std::array<std::shared_ptr<const Features>,22> encoded{};
    std::vector<Hex> geometry;
    std::vector<bool> pinned;
    Features active;
    int prior_white=0;
    unsigned rebuilt_pieces=0;
};
inline std::vector<bool> connectivity_pins(const std::vector<Hex>& cells) {
    if(cells.size()>22)throw std::runtime_error("Base Hive has at most 22 occupied cells");
    std::vector<bool> pins(cells.size());
    std::array<std::array<unsigned,6>,22> edges{};std::array<unsigned,22> degree{};
    for(unsigned i=0;i<cells.size();++i)for(unsigned j=i+1;j<cells.size();++j)
        if(adjacent(cells[i],cells[j])){edges[i][degree[i]++]=j;edges[j][degree[j]++]=i;}
    std::array<int,22> entered{},low{};entered.fill(-1);int clock=0;
    auto visit=[&](auto&& self,unsigned v,int parent)->void {
        entered[v]=low[v]=clock++;unsigned children=0;
        for(unsigned i=0;i<degree[v];++i){auto w=edges[v][i];
            if(entered[w]<0){++children;self(self,w,int(v));low[v]=std::min(low[v],low[w]);if(parent>=0&&low[w]>=entered[v])pins[v]=true;}
            else if(int(w)!=parent)low[v]=std::min(low[v],entered[w]);}
        if(parent<0&&children>1)pins[v]=true;
    };
    for(unsigned i=0;i<cells.size();++i)if(entered[i]<0)visit(visit,i,-1);
    return pins;
}
inline unsigned local_exits(const FastPiece& p) {
    unsigned exits=0;
    for(unsigned d=0;d<6;++d) {
        bool gate=p.neighbors[(d+5)%6]>=p.height&&p.neighbors[(d+1)%6]>=p.height;
        // A necessary local departure condition, not exact movement legality.
        if(!gate&&(p.neighbors[d]==0||p.layer>0))++exits;
    }
    return exits;
}
inline Features encode_fast_piece(const FastPiece& p,unsigned id) {
    Features result;
    // Slot ranges match the existing Base Hive identity layout.
    constexpr unsigned bugs[]{0,1,1,2,2,3,3,3,4,4,4};
    unsigned bug=bugs[id%11];
    for(unsigned perspective=0;perspective<2;++perspective) {
        unsigned role=(id/11)^perspective,identity=perspective?(id+11)%22:id;
        auto q=std::uint32_t(p.canonical?p.coordinates[perspective][0]:int(p.cell.q)-p.anchors[perspective].q);
        auto r=std::uint32_t(p.canonical?p.coordinates[perspective][1]:int(p.cell.r)-p.anchors[perspective].r);
        auto coords=mix((std::uint64_t(q)<<32)|r);
        bool covered=p.layer+1!=p.height;
        result[perspective].push_back(unsigned(mix(coords^mix(identity+32*p.layer+1024*!covered+77))%2048));
        result[perspective].push_back(2048+unsigned(mix(coords^mix(bug+8*role+32*p.layer+1024*!covered+91))%2048));
        unsigned flags=unsigned(covered)+2*unsigned(p.top_color!=(id/11));
        result[perspective].push_back(4096+role*128+bug*16+flags);
        if(!covered) {
            unsigned occupied=0,gates=0;
            const auto& neighbors=p.canonical?p.oriented_neighbors[perspective]:p.neighbors;
            for(unsigned d=0;d<6;++d){occupied|=unsigned(neighbors[d]>0)<<d;gates|=unsigned(neighbors[(d+5)%6]>=p.height&&neighbors[(d+1)%6]>=p.height)<<d;}
            result[perspective].push_back(4608+role*320+bug*64+occupied);
            result[perspective].push_back(5248+role*320+bug*64+gates);
            result[perspective].push_back(5888+role*128+bug*16+local_exits(p));
        }
    }
    return result;
}
inline FastFeatures fast_features(const Board& board,const FastFeatures* previous=nullptr,unsigned version=5) {
    FastFeatures next;
    std::array<Hex,2> anchors{};std::array<bool,2> queens{};
    const auto& stacks=board.stacks();
    auto height=[&](Hex cell){for(const auto& s:stacks)if(s.cell==cell)return unsigned(s.pieces.size());return 0u;};
    for(const auto& s:stacks){next.geometry.push_back(s.cell);for(auto p:s.pieces)if(p.bug==Bug::queen){anchors[unsigned(p.color)]=s.cell;queens[unsigned(p.color)]=true;}}
    std::array<Coordinates,2> coordinates{};std::array<unsigned,2> frames{};
    if(version==7)for(unsigned perspective=0;perspective<2;++perspective) {
        if(!queens[perspective]) {
            unsigned first=22;
            for(const auto& stack:stacks)for(auto piece:stack.pieces) {
                auto id=(slot(piece)+11*perspective)%22;
                if(id<first){first=id;anchors[perspective]=stack.cell;}
            }
        }
        coordinates[perspective]=canonical_coordinates(board,anchors[perspective],perspective,&frames[perspective]);
    }
    next.pinned=previous&&next.geometry==previous->geometry?previous->pinned:connectivity_pins(next.geometry);
    constexpr int covered_cost[]{45,65,55,70,145};
    constexpr int pinned_cost[]{25,40,35,45,100};
    constexpr int gated_cost[]{12,18,16,20,30};
    for(unsigned i=0;i<stacks.size();++i) {
        const auto& s=stacks[i];std::array<unsigned,6> neighbors{};
        for(unsigned d=0;d<6;++d)neighbors[d]=height(add(s.cell,directions[d]));
        for(unsigned h=0;h<s.pieces.size();++h) {
            auto piece=s.pieces[h];unsigned id=slot(piece);
            FastPiece descriptor{true,s.cell,h,unsigned(s.pieces.size()),unsigned(s.pieces.back().color),neighbors,anchors};
            if(version==7) {
                descriptor.canonical=true;
                for(unsigned p=0;p<2;++p) {
                    descriptor.coordinates[p]=coordinates[p][id];
                    for(unsigned d=0;d<6;++d) {
                        auto xy=orient(directions[d].q,directions[d].r,frames[p]);
                        for(unsigned k=0;k<6;++k)if(xy==std::array<int,2>{directions[k].q,directions[k].r})
                            descriptor.oriented_neighbors[p][k]=neighbors[d];
                    }
                }
            }
            next.pieces[id]=descriptor;
            if(previous&&previous->pieces[id]==descriptor)next.encoded[id]=previous->encoded[id];
            else {next.encoded[id]=std::make_shared<Features>(encode_fast_piece(descriptor,id));++next.rebuilt_pieces;}
            for(unsigned p=0;p<2;++p)next.active[p].insert(next.active[p].end(),(*next.encoded[id])[p].begin(),(*next.encoded[id])[p].end());
            int cost=0;unsigned bug=unsigned(piece.bug);
            // Mutually exclusive reasons avoid double-counting immobilization.
            if(h+1!=s.pieces.size())cost=covered_cost[bug];
            else if(s.pieces.size()==1&&next.pinned[i])cost=pinned_cost[bug];
            else if(queens[unsigned(piece.color)]&&local_exits(descriptor)==0)cost=gated_cost[bug];
            next.prior_white+=(piece.color==Color::white?-cost:cost);
        }
    }
    for(unsigned color=0;color<2;++color) {
        unsigned liberties=7;
        if(queens[color]){liberties=0;for(auto direction:directions)liberties+=height(add(anchors[color],direction))==0;}
        for(unsigned p=0;p<2;++p)next.active[p].push_back(6208+(color^p)*16+liberties);
        if(queens[color])next.prior_white+=(color==0?-1:1)*int((6-liberties)*(6-liberties)*18);
    }
    next.prior_white=std::clamp(next.prior_white,-1800,1800);
    for(auto& perspective:next.active)std::sort(perspective.begin(),perspective.end());
    return next;
}

inline Features features(const Board& b,unsigned version=schema,const Mobility* cached_mobility=nullptr) {
    if(is_fast_schema(version))return fast_features(b,nullptr,version).active;
    if(version<1||version>latest_schema)throw std::runtime_error("unsupported feature schema");
    std::array<Hex,2> anchors{};
    std::array<bool,2> queen_present{};
    for (const auto& s:b.stacks()) for (auto p:s.pieces)
        if(p.bug==Bug::queen) {anchors[unsigned(p.color)]=s.cell;queen_present[unsigned(p.color)]=true;}
    const auto& stacks=b.stacks();
    std::array<Coordinates,2> canonical{};
    if(version==6)for(unsigned perspective=0;perspective<2;++perspective) {
        if(!queen_present[perspective]) {
            unsigned first=22;
            for(const auto& stack:stacks)for(auto piece:stack.pieces) {
                auto identity=(slot(piece)+11*perspective)%22;
                if(identity<first){first=identity;anchors[perspective]=stack.cell;}
            }
        }
        canonical[perspective]=canonical_coordinates(b,anchors[perspective],perspective);
    }
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
    if(version>=4)mobility=cached_mobility?*cached_mobility:movement_counts(b);
    for(unsigned perspective=0;perspective<2;++perspective) {
        out[perspective].reserve(5*22+2);
        for(unsigned cell_index=0;cell_index<stacks.size();++cell_index) {
          const auto& s=stacks[cell_index];for(unsigned h=0;h<s.pieces.size();++h) {
            auto p=s.pieces[h];
            unsigned identity=slot(p);
            if(perspective) identity=(identity+11)%22;
            // Hash full signed relative coordinates; never clip the hive to a window.
            auto relative=version==6?canonical[perspective][slot(p)]:
                std::array<int,2>{int(s.cell.q)-int(anchors[perspective].q),int(s.cell.r)-int(anchors[perspective].r)};
            auto q=std::uint32_t(relative[0]);
            auto r=std::uint32_t(relative[1]);
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
                        if(relative[0]==dq&&relative[1]==dr)local=index;
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
                    if(version>=4) {
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
