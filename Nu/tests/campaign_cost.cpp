#include "search.hpp"
#include <fstream>
#include <iostream>

int main(int argc,char** argv)try {
    if(argc!=3&&argc!=4)throw std::runtime_error("model, frozen G1 roots, optional hybrid mask required");
    nu::SearchOptions options;
    if(argc==4){options.hybrid=true;options.hybrid_terms=std::stoul(argv[3]);if(options.hybrid_terms>127)throw std::runtime_error("invalid mask");}
    nu::Model model;model.load(argv[1]);
    std::ifstream input(argv[2]);std::string line;
    std::uint64_t eval_ns=0,make_ns=0,reconstruction_ns=0;std::int64_t consumed=0;unsigned samples=0;
    while(std::getline(input,line)) {
        auto board=nu::Board::from_position_string(line);
        if(!board||board->is_terminal())throw std::runtime_error("invalid benchmark root");
        auto constructed=std::chrono::steady_clock::now();nu::State state(model,*board);
        reconstruction_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-constructed).count();
        auto moves=board->legal_moves();
        for(unsigned repeat=0;repeat<100;++repeat) {
            auto start=std::chrono::steady_clock::now();consumed+=nu::Search::evaluate(state,options);
            eval_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        }
        for(unsigned i=0;i<std::min<unsigned>(16,moves.size());++i) {
            auto start=std::chrono::steady_clock::now();auto undo=state.make(moves[i],true);
            consumed+=nu::Search::evaluate(state,options);state.unmake(undo);
            make_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
            if(!state.equivalent())throw std::runtime_error("make/unmake benchmark mismatch");
        }
        ++samples;
    }
    if(!samples)throw std::runtime_error("no benchmark roots");
    std::cout<<"{\"schema\":"<<model.feature_schema<<",\"roots\":"<<samples
             <<",\"evaluation_ns\":"<<eval_ns<<",\"make_evaluate_unmake_ns\":"<<make_ns
             <<",\"reconstruction_ns\":"<<reconstruction_ns
             <<",\"consumed_checksum\":"<<consumed<<"}\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
