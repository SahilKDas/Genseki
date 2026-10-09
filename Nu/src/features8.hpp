#pragma once
#include "features.hpp"
#include <span>

namespace nu {
template<class T,std::size_t Capacity> struct FixedList {
    std::array<T,Capacity> data{};
    unsigned count=0;
    void push_back(T value) {
        if(count==Capacity)throw std::runtime_error("fixed feature capacity exceeded");
        data[count++]=value;
    }
    auto begin(){return data.begin();} auto end(){return data.begin()+count;}
    auto begin()const{return data.begin();} auto end()const{return data.begin()+count;}
    unsigned size()const{return count;}
    const T& operator[](unsigned i)const{return data[i];}
    T& operator[](unsigned i){return data[i];}
};
using PieceFeatures8=std::array<FixedList<unsigned,6>,2>;
using ActiveFeatures8=std::array<FixedList<unsigned,134>,2>;
struct FastFeatures8 {
    std::array<FastPiece,22> pieces{};
    std::array<PieceFeatures8,22> encoded{};
    std::array<Hex,22> geometry{};
    std::array<bool,22> pinned{};
    unsigned cells=0,rebuilt_pieces=0;
    ActiveFeatures8 active;
    std::array<std::array<unsigned,2>,2> queen_features{};
    int prior_white=0;
};
struct FeatureScratch8 {
    struct Cell {Hex cell{};unsigned height=0,top_color=0;std::array<unsigned,6> neighbors{};};
    std::array<Cell,22> cells{};
    std::array<std::array<int,4>,22> candidate{},best{};
    Coordinates coordinates{};
};

// Relative identities are unique: canonical keys have the same identity order
// in every frame, so the twelve candidate keys need no sorting or allocation.
inline Coordinates canonical8(const std::array<FastPiece,22>& pieces,Hex anchor,
                              unsigned perspective,unsigned& frame,FeatureScratch8& scratch) {
    Coordinates best_coordinates{};
    for(unsigned symmetry=0;symmetry<12;++symmetry) {
        unsigned count=0;
        for(unsigned relative=0;relative<22;++relative) {
            auto id=(relative+11*perspective)%22;
            const auto& piece=pieces[id];if(!piece.present)continue;
            auto xy=orient(int(piece.cell.q)-int(anchor.q),int(piece.cell.r)-int(anchor.r),symmetry);
            scratch.coordinates[id]=xy;
            scratch.candidate[count++]={int(relative),int(piece.layer),xy[0],xy[1]};
        }
        if(symmetry==0||std::lexicographical_compare(scratch.candidate.begin(),scratch.candidate.begin()+count,
                                                    scratch.best.begin(),scratch.best.begin()+count)) {
            std::copy_n(scratch.candidate.begin(),count,scratch.best.begin());
            best_coordinates=scratch.coordinates;frame=symmetry;
        }
    }
    return best_coordinates;
}
inline constexpr auto direction_frames8=[] {
    std::array<std::array<unsigned,6>,12> result{};
    for(unsigned frame=0;frame<12;++frame)for(unsigned d=0;d<6;++d) {
        auto xy=orient(directions[d].q,directions[d].r,frame);
        for(unsigned k=0;k<6;++k)if(xy==std::array<int,2>{directions[k].q,directions[k].r})result[frame][d]=k;
    }
    return result;
}();

inline std::array<bool,22> pins8(const std::array<Hex,22>& geometry,unsigned count) {
    std::array<bool,22> pins{};
    std::array<std::array<unsigned,6>,22> edges{};std::array<unsigned,22> degree{};
    for(unsigned i=0;i<count;++i)for(unsigned j=i+1;j<count;++j)if(adjacent(geometry[i],geometry[j])) {
        if(degree[i]==6||degree[j]==6)throw std::runtime_error("invalid hex geometry");
        edges[i][degree[i]++]=j;edges[j][degree[j]++]=i;
    }
    std::array<int,22> entered{},low{};entered.fill(-1);int clock=0;
    auto visit=[&](auto&& self,unsigned v,int parent)->void {
        entered[v]=low[v]=clock++;unsigned children=0;
        for(unsigned i=0;i<degree[v];++i){auto w=edges[v][i];
            if(entered[w]<0){++children;self(self,w,int(v));low[v]=std::min(low[v],low[w]);if(parent>=0&&low[w]>=entered[v])pins[v]=true;}
            else if(int(w)!=parent)low[v]=std::min(low[v],entered[w]);}
        if(parent<0&&children>1)pins[v]=true;
    };
    for(unsigned i=0;i<count;++i)if(entered[i]<0)visit(visit,i,-1);
    return pins;
}
inline PieceFeatures8 encode8(const FastPiece& piece,unsigned id) {
    PieceFeatures8 result;
    constexpr unsigned bugs[]{0,1,1,2,2,3,3,3,4,4,4};unsigned bug=bugs[id%11];
    for(unsigned perspective=0;perspective<2;++perspective) {
        unsigned role=(id/11)^perspective,identity=(id+11*perspective)%22;
        auto q=std::uint32_t(piece.coordinates[perspective][0]),r=std::uint32_t(piece.coordinates[perspective][1]);
        auto coords=mix((std::uint64_t(q)<<32)|r);bool covered=piece.layer+1!=piece.height;
        auto& out=result[perspective];
        out.push_back(unsigned(mix(coords^mix(identity+32*piece.layer+1024*!covered+77))%2048));
        out.push_back(2048+unsigned(mix(coords^mix(bug+8*role+32*piece.layer+1024*!covered+91))%2048));
        unsigned flags=unsigned(covered)+2*unsigned(piece.top_color!=(id/11));
        out.push_back(4096+role*128+bug*16+flags);
        if(!covered) {
            unsigned occupied=0,gates=0;const auto& neighbors=piece.oriented_neighbors[perspective];
            for(unsigned d=0;d<6;++d){occupied|=unsigned(neighbors[d]>0)<<d;gates|=unsigned(neighbors[(d+5)%6]>=piece.height&&neighbors[(d+1)%6]>=piece.height)<<d;}
            out.push_back(4608+role*320+bug*64+occupied);
            out.push_back(5248+role*320+bug*64+gates);
            out.push_back(5888+role*128+bug*16+local_exits(piece));
        }
    }
    return result;
}

inline void fast_features8(FastFeatures8& next,const Board& board,const FastFeatures8* previous,FeatureScratch8& scratch) {
    next=FastFeatures8{};
    const auto& stacks=board.stacks();
    if(stacks.size()>22)throw std::runtime_error("Base Hive has at most 22 stacks");
    if(stacks.empty()) {
        for(unsigned p=0;p<2;++p) {
            for(unsigned color=0;color<2;++color)next.queen_features[p][color]=6208+(color^p)*16+7;
            next.active[p].push_back(6215);next.active[p].push_back(6231);
        }
        return;
    }
    std::array<Hex,2> anchors{};std::array<bool,2> queens{};unsigned present=0;
    next.cells=unsigned(stacks.size());
    auto height=[&](Hex cell){for(unsigned i=0;i<next.cells;++i)if(scratch.cells[i].cell==cell)return scratch.cells[i].height;return 0u;};
    for(unsigned i=0;i<next.cells;++i) {
        const auto& stack=stacks[i];if(stack.pieces.empty())throw std::runtime_error("empty stack");
        next.geometry[i]=stack.cell;scratch.cells[i]={stack.cell,unsigned(stack.pieces.size()),unsigned(stack.pieces.back().color),{}};
        for(unsigned layer=0;layer<stack.pieces.size();++layer) {
            auto piece=stack.pieces[layer];auto id=slot(piece);
            if(id>=22||next.pieces[id].present||++present>22)throw std::runtime_error("invalid Base Hive identity");
            next.pieces[id]={true,stack.cell,layer,unsigned(stack.pieces.size()),unsigned(stack.pieces.back().color)};
            if(piece.bug==Bug::queen){anchors[unsigned(piece.color)]=stack.cell;queens[unsigned(piece.color)]=true;}
        }
    }
    for(unsigned i=0;i<next.cells;++i)for(unsigned d=0;d<6;++d)scratch.cells[i].neighbors[d]=height(add(scratch.cells[i].cell,directions[d]));
    std::array<Coordinates,2> coordinates{};std::array<unsigned,2> frames{};
    for(unsigned perspective=0;perspective<2;++perspective) {
        if(!queens[perspective])for(unsigned relative=0;relative<22;++relative) {
            auto id=(relative+11*perspective)%22;
            if(next.pieces[id].present){anchors[perspective]=next.pieces[id].cell;break;}
        }
        coordinates[perspective]=canonical8(next.pieces,anchors[perspective],perspective,frames[perspective],scratch);
    }
    next.pinned=previous&&next.geometry==previous->geometry&&next.cells==previous->cells?previous->pinned:pins8(next.geometry,next.cells);
    constexpr int covered_cost[]{45,65,55,70,145},pinned_cost[]{25,40,35,45,100},gated_cost[]{12,18,16,20,30};
    for(unsigned i=0;i<next.cells;++i)for(auto piece:stacks[i].pieces) {
        auto id=slot(piece);auto& descriptor=next.pieces[id];
        descriptor.anchors=anchors;descriptor.neighbors=scratch.cells[i].neighbors;descriptor.canonical=true;
        for(unsigned p=0;p<2;++p){descriptor.coordinates[p]=coordinates[p][id];for(unsigned d=0;d<6;++d)
            descriptor.oriented_neighbors[p][direction_frames8[frames[p]][d]]=descriptor.neighbors[d];}
        if(previous&&previous->pieces[id]==descriptor)next.encoded[id]=previous->encoded[id];
        else {next.encoded[id]=encode8(descriptor,id);++next.rebuilt_pieces;}
        for(unsigned p=0;p<2;++p)for(auto feature:next.encoded[id][p])next.active[p].push_back(feature);
        int cost=0;auto bug=unsigned(piece.bug);
        if(descriptor.layer+1!=descriptor.height)cost=covered_cost[bug];
        else if(descriptor.height==1&&next.pinned[i])cost=pinned_cost[bug];
        else if(queens[unsigned(piece.color)]&&local_exits(descriptor)==0)cost=gated_cost[bug];
        next.prior_white+=(piece.color==Color::white?-cost:cost);
    }
    for(unsigned color=0;color<2;++color) {
        unsigned liberties=7;
        if(queens[color]){liberties=0;for(auto direction:directions)liberties+=height(add(anchors[color],direction))==0;}
        for(unsigned p=0;p<2;++p){auto feature=6208+(color^p)*16+liberties;next.queen_features[p][color]=feature;next.active[p].push_back(feature);}
        if(queens[color])next.prior_white+=(color==0?-1:1)*int((6-liberties)*(6-liberties)*18);
    }
    next.prior_white=std::clamp(next.prior_white,-1800,1800);
    for(auto& perspective:next.active)std::sort(perspective.begin(),perspective.end());
}

struct FeatureWorkspace8 {
    FeatureScratch8 scratch;
    std::array<std::shared_ptr<FastFeatures8>,128> snapshots{};
    std::shared_ptr<FastFeatures8> acquire() {
        for(auto& snapshot:snapshots) {
            if(!snapshot){snapshot=std::make_shared<FastFeatures8>();return snapshot;}
            if(snapshot.use_count()==1)return snapshot;
        }
        // Correctness fallback for callers retaining more than 128 ancestors.
        return std::make_shared<FastFeatures8>();
    }
};
}
