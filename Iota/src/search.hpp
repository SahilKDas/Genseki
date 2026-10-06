#pragma once
#include "model.hpp"
#include <chrono>
#include <unordered_map>

namespace iota {
struct Interrupted {};
struct SearchResult {Move move{};int depth=0;uint64_t nodes=0;float value=0;std::vector<Move> pv;std::vector<float> policy;};
struct Entry {uint64_t key=0;Move move{};float score=0;int depth=-1,bound=0;unsigned age=0;};
struct Search {
    const Model& model;std::chrono::steady_clock::time_point deadline;
    std::vector<std::array<Entry,4>> table;
    std::unordered_map<std::string,int> history;
    std::unordered_map<std::string,Prediction> evaluations;
    std::array<std::array<Move,2>,128> killers{};
    std::vector<uint64_t> path;uint64_t nodes=0;unsigned age=0;
    explicit Search(const Model& m,size_t mib=16):model(m),table(std::max(size_t(1),mib*1024*1024/sizeof(table[0]))){}
    void check(){if(std::chrono::steady_clock::now()>=deadline)throw Interrupted{};}
    static void callback(void* p){static_cast<Search*>(p)->check();}
    struct Hook {Hook(Search& s){nu_generation_check=callback;nu_generation_context=&s;}~Hook(){nu_generation_check=nullptr;nu_generation_context=nullptr;}};
    struct Applied {
        Board& board;Undo undo;std::vector<uint64_t>& path;
        Applied(Board& b,const Move& m,std::vector<uint64_t>& p):board(b),undo(b.make_generated_move(m)),path(p){path.push_back(hash(b));}
        ~Applied(){path.pop_back();board.unmake_move(undo);}
    };
    float terminal(const Board& b,int ply) const {auto r=b.result();if(r==GameResult::draw)return 0;bool win=(r==GameResult::white_win)==(b.side_to_move()==Color::white);return win?10000-ply:-10000+ply;}
    uint64_t key(const Board& b)const {uint64_t k=hash(b);for(auto p:path){k^=p+0x9e3779b97f4a7c15ull+(k<<6)+(k>>2);}return k;}
    static float stored(float v,int ply){return v>9000?v+ply:v<-9000?v-ply:v;}
    static float restored(float v,int ply){return v>9000?v-ply:v<-9000?v+ply:v;}
    Prediction evaluate(const Board& b,const std::vector<Move>& moves){
        auto identity=b.position_string();auto found=evaluations.find(identity);if(found!=evaluations.end())return found->second;
        auto p=model.predict(b,moves,[&]{check();});if(evaluations.size()>=256)evaluations.erase(evaluations.begin());evaluations.emplace(std::move(identity),p);return p;
    }
    float ab(Board& b,int depth,float alpha,float beta,int ply,std::vector<Move>& pv){
        check();++nodes;if(b.is_terminal())return terminal(b,ply);
        if(std::count(path.begin(),path.end(),hash(b))>=3)return 0;
        auto k=key(b);auto& bucket=table[k%table.size()];Entry* hit=nullptr;for(auto& t:bucket)if(t.depth>=0&&t.key==k){hit=&t;break;}
        if(hit&&hit->depth>=depth){float v=restored(hit->score,ply);if(hit->bound==0||(hit->bound==1&&v>=beta)||(hit->bound==2&&v<=alpha)){pv={hit->move};return v;}}
        auto moves=b.legal_moves();
        // Exact one-ply terminal wins precede neural evaluation, including at leaves.
        for(auto m:moves){check();Applied a(b,m,path);if(b.is_terminal()){float score=-terminal(b,ply+1);if(score>9000){pv={m};return score;}}}
        auto pred=evaluate(b,moves);
        if(depth<=0)return pred.value*1000;
        std::vector<size_t> order(moves.size());std::iota(order.begin(),order.end(),0);
        std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t c){auto score=[&](size_t i){return pred.policy[i]+history[move_notation(moves[i])]/1024.f+(hit&&moves[i]==hit->move?1e6f:0)+(ply<128&&moves[i]==killers[ply][0]?1000.f:0);};return score(a)>score(c);});
        float original=alpha,best=-20000;Move chosen=moves.front();bool first=true;
        for(auto i:order){std::vector<Move> child;float score;{Applied a(b,moves[i],path);if(first)score=-ab(b,depth-1,-beta,-alpha,ply+1,child);else {score=-ab(b,depth-1,-alpha-0.01f,-alpha,ply+1,child);if(score>alpha&&score<beta)score=-ab(b,depth-1,-beta,-alpha,ply+1,child);}}
            first=false;if(score>best){best=score;chosen=moves[i];pv={chosen};pv.insert(pv.end(),child.begin(),child.end());}alpha=std::max(alpha,score);if(alpha>=beta){auto& h=history[move_notation(chosen)];h=std::min(32768,h+depth*depth);if(ply<128){killers[ply][1]=killers[ply][0];killers[ply][0]=chosen;}break;}}
        auto replace=std::min_element(bucket.begin(),bucket.end(),[&](auto& a,auto& c){return a.depth-int(age-a.age)*4<c.depth-int(age-c.age)*4;});if(hit)replace=bucket.begin()+(hit-bucket.data());*replace={k,chosen,stored(best,ply),depth,best<=original?2:best>=beta?1:0,age};return best;
    }
    struct Node {Move move{};float prior=1,sum=0;int visits=0;std::vector<size_t> children;};
    SearchResult run(Board board,int milliseconds,int maxdepth,const std::string& mode,const std::vector<uint64_t>& gamehistory={}){
        if(mode!="alphabeta"&&mode!="mcts")throw std::runtime_error("unsupported search mode");
        // Generate the legal fallback before enabling cancellation. Its cost is reported in wall time.
        auto start=std::chrono::steady_clock::now();auto legal=board.legal_moves();if(legal.empty())throw std::runtime_error("terminal position has no bestmove");
        SearchResult result;result.move=legal.front();deadline=start+std::chrono::milliseconds(std::max(0,milliseconds));nodes=0;path=gamehistory;if(path.empty()||path.back()!=hash(board))path.push_back(hash(board));++age;for(auto& [m,h]:history)h/=2;Hook hook(*this);
        try {if(mode=="alphabeta")for(int d=1;d<=maxdepth;++d){std::vector<Move> pv;float window=d>1?100:20000,lo=d>1?result.value-window:-20000,hi=d>1?result.value+window:20000;float v=ab(board,d,lo,hi,0,pv);if(v<=lo||v>=hi){pv.clear();v=ab(board,d,-20000,20000,0,pv);}check();result.value=v;result.depth=d;if(!pv.empty()){result.move=pv[0];result.pv=pv;}if(std::abs(v)>9000)break;}
        else {
            std::vector<Node> tree(1);tree.reserve(16384);
            while(tree.size()<16384){check();Board b=board;auto saved=path;std::vector<size_t> trace{0};size_t n=0;int ply=0;
                while(!tree[n].children.empty()&&!b.is_terminal()){float best=-1e30;size_t chosen=tree[n].children[0];for(auto c:tree[n].children){auto& ch=tree[c];float q=ch.visits?-ch.sum/ch.visits:0;float u=1.5f*ch.prior*std::sqrt(float(tree[n].visits+1))/(ch.visits+1);if(q+u>best){best=q+u;chosen=c;}}(void)b.make_generated_move(tree[chosen].move);path.push_back(hash(b));trace.push_back(chosen);n=chosen;++ply;if(std::count(path.begin(),path.end(),hash(b))>=3)break;}
                float v=0;if(b.is_terminal())v=terminal(b,ply)/10000;else if(std::count(path.begin(),path.end(),hash(b))<3){auto moves=b.legal_moves();auto p=model.predict(b,moves,[&]{check();});v=p.value;float mx=*std::max_element(p.policy.begin(),p.policy.end()),sum=0;for(auto& x:p.policy){x=std::exp(x-mx);sum+=x;}if(tree.size()+moves.size()>16384){path=saved;break;}for(size_t i=0;i<moves.size();++i){size_t c=tree.size();tree.push_back({moves[i],p.policy[i]/sum});tree[n].children.push_back(c);}}
                for(auto it=trace.rbegin();it!=trace.rend();++it){tree[*it].sum+=v;++tree[*it].visits;v=-v;}path=saved;++nodes;
                if(!tree[0].children.empty()){auto c=*std::max_element(tree[0].children.begin(),tree[0].children.end(),[&](auto a,auto c){return tree[a].visits<tree[c].visits;});result.move=tree[c].move;result.value=tree[c].visits?-tree[c].sum/tree[c].visits*1000:0;result.pv={result.move};result.policy.clear();float visits=0;for(auto child:tree[0].children)visits+=tree[child].visits;for(auto child:tree[0].children)result.policy.push_back(visits?tree[child].visits/visits:tree[child].prior);}
            }
        }}catch(const Interrupted&){}path=gamehistory;if(path.empty()||path.back()!=hash(board))path.push_back(hash(board));result.nodes=nodes;return result;
    }
};
}
