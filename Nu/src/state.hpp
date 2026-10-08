#pragma once
#include "model.hpp"
#include <memory>
#include <chrono>
#include <unordered_map>

namespace nu {
struct Metrics {std::uint64_t features_ns=0,generation_ns=0,ordering_ns=0,tt_ns=0,inference_ns=0,mobility_full=0,mobility_incremental=0,fast_piece_rebuilds=0;};
inline thread_local Metrics* metrics=nullptr;
struct State {
    Board board;
    const Model* model;
    mutable Mobility mobility{};
    mutable Features active;
    mutable Accumulator accumulator;
    mutable bool features_dirty=false;
    bool eager_features=false;
    mutable std::optional<Move> pending_move;
    mutable bool pending_unchanged=false;
    mutable std::shared_ptr<const FastFeatures> fast;
    struct CachedFeatures {Features active;Mobility mobility;};
    static auto& feature_cache() {
        static thread_local std::unordered_map<std::string,CachedFeatures> cache;
        return cache;
    }
    std::uint64_t hash;
    std::uint64_t history_key;
    std::vector<std::uint64_t> path;
    std::vector<std::uint64_t> repeat_path;
    std::shared_ptr<const std::vector<Move>> move_cache;
    struct Undo { genseki::Undo board; Features previous; std::uint64_t hash,history_key; std::shared_ptr<const std::vector<Move>> moves; Mobility mobility; bool dirty; std::optional<Move> pending; bool unchanged; std::shared_ptr<const FastFeatures> fast; };
    explicit State(const Model& m,Board b={}):board(std::move(b)),model(&m),mobility((m.feature_schema==4||m.feature_schema==6)?movement_counts(board):Mobility{}),active(features(board,m.feature_schema,&mobility)),accumulator(m),hash(position_hash(board)),history_key(mix(hash)),path{hash} {
        if(m.feature_schema==fast_schema){fast=std::make_shared<FastFeatures>(fast_features(board));active=fast->active;}
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
        auto before=active;auto old_mobility=mobility;auto old_dirty=features_dirty;
        auto old_pending=pending_move;auto old_unchanged=pending_unchanged;auto old_fast=fast;
        pending_move=old_dirty?std::nullopt:std::optional<Move>(move);pending_unchanged=unchanged_occupancy;
        features_dirty=true;
        try {if(eager_features)ensure_features(old_dirty?nullptr:&move,unchanged_occupancy);}
        catch(...) {board.unmake_move(undo);features_dirty=old_dirty;pending_move=old_pending;pending_unchanged=old_unchanged;fast=old_fast;throw;}
        auto cached=std::move(move_cache);move_cache.reset();
        hash=old^delta;path.push_back(hash);history_key=mix(history_key^hash);
        repeat_path.push_back(repeat_path.back()^repeat_delta);
        return {undo,std::move(before),old,previous_history,std::move(cached),old_mobility,old_dirty,old_pending,old_unchanged,std::move(old_fast)};
    }
    void unmake(const Undo& undo) {
        board.unmake_move(undo.board);
        accumulator.update(*model,active,undo.previous);
        active=undo.previous;hash=undo.hash;history_key=undo.history_key;path.pop_back();repeat_path.pop_back();move_cache=undo.moves;mobility=undo.mobility;features_dirty=undo.dirty;pending_move=undo.pending;pending_unchanged=undo.unchanged;fast=undo.fast;
    }
    void ensure_features(const Move* move=nullptr,bool unchanged_occupancy=false) const {
        if(!features_dirty)return;
        auto started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
        if(model->feature_schema==fast_schema) {
            auto next=std::make_shared<FastFeatures>(fast_features(board,fast.get()));
            if(metrics)metrics->fast_piece_rebuilds+=next->rebuilt_pieces;
            accumulator.update(*model,active,next->active);
            active=next->active;fast=std::move(next);features_dirty=false;pending_move.reset();
            if(metrics)metrics->features_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
            return;
        }
        if(!move&&pending_move){move=&*pending_move;unchanged_occupancy=pending_unchanged;}
        // Thread-local and bounded: full serialized keys avoid hash aliasing and locks.
        // Inputs depend on the schema and board, not network weights or search history.
        auto& cache=feature_cache();
        std::string identity;
        if(!eager_features) {
            identity=std::to_string(model->feature_schema)+":"+board.position_string();
            auto found=cache.find(identity);
            if(found!=cache.end()) {
                auto next=found->second.active;
                accumulator.update(*model,active,next);
                active=std::move(next);mobility=found->second.mobility;features_dirty=false;pending_move.reset();
                if(metrics)metrics->features_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
                return;
            }
        }
        // Build into temporaries so cancellation leaves the cached ancestor intact.
        if(metrics&&(model->feature_schema==4||model->feature_schema==6)){if(move&&unchanged_occupancy)++metrics->mobility_incremental;else ++metrics->mobility_full;}
        auto next_mobility=(model->feature_schema==4||model->feature_schema==6)?
            (move?update_movement_counts(board,mobility,*move,unchanged_occupancy):movement_counts(board)):Mobility{};
        auto next=features(board,model->feature_schema,&next_mobility);
        if(!eager_features) {
            if(cache.size()>=256)cache.erase(cache.begin());
            cache.emplace(std::move(identity),CachedFeatures{next,next_mobility});
        }
        accumulator.update(*model,active,next);
        active=std::move(next);mobility=next_mobility;features_dirty=false;pending_move.reset();
        if(metrics)metrics->features_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
    }
    int strategic_prior(Color side) const {
        if(model->feature_schema!=fast_schema)return 0;
        ensure_features();return side==Color::white?fast->prior_white:-fast->prior_white;
    }
    int evaluate() const {
        ensure_features();auto started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
        int score=std::clamp(accumulator.score(*model,board.side_to_move())+strategic_prior(board.side_to_move()),-6800,6800);
        if(metrics)metrics->inference_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        return score;
    }
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
        ensure_features();
        auto refreshed=(model->feature_schema==4||model->feature_schema==6)?movement_counts(board):Mobility{};
        Accumulator reference(*model);reference.refresh(*model,features(board,model->feature_schema,&refreshed));
        auto history=mix(path.front());for(unsigned i=1;i<path.size();++i)history=mix(history^path[i]);
        return reference.sums==accumulator.sums&&(model->feature_schema!=fast_schema||fast->prior_white==fast_features(board).prior_white)&&hash==position_hash(board)&&history==history_key&&repeat_path.back()==repetition_hash(board)
            &&((model->feature_schema!=4&&model->feature_schema!=6)||mobility==refreshed);
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
