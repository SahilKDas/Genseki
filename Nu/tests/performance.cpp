#include "search.hpp"
#include <iostream>
#include <random>

int main(int argc,char** argv)try {
    if(argc!=2)throw std::runtime_error("model path required");
    nu::Model model;model.load(argv[1]);
    double elapsed[2]{};std::uint64_t features[2]{},nodes[2]{};unsigned samples=0;
    for(unsigned seed:{823u,881u}) {
        std::mt19937 random(seed);nu::Board board;
        for(unsigned ply=0;ply<=20&&!board.is_terminal();++ply) {
            if(ply%4==0)for(unsigned repeat=0;repeat<3;++repeat) {
                nu::SearchResult results[2];
                // Alternate execution order to reduce systematic warm-cache bias.
                for(unsigned lane=0;lane<2;++lane) {
                    unsigned mode=(lane+repeat)%2;
                    nu::State state(model,board);state.eager_features=mode==0;
                    nu::State::feature_cache().clear();
                    nu::Search search(16);nu::SearchOptions options;options.profile=true;
                    auto start=std::chrono::steady_clock::now();
                    results[mode]=search.run(state,2,5000,1,nullptr,options);
                    elapsed[mode]+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
                    features[mode]+=results[mode].profile.features_ns;nodes[mode]+=results[mode].nodes;
                    if(results[mode].depth!=2||!state.equivalent())throw std::runtime_error("incomplete or invalid benchmark");
                }
                if(results[0].score!=results[1].score||results[0].move!=results[1].move||results[0].nodes!=results[1].nodes)
                    throw std::runtime_error("reference search disagreement");
                ++samples;
            }
            auto moves=board.legal_moves();(void)board.make_generated_move(moves[random()%moves.size()]);
        }
    }
    std::cout<<"{\"paired_samples\":"<<samples<<",\"depth\":2,\"eager_ms\":"<<elapsed[0]
        <<",\"lazy_ms\":"<<elapsed[1]<<",\"speedup\":"<<elapsed[0]/elapsed[1]
        <<",\"eager_feature_ns\":"<<features[0]<<",\"lazy_feature_ns\":"<<features[1]
        <<",\"eager_nodes\":"<<nodes[0]<<",\"lazy_nodes\":"<<nodes[1]<<",\"equal_results\":true}\n";
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
