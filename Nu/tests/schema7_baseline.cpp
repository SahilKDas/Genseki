#include "search.hpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <new>
#include <random>

// Allocation requests, not live/peak memory. Instrumentation applies equally to both lanes.
static std::atomic<bool> counting{false};
static std::atomic<std::uint64_t> allocations{0}, requested_bytes{0};
void* operator new(std::size_t size) {
    if(void* value=std::malloc(size?size:1)) {
        if(counting.load(std::memory_order_relaxed)) {
            allocations.fetch_add(1,std::memory_order_relaxed);
            requested_bytes.fetch_add(size,std::memory_order_relaxed);
        }
        return value;
    }
    throw std::bad_alloc();
}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete(void* value) noexcept{std::free(value);}
void operator delete[](void* value) noexcept{std::free(value);}
void operator delete(void* value,std::size_t) noexcept{std::free(value);}
void operator delete[](void* value,std::size_t) noexcept{std::free(value);}

using Clock=std::chrono::steady_clock;
static std::int64_t consumed=0;
template<class Function> void measure(const char* name,Function function) {
    allocations=0;requested_bytes=0;counting=true;
    auto started=Clock::now();
    for(unsigned repeat=0;repeat<200;++repeat) {
        std::atomic_signal_fence(std::memory_order_seq_cst);
        function();
        std::atomic_signal_fence(std::memory_order_seq_cst);
    }
    auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
    counting=false;
    std::cout<<'"'<<name<<"\":{\"iterations\":200,\"ns\":"<<elapsed
             <<",\"allocations\":"<<allocations<<",\"requested_bytes\":"<<requested_bytes<<'}';
}

int main(int argc,char** argv)try {
    if(argc!=2)throw std::runtime_error("schema-7/8 model path required");
    nu::Model model;model.load(argv[1]);
    if(model.feature_schema!=7&&model.feature_schema!=8)throw std::runtime_error("schema 7 or 8 required");
    nu::Board middle;std::mt19937 random(823);
    for(unsigned ply=0;ply<16;++ply) {
        auto moves=middle.legal_moves();
        if(middle.is_terminal()||moves.empty())throw std::runtime_error("invalid seeded root");
        (void)middle.make_generated_move(moves[random()%moves.size()]);
    }
    auto stack=nu::Board::from_position_string("G1|b|8|4|4|0,0=wA1,bB1;1,0=wQ;2,0=bQ");
    auto tactical=nu::Board::from_position_string("G1|w|46|23|23|-2,3=bA2;-2,4=wA2;-2,5=bS2;-1,2=bG3;0,-3=wA3;0,-2=bA3;0,-1=wG1,bB1;0,0=bG2;0,1=bS1;1,-2=bQ;1,-1=wG2;1,0=wQ;2,-4=wB2;2,-3=wS2;2,-2=wA1;2,0=bA1;3,0=bG1,bB2;4,0=wS1;5,-1=wB1");
    if(!stack||!tactical)throw std::runtime_error("invalid fixtures");
    std::vector<std::pair<std::string,nu::Board>> roots{{"opening",{}},{"middlegame",middle},{"stacked",*stack},{"tactical",*tactical}};
    std::cout<<"{\"version\":1,\"schema\":"<<model.feature_schema<<",\"allocation_scope\":\"ordinary-new-requests\",\"components\":[";
    bool first=true;
    for(auto& [name,board]:roots) {
        if(!first)std::cout<<',';
        first=false;
        nu::State state(model,board);nu::FeatureCache worker_cache;state.bind_cache(worker_cache);
        auto moves=board.legal_moves();nu::FastFeatures8 fixed;nu::FeatureScratch8 scratch;
        std::cout<<"{\"category\":\""<<name<<"\",\"position\":\""<<board.position_string()<<"\",\"cache_entries\":"<<state.cache_entries()<<',';
        measure("features",[&]{
            if(model.feature_schema==8){nu::fast_features8(fixed,board,nullptr,scratch);consumed+=fixed.prior_white;for(auto& bank:fixed.active)for(auto feature:bank)consumed+=feature;}
            else {auto value=nu::fast_features(board,nullptr,7);consumed+=value.prior_white;for(auto& bank:value.active)for(auto feature:bank)consumed+=feature;}
        });std::cout<<',';
        measure("inference",[&]{consumed+=state.accumulator.score(model,board.side_to_move());});std::cout<<',';
        measure("board_copy",[&]{auto copy=board;consumed+=copy.ply()+copy.stacks().size();});std::cout<<',';
        measure("state_copy",[&]{auto copy=state;consumed+=copy.evaluate();});std::cout<<',';
        measure("move_generation",[&]{auto value=board.legal_moves();consumed+=value.size();for(auto& move:value)consumed+=move.to.q+move.to.r;});std::cout<<',';
        measure("make_evaluate_unmake",[&]{auto undo=state.make(moves.front(),true);consumed+=state.evaluate();state.unmake(undo);});
        if(!state.equivalent())throw std::runtime_error("state mismatch");
        std::cout<<'}';
    }
    std::cout<<"],\"search\":[";first=true;
    for(unsigned repeat=0;repeat<3;++repeat)for(unsigned threads:{1u,2u,4u,8u})for(auto& [name,board]:roots) {
        nu::State state(model,board);nu::Search search(16);nu::SearchOptions options;options.profile=true;
        allocations=0;requested_bytes=0;counting=true;auto started=Clock::now();
        auto result=search.run(state,64,230,threads,nullptr,options);
        double elapsed=std::chrono::duration<double,std::milli>(Clock::now()-started).count();counting=false;
        if(!board.is_legal(result.move)||!state.equivalent())throw std::runtime_error("invalid search");
        consumed+=result.score+result.depth+result.nodes+result.move.to.q+result.move.to.r;
        if(!first)std::cout<<',';
        first=false;
        std::cout<<"{\"category\":\""<<name<<"\",\"repeat\":"<<repeat<<",\"threads\":"<<threads
                 <<",\"ms\":"<<elapsed<<",\"deadline_failure\":"<<(elapsed>250?"true":"false")
                 <<",\"depth\":"<<result.depth<<",\"nodes\":"<<result.nodes<<",\"score\":"<<result.score
                 <<",\"allocations\":"<<allocations<<",\"requested_bytes\":"<<requested_bytes
                 <<",\"features_ns\":"<<result.profile.features_ns<<",\"inference_ns\":"<<result.profile.inference_ns
                 <<",\"generation_ns\":"<<result.profile.generation_ns<<",\"legal\":true}";
    }
    std::cout<<"],\"consumed_checksum\":"<<consumed<<"}\n";
}catch(const std::exception& error){counting=false;std::cerr<<error.what()<<'\n';return 1;}
