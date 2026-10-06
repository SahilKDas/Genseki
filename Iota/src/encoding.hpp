#pragma once
#include "genseki/core/board.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>

namespace iota {
using namespace genseki;
constexpr int features=80, action_features=16;
struct Encoded {
    std::vector<Hex> cells;
    std::vector<float> x;
    std::vector<std::array<int,6>> edges;
    std::map<Hex,int> index;
    Hex offset{};
    bool modern=false;
    std::vector<std::array<int,3>> links; // destination, source, relation
    std::map<Piece,int> stones;
};
inline Encoded encode(const Board& b,bool cnn,bool modern=false,bool directional=false) {
    Encoded e;
    e.modern=modern;
    int loq=0,hiq=0,lor=0,hir=0;
    if(!b.stacks().empty()) {
        loq=hiq=b.stacks()[0].cell.q;lor=hir=b.stacks()[0].cell.r;
        for(auto& s:b.stacks()) {loq=std::min(loq,int(s.cell.q));hiq=std::max(hiq,int(s.cell.q));lor=std::min(lor,int(s.cell.r));hir=std::max(hir,int(s.cell.r));}
    }
    e.offset={static_cast<int16_t>((loq+hiq)/2),static_cast<int16_t>((lor+hir)/2)};
    if(modern&&!b.stacks().empty()) {
        std::optional<Piece> anchor;
        for(auto& s:b.stacks())for(auto p:s.pieces)if(!anchor||p<*anchor){anchor=p;e.offset=s.cell;}
    }
    std::set<Hex> nodes;
    if(cnn)for(int q=-22;q<=22;++q)for(int r=-22;r<=22;++r) {
        if(!modern||std::abs(q+r)<=22)nodes.insert({int16_t(q+e.offset.q),int16_t(r+e.offset.r)});
    }
    else {
        nodes.insert({0,0});
        if(!b.stacks().empty())nodes.clear();
        for(auto& s:b.stacks()){nodes.insert(s.cell);for(auto d:directions)nodes.insert(add(s.cell,d));}
    }
    for(auto h:nodes){
        auto stack=std::find_if(b.stacks().begin(),b.stacks().end(),[&](auto& s){return s.cell==h;});
        if(modern&&!cnn&&stack!=b.stacks().end()) {
            for(auto p:stack->pieces){e.stones[p]=int(e.cells.size());e.cells.push_back(h);}
            e.index[h]=int(e.cells.size())-1;
        } else {e.index[h]=int(e.cells.size());e.cells.push_back(h);}
    }
    e.x.assign(e.cells.size()*features,0);
    std::array<int,10> reserves{1,2,2,3,3,1,2,2,3,3};
    std::array<bool,2> queen{};
    for(auto& s:b.stacks())for(auto p:s.pieces){--reserves[int(p.color)*5+int(p.bug)];if(p.bug==Bug::queen)queen[int(p.color)]=true;}
    for(size_t i=0;i<e.cells.size();++i){
        auto h=e.cells[i];float* f=e.x.data()+i*features;
        f[0]=1; f[64]=b.side_to_move()==Color::white?1:0;f[65]=b.side_to_move()==Color::black?1:0;
        for(int c=0;c<2;++c){f[66+c]=queen[c];f[68+c]=std::min(4,int((b.ply()+1-c)/2))/4.f;}
        for(int j=0;j<10;++j)f[70+j]=reserves[j]/3.f;
        for(auto& s:b.stacks())if(s.cell==h){
            if(s.pieces.size()>5)throw std::runtime_error("invalid Base stack height");
            f[1]=1;f[2]=s.pieces.size()/5.f;
            for(size_t k=0;k<s.pieces.size();++k){auto p=s.pieces[k];f[3+k*10+int(p.color)*5+int(p.bug)]=1;}
            auto p=s.pieces.back();f[53+int(p.color)*5+int(p.bug)]=1;
            f[63]=s.pieces.size()>1;
            if(modern&&!cnn)for(size_t k=0;k<s.pieces.size();++k)if(e.stones.at(s.pieces[k])==int(i)){
                std::fill(f+53,f+63,0.f);
                auto p=s.pieces[k];f[53+int(p.color)*5+int(p.bug)]=1;
                f[2]=(k+1)/5.f;f[63]=k+1<s.pieces.size();
            }
        }
        std::array<int,6> a{};for(int d=0;d<6;++d){auto it=e.index.find(add(h,directions[d]));a[d]=it==e.index.end()?-1:it->second;}e.edges.push_back(a);
    }
    if(modern) {
        // Hex messages use surface stones; buried stones communicate vertically.
        for(auto [cell,i]:e.index)for(int d=0;d<6;++d){auto it=e.index.find(add(cell,directions[d]));if(it!=e.index.end())e.links.push_back({i,it->second,directional?d:0});}
        if(!cnn) {
            for(auto& s:b.stacks())for(size_t k=1;k<s.pieces.size();++k){int below=e.stones.at(s.pieces[k-1]),above=e.stones.at(s.pieces[k]);e.links.push_back({above,below,1});e.links.push_back({below,above,2});}
            for(auto m:b.legal_moves())if(m.from&&m.kind!=MoveKind::pass){int src=e.stones.at(m.piece),dst=e.index.at(m.to);e.links.push_back({dst,src,3});e.links.push_back({src,dst,4});}
        }
        std::sort(e.links.begin(),e.links.end());e.links.erase(std::unique(e.links.begin(),e.links.end()),e.links.end());
    }
    return e;
}
inline std::array<float,action_features> action(const Board& b,const Move& m,bool modern=false){
    std::array<float,action_features> a{};a[int(m.kind)]=1;a[3+int(m.piece.bug)]=1;
    if(m.from){a[8]=(m.to.q-m.from->q)/22.f;a[9]=(m.to.r-m.from->r)/22.f;}
    if(modern&&m.from){int q=m.to.q-m.from->q,r=m.to.r-m.from->r;a[8]=std::max({std::abs(q),std::abs(r),std::abs(q+r)})/22.f;a[9]=q==0&&r==0;}
    for(auto& s:b.stacks()){if(m.from&&s.cell==*m.from)a[10]=s.pieces.size()/5.f;if(s.cell==m.to)a[11]=s.pieces.size()/5.f;}
    a[12]=m.piece.color==b.side_to_move();a[13]=m.from.has_value();a[14]=m.kind==MoveKind::pass;a[15]=1;return a;
}
inline uint64_t hash(const Board& b){
    uint64_t h=1469598103934665603ull;
    // Position identity deliberately excludes the full move history.
    auto byte=[&](unsigned x){h^=x;h*=1099511628211ull;};byte(int(b.side_to_move()));
    for(auto& s:b.stacks()){byte(uint16_t(s.cell.q)&255);byte(uint16_t(s.cell.q)>>8);byte(uint16_t(s.cell.r)&255);byte(uint16_t(s.cell.r)>>8);byte(s.pieces.size());for(auto p:s.pieces){byte(int(p.color));byte(int(p.bug));byte(p.id);}}
    byte(std::min(size_t(8),b.ply()));return h;
}
inline std::string canonical(const Board& b){
    std::string best;
    for(int reflect=0;reflect<2;++reflect)for(int rot=0;rot<6;++rot){
        std::vector<std::pair<Hex,std::string>> v;
        for(auto& s:b.stacks()){int q=s.cell.q,r=s.cell.r;if(reflect)std::swap(q,r);for(int k=0;k<rot;++k){int t=-r;r=q+r;q=t;}std::string p;for(auto x:s.pieces)p+=char('A'+int(x.color)*5+int(x.bug));v.push_back({{int16_t(q),int16_t(r)},p});}
        std::sort(v.begin(),v.end());int q=v.empty()?0:v[0].first.q,r=v.empty()?0:v[0].first.r;
        std::string out=std::to_string(int(b.side_to_move()))+":"+std::to_string(std::min(size_t(8),b.ply()));
        for(auto& [h,p]:v)out+=";"+std::to_string(h.q-q)+","+std::to_string(h.r-r)+":"+p;
        if(best.empty()||out<best)best=out;
    }return best;
}
}
