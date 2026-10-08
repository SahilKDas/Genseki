#include "state.hpp"
#include <iostream>
#include <random>
int main(int argc,char** argv)try {
 if(argc!=3)throw std::runtime_error("schema 4 and schema 5 model paths required");
 nu::Model old,fast;old.load(argv[1]);fast.load(argv[2]);
 if(old.feature_schema!=4||fast.feature_schema!=5||old.hidden!=fast.hidden)throw std::runtime_error("matched widths and explicit schemas required");
 std::array<nu::Metrics,2> profiles{};std::array<std::uint64_t,2> wall{};unsigned samples=0;std::array<std::int64_t,2> score_checksum{};
 std::mt19937 rng(917);nu::Board board;
 for(unsigned ply=0;ply<40&&!board.is_terminal();++ply){
  auto moves=board.legal_moves();
  if(ply>=8&&ply%4==0)for(unsigned i=0;i<std::min<unsigned>(24,moves.size());++i)for(unsigned repeat=0;repeat<3;++repeat){
   for(unsigned lane=0;lane<2;++lane){unsigned mode=(lane+repeat)%2;const auto& model=mode?fast:old;
    nu::State state(model,board);state.eager_features=true;nu::metrics=&profiles[mode];
    auto start=std::chrono::steady_clock::now();auto undo=state.make(moves[i],true);score_checksum[mode]+=state.evaluate();state.unmake(undo);
    wall[mode]+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();nu::metrics=nullptr;
    if(!state.equivalent())throw std::runtime_error("reconstruction disagreement");
   }++samples;
  }
  (void)board.make_generated_move(moves[rng()%moves.size()]);
 }
 std::cout<<"{\"same_move_samples\":"<<samples<<",\"schema4_ns\":"<<wall[0]<<",\"schema5_ns\":"<<wall[1]
 <<",\"schema4_features_ns\":"<<profiles[0].features_ns<<",\"schema5_features_ns\":"<<profiles[1].features_ns
 <<",\"schema4_inference_ns\":"<<profiles[0].inference_ns<<",\"schema5_inference_ns\":"<<profiles[1].inference_ns
 <<",\"score_checksums\":["<<score_checksum[0]<<','<<score_checksum[1]<<"]"
 <<",\"schema5_full_mobility_calls\":"<<profiles[1].mobility_full<<",\"schema5_piece_rebuilds\":"<<profiles[1].fast_piece_rebuilds<<"}\n";
 return 0;
}catch(const std::exception& error){nu::metrics=nullptr;std::cerr<<error.what()<<'\n';return 1;}
