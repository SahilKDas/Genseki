#pragma once
#include "model.hpp"
#include <memory>
#include <chrono>

namespace nu {
struct Metrics {std::uint64_t features_ns=0,generation_ns=0,ordering_ns=0,tt_ns=0;};
inline thread_local Metrics* metrics=nullptr;
struct State {
    Board board;
    const Model* model;
    Mobility mobility{};
    Features active;
    Accumulator accumulator;
    std::uint64_t hash;
    std::uint64_t history_key;
    std::vector<std::uint64_t> path;
    std::vector<std::uint64_t> repeat_path;
    std::shared_ptr<const std::vector<Move>> move_cache;
    struct Undo { genseki::Undo board; Features previous; std::uint64_t hash,history_key; std::shared_ptr<const std::vector<Move>> moves; Mobility mobility; };
    explicit State(const Model& m,Board b={}):board(std::move(b)),model(&m),mobility(m.feature_schema==4?movement_counts(board):Mobility{}),active(features(board,m.feature_schema,&mobility)),accumulator(m),hash(position_hash(board)),history_key(mix(hash)),path{hash} {
        accumulator.refresh(m,active);
        repeat_path.push_back(repetition_hash(board));
    }
    Undo make(const Move& move,bool generated=false) {
        auto old=hash;auto previous_history=history_key;
        auto delta=mix(unsigned(board.side_to_move())+17)^mix(unsigned(other(board.side_to_move()))+17)
            ^mix(std::min<std::size_t>(board.ply(),8)+987)^mix(std::min<std::size_t>(board.ply()+1,8)+987);
        auto repeat_delta=delta;
        bool unchanged_occupancy=false;
        if(move.kind!=MoveKind::pass) {
            unsigned target_height=0;
            unsigned source_height=0;
            for(const auto& stack:board.stacks()) {
                if(stack.cell==move.to)target_height=unsigned(stack.pieces.size());
                if(move.from&&stack.cell==*move.from) {
                    source_height=unsigned(stack.pieces.size());
                    delta^=piece_hash(move.piece,*move.from,unsigned(stack.pieces.size()-1));
                    auto piece=move.piece;piece.id=0;repeat_delta^=piece_hash(piece,*move.from,unsigned(stack.pieces.size()-1));
                }
            }
            delta^=piece_hash(move.piece,move.to,target_height);
            auto piece=move.piece;piece.id=0;repeat_delta^=piece_hash(piece,move.to,target_height);
            unchanged_occupancy=move.kind==MoveKind::movement&&move.piece.bug==Bug::beetle&&source_height>1&&target_height>0;
        }
        genseki::Undo undo;
        if(generated)undo=board.make_generated_move(move);
        else {auto checked=board.make_move(move);if(!checked)throw std::runtime_error("attempted illegal move");undo=*checked;}
        Features next;
        Mobility next_mobility{};
        auto started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
        try {
            if(model->feature_schema==4)next_mobility=update_movement_counts(board,mobility,move,unchanged_occupancy);
            next=features(board,model->feature_schema,&next_mobility);
        }
        catch(...) {board.unmake_move(undo);throw;}
        if(metrics)metrics->features_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        accumulator.update(*model,active,next);
        auto before=std::move(active);active=std::move(next);
        auto cached=std::move(move_cache);move_cache.reset();
        hash=old^delta;path.push_back(hash);history_key=mix(history_key^hash);
        repeat_path.push_back(repeat_path.back()^repeat_delta);
        auto old_mobility=mobility;mobility=next_mobility;
        return {undo,std::move(before),old,previous_history,std::move(cached),old_mobility};
    }
    void unmake(const Undo& undo) {
        board.unmake_move(undo.board);
        accumulator.update(*model,active,undo.previous);
        active=undo.previous;hash=undo.hash;history_key=undo.history_key;path.pop_back();repeat_path.pop_back();move_cache=undo.moves;mobility=undo.mobility;
    }
    int evaluate() const {return accumulator.score(*model,board.side_to_move());}
    const std::vector<Move>& legal() {
        if(!move_cache) {
            auto started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
            move_cache=std::make_shared<const std::vector<Move>>(board.legal_moves());
            if(metrics)metrics->generation_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        }
        return *move_cache;
    }
    bool repetition()const{return match_repetition(repeat_path);}
    bool equivalent() const {
        auto refreshed=model->feature_schema==4?movement_counts(board):Mobility{};
        Accumulator reference(*model);reference.refresh(*model,features(board,model->feature_schema,&refreshed));
        auto history=mix(path.front());for(unsigned i=1;i<path.size();++i)history=mix(history^path[i]);
        return reference.sums==accumulator.sums&&hash==position_hash(board)&&history==history_key&&repeat_path.back()==repetition_hash(board)
            &&(model->feature_schema!=4||mobility==refreshed);
    }
    std::uint64_t context_key() const {
        // Conservative: history-dependent repetition scores must not cross contexts.
        return mix(hash^history_key);
    }
};
struct Applied {
    State& state;State::Undo undo;
    Applied(State& s,const Move& m):state(s),undo(s.make(m,true)){}
    Applied(const Applied&)=delete;
    Applied& operator=(const Applied&)=delete;
    ~Applied(){state.unmake(undo);}
};
}
