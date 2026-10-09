#pragma once
#include "state.hpp"
#include "hybrid.hpp"
#include <atomic>
#include <mutex>
#include <thread>

namespace nu {
inline thread_local unsigned generation_checks=0;
struct SearchOptions {unsigned threat_plies=0;bool lmr=false,profile=false,adaptive=false,hybrid=false,deadline_guard=false,cooperative_ordering=false,root_pvs=false;unsigned hybrid_weight=100,hybrid_terms=63;};
struct SearchTiming {std::uint64_t setup_ns=0,join_ns=0,total_ns=0,stop_lag_ns=0,reply_ns=0;};
struct SearchResult {Move move{};int score=0;unsigned depth=0;std::uint64_t nodes=0;std::vector<Move> pv;Metrics profile;SearchTiming timing;};
class Search {
    struct Entry {std::uint64_t key=0,context=0;int value=0,depth=-1,bound=0;Move move{};unsigned age=0;};
    using Bucket=std::array<Entry,4>;
    std::vector<Bucket> table;
    std::array<std::mutex,64> locks;
    std::atomic<bool> stopped{false};
    std::atomic<std::uint64_t> nodes{0};
    std::chrono::steady_clock::time_point deadline;
    unsigned age=0;
    SearchOptions options;
    const Model* table_model=nullptr;
    struct Interrupted {};
    void checkpoint()const {
        if(stopped.load(std::memory_order_relaxed)||std::chrono::steady_clock::now()>=deadline)throw Interrupted{};
    }
    struct GenerationScope {
        void (*previous)(void*);void* context;Metrics* previous_metrics;
        GenerationScope(Search& search,Metrics* profile):previous(nu_generation_check),context(nu_generation_context),previous_metrics(metrics) {
            generation_checks=0;nu_generation_context=&search;
            nu_generation_check=[](void* p){
                auto& search=*static_cast<Search*>(p);
                if(search.options.deadline_guard||(++generation_checks&3)==0||search.stopped.load(std::memory_order_relaxed))search.checkpoint();
            };metrics=profile;
        }
        ~GenerationScope(){nu_generation_check=previous;nu_generation_context=context;metrics=previous_metrics;}
    };
    struct Ordering {
        std::uint64_t visited=0;
        std::array<std::array<std::optional<Move>,2>,128> killers{};
        std::array<std::array<int,8192>,2> history{};
        std::array<std::optional<Move>,8192> counters{};
        std::array<std::vector<Move>,128> move_buffers,pv_buffers;
        std::array<std::vector<std::pair<Move,int>>,128> rank_buffers;
        static unsigned index(const Move& m) {
            auto value=std::uint64_t(slot(m.piece))^(std::uint64_t(std::uint16_t(m.to.q))<<16)
                ^(std::uint64_t(std::uint16_t(m.to.r))<<32)^(std::uint64_t(m.kind)<<56);
            return unsigned(mix(value)%8192);
        }
        void decay(){for(auto& side:history)for(auto& value:side)value=value*3/4;}
        int score(const Move& m,unsigned ply,Color side,const std::optional<Move>& previous)const {
            int value=history[unsigned(side)][index(m)];
            if(previous&&counters[index(*previous)]==m)value+=80000;
            if(ply<killers.size()) {
                if(killers[ply][0]==m)value+=100000;
                else if(killers[ply][1]==m)value+=90000;
            }
            return value;
        }
        void cutoff(const Move& m,unsigned ply,Color side,int depth,const std::optional<Move>& previous) {
            if(ply<killers.size()&&killers[ply][0]!=m){killers[ply][1]=killers[ply][0];killers[ply][0]=m;}
            if(previous)counters[index(*previous)]=m;
            auto& value=history[unsigned(side)][index(m)];value=std::min(80000,value+depth*depth);
        }
    };
    static int terminal(const Board& board,unsigned ply) {
        auto result=board.result();if(result==GameResult::draw)return 0;
        return ((result==GameResult::white_win)==(board.side_to_move()==Color::white))?100000-int(ply):-100000+int(ply);
    }
    static unsigned liberties(const Board& board,Color color) {
        for(const auto& stack:board.stacks())for(auto p:stack.pieces)if(p.color==color&&p.bug==Bug::queen) {
            unsigned free=0;
            for(auto direction:directions) {
                auto cell=add(stack.cell,direction);
                free+=std::none_of(board.stacks().begin(),board.stacks().end(),[&](const Stack& s){return s.cell==cell;});
            }
            return free;
        }
        return 7;
    }
    static bool tactical(const Board& board,const Move& move) {
        if(move.kind==MoveKind::pass||move.piece.bug==Bug::queen||move.piece.bug==Bug::beetle)return true;
        for(const auto& stack:board.stacks())for(auto piece:stack.pieces)if(piece.bug==Bug::queen) {
            if(adjacent(stack.cell,move.to)||stack.cell==move.to||(move.from&&adjacent(stack.cell,*move.from)))return true;
        }
        return false;
    }
    bool winning_reply(const Board& original,Color side) {
        if(liberties(original,other(side))>1)return false;
        auto board=original.with_side_to_move(side);
        for(auto move:board.legal_moves()) {
            checkpoint();auto undo=board.make_generated_move(move);auto result=board.result();board.unmake_move(undo);
            if(result==(side==Color::white?GameResult::white_win:GameResult::black_win))return true;
        }
        return false;
    }
    int cooperation(const Board& board,const Move& move,unsigned own,unsigned enemy) {
        if(move.kind==MoveKind::pass)return 0;
        Board child=board;auto undo=child.make_generated_move(move);(void)undo;
        const auto mover=board.side_to_move();
        if(child.is_terminal())return child.result()==GameResult::draw?0:
            child.result()==(mover==Color::white?GameResult::white_win:GameResult::black_win)?1000000:-1000000;
        const auto after_own=liberties(child,mover),after_enemy=liberties(child,other(mover));
        int score=0;
        if(own<=2&&after_own>own)score+=140000;
        if(own<=2&&after_own<own)score-=180000;
        if(enemy<=3&&after_enemy<enemy)score+=50000;
        // A visually closed liberty is not necessarily an executable surround.
        if(own==1)score+=winning_reply(child,other(mover))?-400000:400000;
        std::array<Hex,22> cells{};unsigned count=0;
        for(const auto& stack:child.stacks())cells[count++]=stack.cell;
        auto pins=pins8(cells,count);
        std::optional<Hex> queen;
        for(const auto& stack:child.stacks())for(auto piece:stack.pieces)
            if(piece.color==other(mover)&&piece.bug==Bug::queen)queen=stack.cell;
        if(queen)for(unsigned i=0;i<count;++i) {
            const auto& stack=child.stacks()[i];auto piece=stack.pieces.back();
            if(piece.color==other(mover)&&piece.bug!=Bug::queen&&adjacent(stack.cell,*queen)&&
               stack.pieces.size()==1&&pins[i])score+=8000;
        }
        return score;
    }
    bool reduction_safe(const Board& board,const Move& move)const {
        // Never reduce a remote defense merely because it is not Queen-adjacent.
        return !tactical(board,move)&&liberties(board,board.side_to_move())>2&&
               liberties(board,other(board.side_to_move()))>2;
    }
    int threat(State& state,int alpha,int beta,unsigned ply,unsigned remaining,std::vector<Move>& pv,Ordering& ordering) {
        checkpoint();++ordering.visited;
        if(state.board.is_terminal())return terminal(state.board,ply);
        if(state.repetition())return 0;
        const unsigned threshold=options.threat_plies>=2?2:1;
        if(!remaining||(liberties(state.board,Color::white)>threshold&&liberties(state.board,Color::black)>threshold))return evaluate(state,options);
        const auto mover=state.board.side_to_move();
        bool danger=winning_reply(state.board,other(mover));
        int best=danger?-100001:evaluate(state,options);
        bool defense=false;
        // Only actual wins and replies that remove every immediate winning response extend.
        for(auto move:state.legal()) {
            checkpoint();Applied applied(state,move);auto result=state.board.result();
            bool win=result==(mover==Color::white?GameResult::white_win:GameResult::black_win);
            if(!win&&!danger) {
                if(threshold==1||remaining<2||!winning_reply(state.board,mover))continue;
            }
            if(result==GameResult::ongoing&&!state.repetition()&&winning_reply(state.board,other(mover)))continue;
            defense=true;auto& child=ordering.pv_buffers[ply+1];child.clear();
            int value=-threat(state,-beta,-alpha,ply+1,remaining-1,child,ordering);
            if(value>best){best=value;pv={move};pv.insert(pv.end(),child.begin(),child.end());}
            alpha=std::max(alpha,value);if(alpha>=beta)break;
        }
        if(danger&&!defense)return -100000+int(ply)+2;
        return best;
    }
    Entry probe(std::uint64_t key,std::uint64_t context) {
        const auto index=key%table.size();std::lock_guard guard(locks[index%locks.size()]);
        Entry best;
        for(auto entry:table[index])if(entry.depth>=0&&entry.key==key) {
            if(entry.context==context)return entry;
            if(entry.depth>best.depth)best=entry;
        }
        return best;
    }
    void save(Entry next) {
        const auto index=next.key%table.size();std::lock_guard guard(locks[index%locks.size()]);
        auto& bucket=table[index];auto victim=bucket.begin();
        for(auto it=bucket.begin();it!=bucket.end();++it) {
            if(it->key==next.key&&it->context==next.context&&it->depth>=0) {
                if(it->depth>next.depth&&next.bound!=0)return;
                victim=it;break;
            }
            if(it->depth<0){victim=it;break;}
            auto priority=[&](const Entry& e){return e.depth-8*int(age-e.age);};
            if(priority(*it)<priority(*victim))victim=it;
        }
        *victim=next;
    }
    int visit(State& s,int depth,int alpha,int beta,unsigned ply,std::vector<Move>& pv,Ordering& ordering,bool pv_node=true) {
        ++ordering.visited;checkpoint();
        if(s.board.is_terminal())return terminal(s.board,ply);
        if(s.repetition())return 0;
        if(depth<=0)return options.threat_plies?threat(s,alpha,beta,ply,options.threat_plies,pv,ordering):evaluate(s,options);
        const auto key=s.hash,context=s.context_key();
        auto started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
        auto cached=probe(key,context);
        if(metrics)metrics->tt_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        auto unpack=[&](int value){return value>90000?value-int(ply):value<-90000?value+int(ply):value;};
        if(cached.depth>=depth&&cached.key==key&&cached.context==context) {
            auto value=unpack(cached.value);
            if(cached.bound==0||(cached.bound==1&&value>=beta)||(cached.bound==2&&value<=alpha))return value;
        }
        auto& moves=ordering.move_buffers[ply];moves=s.legal();const auto mover=s.board.side_to_move();
        std::optional<Move> previous=s.board.history().empty()?std::nullopt:std::optional<Move>(s.board.history().back());
        started=metrics?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
        auto& ranked=ordering.rank_buffers[ply];ranked.clear();ranked.reserve(moves.size());
        const auto own=options.cooperative_ordering?liberties(s.board,mover):7;
        const auto enemy=options.cooperative_ordering?liberties(s.board,other(mover)):7;
        for(auto move:moves) {
            checkpoint();
            auto priority=ordering.score(move,ply,mover,previous)+(tactical(s.board,move)?20000:0);
            if(options.cooperative_ordering&&(own<=2||enemy<=3))priority+=cooperation(s.board,move,own,enemy);
            ranked.emplace_back(move,priority);
        }
        std::stable_sort(ranked.begin(),ranked.end(),[](auto& a,auto& b){return a.second>b.second;});
        for(unsigned i=0;i<moves.size();++i)moves[i]=ranked[i].first;
        if(cached.depth>=0&&cached.key==key){auto found=std::find(moves.begin(),moves.end(),cached.move);if(found!=moves.end())std::rotate(moves.begin(),found,found+1);}
        if(metrics)metrics->ordering_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        int original=alpha,best=-100001;Move selected=moves.front();
        for(unsigned i=0;i<moves.size();++i) {
            bool reduce=options.lmr&&!pv_node&&depth>=3&&i>=4&&moves.size()>1&&reduction_safe(s.board,moves[i])&&moves[i]!=cached.move;
            Applied applied(s,moves[i]);auto& child=ordering.pv_buffers[ply+1];child.clear();int value;
            if(i==0)value=-visit(s,depth-1,-beta,-alpha,ply+1,child,ordering,pv_node);
            else {
                value=-visit(s,depth-1-int(reduce),-alpha-1,-alpha,ply+1,child,ordering,false);
                if(reduce&&value>alpha){child.clear();value=-visit(s,depth-1,-alpha-1,-alpha,ply+1,child,ordering,false);}
                if(value>alpha&&value<beta){child.clear();value=-visit(s,depth-1,-beta,-alpha,ply+1,child,ordering,pv_node);}
            }
            if(value>best){best=value;selected=moves[i];pv={selected};pv.insert(pv.end(),child.begin(),child.end());}
            alpha=std::max(alpha,value);if(alpha>=beta){ordering.cutoff(moves[i],ply,mover,depth,previous);break;}
        }
        int packed=best>90000?best+int(ply):best<-90000?best-int(ply):best;
        save({key,context,packed,depth,best<=original?2:best>=beta?1:0,selected,age});return best;
    }
public:
    static int evaluate(const State& state,const SearchOptions& settings) {
        int base=state.evaluate();
        if(!settings.hybrid||!settings.hybrid_weight)return base;
        int bonus=handcrafted_white(state.board,settings.hybrid_terms)*(state.board.side_to_move()==Color::white?1:-1);
        return std::clamp(base+bonus*int(settings.hybrid_weight)/100,-8000,8000);
    }
    std::size_t allocated_table_bytes()const {return table.capacity()*sizeof(Bucket);}
    explicit Search(unsigned mib=16,std::size_t bucket_limit=0):table(std::max<std::size_t>(1,
        std::min(bucket_limit?bucket_limit:std::numeric_limits<std::size_t>::max(),std::size_t(std::clamp(mib,1u,256u))*1024*1024/sizeof(Bucket)))){}
    void cancel(){stopped.store(true,std::memory_order_relaxed);}
    SearchResult run(const State& initial,unsigned max_depth,double milliseconds,unsigned threads=1,std::atomic<bool>* entered=nullptr,SearchOptions settings={}) {
        auto started=std::chrono::steady_clock::now();
        if(!std::isfinite(milliseconds)||milliseconds<0||milliseconds>60000)throw std::runtime_error("invalid search time");
        if(settings.threat_plies>4||max_depth>64||settings.hybrid_weight>200||settings.hybrid_terms>127)throw std::runtime_error("search bounds exceeded");
        if(age&&(table_model!=initial.model||settings.threat_plies!=options.threat_plies||settings.lmr!=options.lmr||settings.cooperative_ordering!=options.cooperative_ordering||settings.root_pvs!=options.root_pvs||settings.hybrid!=options.hybrid||settings.hybrid_weight!=options.hybrid_weight||settings.hybrid_terms!=options.hybrid_terms)) {
            for(auto& bucket:table)for(auto& entry:bucket)entry.depth=-1;
        }
        table_model=initial.model;options=settings;stopped=false;nodes=0;++age;
        // Account for setup and reserve bounded time for unwinding and response preparation.
        auto reserve=std::min(settings.deadline_guard?35.0:10.0,milliseconds*(settings.deadline_guard?.2:.05));
        deadline=started+std::chrono::microseconds(std::int64_t(std::max(0.0,milliseconds-reserve)*1000));
        if(entered)entered->store(true);
        State root=initial;auto moves=root.legal();if(moves.empty())throw std::runtime_error("game over");
        SearchResult completed;completed.move=moves.front();completed.pv={completed.move};
        if(options.cooperative_ordering) {
            GenerationScope scope(*this,nullptr);
            try {
                const auto own=liberties(root.board,root.board.side_to_move());
                const auto enemy=liberties(root.board,other(root.board.side_to_move()));
                if(own<=2||enemy<=3) {
                    std::vector<std::pair<Move,int>> ranked;ranked.reserve(moves.size());
                    for(auto move:moves){checkpoint();ranked.emplace_back(move,cooperation(root.board,move,own,enemy));}
                    std::stable_sort(ranked.begin(),ranked.end(),[](auto& a,auto& b){return a.second>b.second;});
                    for(unsigned i=0;i<moves.size();++i)moves[i]=ranked[i].first;
                    completed.move=moves.front();completed.pv={completed.move};
                }
            }catch(Interrupted&){stopped=true;}
        }
        const auto count=std::min<unsigned>(std::clamp(threads,1u,12u),moves.size());
        std::vector<Ordering> orderings(count);Metrics aggregate;std::mutex profile_lock;
        // These outlive all iterative-deepening workers; each lane has exclusive access.
        std::vector<FeatureCache> feature_caches(count);
        SearchTiming timing;
        timing.setup_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count();
        double previous_ms=0;
        for(unsigned depth=1;depth<=max_depth;++depth) {
            auto now=std::chrono::steady_clock::now();
            double available=std::chrono::duration<double,std::milli>(deadline-now).count();
            if(stopped||available<=0||(options.adaptive&&max_depth==64&&depth>2&&previous_ms*1.5>available))break;
            for(auto& ordering:orderings)ordering.decay();
            std::vector<SearchResult> roots(moves.size());std::atomic<unsigned> next{0};std::atomic<bool> interrupted{false};
            std::atomic<int> shared_alpha{-100001};std::vector<unsigned char> exact_roots(moves.size());
            std::exception_ptr failure;std::mutex failure_lock;
            auto worker=[&](unsigned lane) {
              try {
                State state=root;state.bind_cache(feature_caches[lane]);
                if(state.model->feature_schema==8)for(auto& bank:state.active)bank.reserve(134);
                auto& ordering=orderings[lane];auto before=ordering.visited;
                Metrics profile;GenerationScope scope(*this,options.profile?&profile:nullptr);int root_alpha=-100001;
                try {
                    for(;;) {
                        unsigned i=next.fetch_add(1,std::memory_order_relaxed);if(i>=moves.size())break;
                        checkpoint();Applied applied(state,moves[i]);auto& child=ordering.pv_buffers[1];child.clear();int score;
                        int shared=shared_alpha.load(std::memory_order_relaxed);bool exact=true;
                        if(options.root_pvs&&shared>-100001) {
                            score=-visit(state,int(depth)-1,-shared-1,-shared,1,child,ordering,false);
                            if(score>shared){child.clear();score=-visit(state,int(depth)-1,-100001,-shared,1,child,ordering);}
                            else exact=false;
                        }else if(count==1&&i>0) {
                            score=-visit(state,int(depth)-1,-root_alpha-1,-root_alpha,1,child,ordering,false);
                            if(score>root_alpha){child.clear();score=-visit(state,int(depth)-1,-100001,-root_alpha,1,child,ordering);}
                            else if(options.root_pvs)exact=false;
                        }else {
                            int lower=depth==1?-100001:std::max(-100001,completed.score-75);
                            int upper=depth==1?100001:std::min(100001,completed.score+75);
                            score=-visit(state,int(depth)-1,-upper,-lower,1,child,ordering);
                            if(score<=lower||score>=upper){child.clear();score=-visit(state,int(depth)-1,-100001,100001,1,child,ordering);}
                        }
                        root_alpha=std::max(root_alpha,score);roots[i]={moves[i],score,depth,0,{moves[i]}, {}, {}};
                        roots[i].pv.insert(roots[i].pv.end(),child.begin(),child.end());
                        exact_roots[i]=exact;
                        if(exact) {
                            int best=shared_alpha.load(std::memory_order_relaxed);
                            while(score>best&&!shared_alpha.compare_exchange_weak(best,score,std::memory_order_relaxed)){}
                        }
                    }
                }catch(Interrupted&){interrupted=true;if(options.deadline_guard)stopped=true;}
                nodes.fetch_add(ordering.visited-before,std::memory_order_relaxed);
                std::lock_guard guard(profile_lock);aggregate.features_ns+=profile.features_ns;aggregate.generation_ns+=profile.generation_ns;
                aggregate.ordering_ns+=profile.ordering_ns;aggregate.tt_ns+=profile.tt_ns;aggregate.inference_ns+=profile.inference_ns;
                aggregate.mobility_full+=profile.mobility_full;aggregate.mobility_incremental+=profile.mobility_incremental;aggregate.fast_piece_rebuilds+=profile.fast_piece_rebuilds;
              } catch(...) {std::lock_guard guard(failure_lock);failure=std::current_exception();stopped=true;}
            };
            std::vector<std::jthread> workers;
            for(unsigned lane=1;lane<count;++lane)workers.emplace_back(worker,lane);
            worker(0);auto join_started=std::chrono::steady_clock::now();
            for(auto& thread:workers)thread.join();
            timing.join_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-join_started).count();
            if(failure)std::rethrow_exception(failure);
            if(interrupted)break;
            if(options.root_pvs) {
                // Fail-low root scores are upper bounds, never selectable PVs.
                std::optional<unsigned> best;
                for(unsigned i=0;i<roots.size();++i)if(exact_roots[i]&&(!best||roots[i].score>roots[*best].score))best=i;
                if(!best)throw std::runtime_error("completed root iteration has no exact result");
                completed=roots[*best];
            }else completed=*std::max_element(roots.begin(),roots.end(),[](auto& a,auto& b){return a.score<b.score;});
            std::stable_sort(roots.begin(),roots.end(),[](const auto& a,const auto& b){return a.score>b.score;});
            for(unsigned i=0;i<moves.size();++i)moves[i]=roots[i].move;
            previous_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-now).count();
            if(std::abs(completed.score)>90000)break;
        }
        // Include destruction of the large per-search scratch pools in the measurement.
        feature_caches.clear();orderings.clear();
        auto finished=std::chrono::steady_clock::now();
        timing.total_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(finished-started).count();
        timing.stop_lag_ns=finished>deadline?std::chrono::duration_cast<std::chrono::nanoseconds>(finished-deadline).count():0;
        completed.nodes=nodes;completed.profile=aggregate;completed.timing=timing;return completed;
    }
};
}
