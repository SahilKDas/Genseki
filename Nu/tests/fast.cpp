#include "state.hpp"
#include <iostream>
#include <random>
#include <thread>
void require(bool v){if(!v)throw std::runtime_error("fast feature integrity failure");}
int main()try {
 for(unsigned schema:{4u,5u,7u})for(unsigned width:{64u,128u}) {
  nu::Model model(width);model.feature_schema=schema;std::mt19937 rng(941);
  for(unsigned game=0;game<6;++game){nu::State state(model);std::vector<nu::State::Undo> undos;
   for(unsigned ply=0;ply<90&&!state.board.is_terminal();++ply){auto moves=state.board.legal_moves();undos.push_back(state.make(moves[rng()%moves.size()],true));
    if(ply%3==0)require(state.equivalent());}
   require(state.equivalent());while(!undos.empty()){state.unmake(undos.back());undos.pop_back();require(state.equivalent());}
  }
 }
 auto ant=nu::Board::from_position_string("G1|w|8|4|4|0,0=wA1,bB1;1,0=wQ;2,0=bQ");
 auto spider=nu::Board::from_position_string("G1|w|8|4|4|0,0=wS1,bB1;1,0=wQ;2,0=bQ");
 require(bool(ant)&&bool(spider));require(nu::fast_features(*ant).prior_white<nu::fast_features(*spider).prior_white);
 nu::Model zero;zero.feature_schema=5;std::fill(zero.output.begin(),zero.output.end(),0);
 nu::State state(zero,*ant);require(state.evaluate()==state.strategic_prior(nu::Color::white));
 require(state.strategic_prior(nu::Color::white)==-state.strategic_prior(nu::Color::black));
 auto snapshot=nu::fast_features(*ant);auto unchanged=nu::fast_features(*ant,&snapshot);require(unchanged.rebuilt_pieces==0);require(unchanged.active==snapshot.active);
 // Schema 4 occupied-stack beetle movement reaches the incremental mobility branch.
 nu::Model reference;reference.feature_schema=4;nu::State stack(reference,ant->with_side_to_move(nu::Color::black));
 bool exercised=false;
 for(auto move:stack.board.legal_moves())if(move.from&&*move.from==nu::Hex{0,0}&&move.to==nu::Hex{1,0}) {
  exercised=true;stack.feature_cache.clear();nu::Metrics profile;nu::metrics=&profile;auto undo=stack.make(move,true);require(stack.pending_move.has_value()&&stack.pending_unchanged);require(stack.equivalent());require(profile.mobility_incremental==1&&profile.mobility_full==0);nu::metrics=nullptr;stack.unmake(undo);require(stack.equivalent());
 }
 require(exercised);
 bool worker_ok=false;std::jthread worker([&]{nu::State local(zero,*spider);worker_ok=local.equivalent();});worker.join();require(worker_ok&&state.equivalent());
 std::cout<<"Nu schema 4/5 lazy, stack, prior, reconstruction and worker tests passed\n";
}catch(const std::exception& error){nu::metrics=nullptr;std::cerr<<error.what()<<'\n';return 1;}
