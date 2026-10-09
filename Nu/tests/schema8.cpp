#include "search.hpp"
#include <iostream>
#include <random>

void require(bool value){if(!value)throw std::runtime_error("schema 8 parity failure");}
void compare(nu::State& optimized,nu::State& reference) {
    require(optimized.evaluate()==reference.evaluate());
    require(optimized.active==reference.active);
    require(optimized.accumulator.sums==reference.accumulator.sums);
    require(optimized.strategic_prior(nu::Color::white)==reference.strategic_prior(nu::Color::white));
    require(optimized.equivalent());
}
int main()try {
    for(unsigned width:{64u,128u})for(bool nonlinear:{false,true}) {
        nu::Model old(width);old.feature_schema=7;
        // Extreme int16 embeddings and bounded biases stress sign extension and
        // removal of negative weights without relying on benign trained values.
        for(unsigned i=0;i<old.embedding.size();++i)old.embedding[i]=i%2?-32768:32767;
        for(unsigned i=0;i<width;++i)old.bias[i]=i%2?-1000000:1000000;
        if(nonlinear) {
            old.head=32;old.head_weights.resize(32*2*width);old.head_bias.resize(32);old.output.resize(32);
            for(unsigned i=0;i<old.head_weights.size();++i)old.head_weights[i]=i%3?-32768:32767;
            for(unsigned i=0;i<32;++i){old.head_bias[i]=i%2?-1000000:1000000;old.output[i]=i%2?-32768:32767;}
        }
        auto next=old;next.feature_schema=8;std::mt19937 random(1701);
        for(unsigned game=0;game<6;++game) {
            nu::State optimized(next),reference(old);nu::FeatureCache cache;optimized.bind_cache(cache);
            optimized.eager_features=reference.eager_features=game%2!=0;
            std::vector<nu::State::Undo> a,b;
            for(unsigned ply=0;ply<90&&!reference.board.is_terminal();++ply) {
                compare(optimized,reference);auto moves=reference.legal();auto move=moves[random()%moves.size()];
                a.push_back(optimized.make(move,true));b.push_back(reference.make(move,true));
                if(ply%3==0)compare(optimized,reference);
            }
            compare(optimized,reference);
            while(!a.empty()){optimized.unmake(a.back());reference.unmake(b.back());a.pop_back();b.pop_back();compare(optimized,reference);}
            require(optimized.board.position_string()==nu::Board{}.position_string());
            auto detached=optimized;require(detached.worker_cache.value==nullptr);compare(detached,reference);
        }
    }
    nu::Model old;old.feature_schema=7;auto next=old;next.feature_schema=8;
    for(const char* text:{"G1|b|8|4|4|0,0=wA1,bB1;1,0=wQ;2,0=bQ",
                         "G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ"}) {
        auto board=nu::Board::from_position_string(text);require(bool(board));
        nu::State a(next,*board),b(old,*board);nu::FeatureCache cache;a.bind_cache(cache);
        compare(a,b);
        for(auto move:board->legal_moves()) {
            auto au=a.make(move,true),bu=b.make(move,true);compare(a,b);
            a.unmake(au);b.unmake(bu);compare(a,b);
        }
        nu::Search left(1),right(1);auto x=left.run(a,2,10000,1),y=right.run(b,2,10000,1);
        require(x.move==y.move&&x.score==y.score&&x.nodes==y.nodes&&x.pv==y.pv);
    }
    nu::FeatureWorkspace8 pool;
    auto first=pool.acquire();first->prior_white=123;
    auto second=pool.acquire();require(first.get()!=second.get()&&first->prior_white==123);
    auto released=second.get();second.reset();require(pool.acquire().get()==released);
    auto identity=nu::FeatureIdentity::from(nu::Board{},6),different=identity;different.ply=9;
    nu::FeatureCache cache;cache.store(7,identity,nu::CachedFeatures{});
    require(cache.find(7,identity)!=nullptr&&cache.find(7,different)==nullptr);
    cache.store(7,different,nu::CachedFeatures{});require(cache.find(7,identity)==nullptr);
    for(unsigned i=0;i<1000;++i){identity.ply=i;cache.store(i,identity,nu::CachedFeatures{});}
    require(cache.count==nu::FeatureCache::capacity);
    std::cout<<"schema 8 features, block deltas, overflow, pool and collision parity passed\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
