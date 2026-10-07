#include "genseki/review/review.hpp"
#include "alpha_process.hpp"

#include <algorithm>
#include <array>
#include <cwctype>
#include <fstream>
#include <iomanip>
#include <set>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <limits>
#include <map>

#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#include <tlhelp32.h>
#endif

namespace genseki::review {
namespace {
using Clock = std::chrono::steady_clock;
struct Interrupted {};
struct Limit { Clock::time_point deadline; std::stop_token stop; };
void check(void* pointer) {
    auto& limit = *static_cast<Limit*>(pointer);
    if (limit.stop.stop_requested() || Clock::now() >= limit.deadline) throw Interrupted{};
}
struct ScopedLimit {
    void (*previous)(void*) = nu_generation_check;
    void* context = nu_generation_context;
    explicit ScopedLimit(Limit& limit) { nu_generation_context = &limit; nu_generation_check = check; }
    ~ScopedLimit() { nu_generation_check = previous; nu_generation_context = context; }
};
const Stack* at(const Board& board, Hex cell) {
    for (const auto& stack : board.stacks()) if (stack.cell == cell) return &stack;
    return nullptr;
}
std::optional<Hex> queen(const Board& board, Color color) {
    for (const auto& stack : board.stacks()) for (const auto& p : stack.pieces)
        if (p.color == color && p.bug == Bug::queen) return stack.cell;
    return {};
}
unsigned neighbours(const Board& board, Hex cell) {
    unsigned n = 0;
    for (const auto d : directions) if (at(board, add(cell,d))) ++n;
    return n;
}
std::string color_name(Color color) { return color == Color::white ? "White" : "Black"; }
std::string piece_name(Piece p) {
    const std::array<std::string_view,5> names{"Queen", "Spider", "Beetle", "Grasshopper", "Ant"};
    return color_name(p.color) + "'s " + std::string(names[static_cast<unsigned>(p.bug)]);
}
bool wins(GameResult result, Color color) {
    return result == (color == Color::white ? GameResult::white_win : GameResult::black_win);
}
bool disconnects(const Board& board, Hex cell) {
    std::set<Hex> occupied;
    for (const auto& s : board.stacks()) if (s.cell != cell || s.pieces.size() > 1) occupied.insert(s.cell);
    if (occupied.size() < 2) return false;
    std::vector<Hex> pending{*occupied.begin()}; occupied.erase(pending[0]);
    while (!pending.empty()) {
        auto current = pending.back(); pending.pop_back();
        for (auto d : directions) {
            auto next = add(current,d);
            if (occupied.erase(next)) pending.push_back(next);
        }
    }
    return !occupied.empty();
}
void fact(Entry& e, std::string kind, std::string english, std::vector<Hex> cells = {}, std::string witness = {}) {
    e.facts.push_back({std::move(kind),std::move(english),std::move(cells),std::move(witness)});
}
std::string escaped(std::string_view text) {
    std::ostringstream out; out << '"';
    for (unsigned char c : text) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
                else out << char(c);
        }
    }
    out << '"'; return out.str();
}
#ifdef _WIN32
HANDLE job_mutex = nullptr;
#endif
}

Entry describe(const Board& before, const Move& move) {
    Entry e; e.ply = static_cast<unsigned>(before.ply()+1); e.move = move;
    const bool replayable=before.history().size()==before.ply();
    if(replayable)e.before_game = before.game_string();
    auto notation = before.uhp_move_string(move);
    if (!notation || !before.is_legal(move)) throw std::invalid_argument("Illegal review move");
    e.notation = *notation;
    auto after = before; (void)after.make_generated_move(move);
    if(replayable)e.after_game = after.game_string();
    if (move.kind == MoveKind::pass) {
        fact(e,"forced_pass",color_name(before.side_to_move()) + " had no legal placement or movement, so passing was required.");
    } else {
        const auto* destination = at(before,move.to);
        const auto* source = move.from ? at(before,*move.from) : nullptr;
        if (destination) {
            fact(e,"cover",piece_name(move.piece) + " climbed onto " + piece_name(destination->pieces.back())
                + ", covering it so it cannot move. Covered stones stay in the hive; they are not captured.", {move.to});
            if (destination->pieces.back().color != move.piece.color)
                fact(e,"stack_control",color_name(move.piece.color) + " now controls the top of this stack. The top stone's colour governs neighbouring placements.",{move.to});
        } else {
            fact(e,move.kind == MoveKind::placement ? "placement" : "movement",
                piece_name(move.piece) + (move.kind == MoveKind::placement ? " was placed into the hive." : " moved to the highlighted space."),{move.to});
        }
        if (source && source->pieces.size() > 1) {
            auto uncovered = source->pieces[source->pieces.size()-2];
            fact(e,"uncover",piece_name(uncovered) + " is no longer covered. Whether it can move still depends on the other Hive rules.",{*move.from});
        }
        if (move.kind == MoveKind::placement && move.piece.bug == Bug::queen) {
            const auto turn = (before.ply()/2)+1;
            fact(e,"queen_placed",piece_name(move.piece) + " is now in play, so this player may move stones on later turns.",{move.to});
            if (turn == 4) fact(e,"queen_deadline","The Queen had to be placed on this fourth turn; it could not be delayed again.",{move.to});
        }
    }
    for (auto color : {Color::white,Color::black}) {
        auto current = queen(after,color); if (!current) continue;
        auto old = queen(before,color);
        auto count = neighbours(after,*current);
        if (!old || *old != *current || neighbours(before,*old) != count) {
            fact(e,"queen_surround",color_name(color) + "'s Queen now has " + std::to_string(count)
                + " of its six neighbouring spaces occupied. Stones of either colour count toward surrounding it.",{*current});
        }
    }
    if (after.result() == GameResult::draw) fact(e,"natural_draw","Both Queens are surrounded on all six sides, so the game is a draw.");
    else if (after.is_terminal()) fact(e,"natural_win",color_name(after.result() == GameResult::white_win ? Color::white : Color::black)
        + " wins because the opposing Queen is surrounded on all six sides.");
    e.explanation = explain(e); return e;
}

std::expected<Report,std::string> prepare(std::string_view replay, std::stop_token stop) {
    if (replay.size() > 262144 || std::count(replay.begin(),replay.end(),';') > 1026)
        return std::unexpected("This replay exceeds the review size limit.");
    Limit limit{Clock::now()+std::chrono::seconds(10),stop}; ScopedLimit bounded(limit);
    try {
    check(&limit);
    auto board = Board::from_game_string(replay);
    if (!board) {
        // Never export an engine's raw input or filesystem context.
        auto error = board.error();
        if (error.starts_with("invalid move ") || error.starts_with("illegal move ")) {
            const auto colon = error.find(':');
            return std::unexpected(error.substr(0,colon) + ": the replay cannot be played legally.");
        }
        return std::unexpected("The Base-Hive replay header or turn does not match its legal move history.");
    }
    Report report; report.replay = board->game_string(); report.game_sha256 = sha256(report.replay);
    report.partial_game = !board->is_terminal();
    Board before;
    for (const auto& move : board->history()) {
        check(&limit);
        report.moves.push_back(describe(before,move));
        (void)before.make_generated_move(move);
    }
    return report;
    } catch(const Interrupted&) {
        return std::unexpected(stop.stop_requested()?"Review cancelled during replay validation.":"Replay validation exceeded its time limit.");
    }
}

void inspect_tactics(Entry& e, const Board& before, Clock::time_point deadline, std::stop_token stop) {
    e.tactical_complete = false;
    Limit limit{deadline,stop}; ScopedLimit bounded(limit);
    try {
        check(&limit);
        const auto actor = before.side_to_move();
        const auto legal = before.legal_moves();
        auto played_position=before;(void)played_position.make_generated_move(e.move);
        for (const auto& move : legal) {
            check(&limit); auto child = before; (void)child.make_generated_move(move);
            if (wins(child.result(),actor)) {
                e.immediate_win = *before.uhp_move_string(move);
                if (!wins(played_position.result(),actor)) fact(e,"missed_win","A different legal move could have surrounded the opposing Queen immediately.",{move.to},*e.immediate_win);
                break;
            }
        }
        auto after = before; (void)after.make_generated_move(e.move);
        if (!after.is_terminal()) {
            for (const auto& reply : after.legal_moves()) {
                check(&limit); auto child = after; (void)child.make_generated_move(reply);
                if (wins(child.result(),other(actor))) {
                    e.winning_reply = *after.uhp_move_string(reply);
                    auto cell = queen(after,actor);
                    fact(e,"winning_reply","After this move, the opponent could surround " + color_name(actor)
                        + "'s Queen on the very next turn.",cell ? std::vector<Hex>{*cell,reply.to} : std::vector<Hex>{reply.to},*e.winning_reply);
                    break;
                }
            }
        }
        if(!after.is_terminal()&&!e.winning_reply&&legal.size()>1) {
            bool only_safe=true;
            for(const auto& alternative:legal) {
                check(&limit);if(alternative==e.move)continue;
                auto child=before;(void)child.make_generated_move(alternative);
                if(child.is_terminal()) {
                    if(!wins(child.result(),other(actor))){only_safe=false;break;}
                    continue;
                }
                bool loses=false;
                for(const auto& reply:child.legal_moves()) {
                    check(&limit);auto final=child;(void)final.make_generated_move(reply);
                    if(wins(final.result(),other(actor))){loses=true;break;}
                }
                if(!loses){only_safe=false;break;}
            }
            if(only_safe)fact(e,"mandatory_defense","This was the only legal move that avoided an immediate Queen-surround win for the opponent.",{e.move.to});
        }
        // Classify restrictions from exact stacks, lifting connectivity, and legal movement.
        if (!after.is_terminal()) for (const auto& stack : after.stacks()) {
            check(&limit);
            for (std::size_t i=0;i+1<stack.pieces.size();++i) {
                if (stack.pieces[i].bug == Bug::queen) fact(e,"covered_queen",piece_name(stack.pieces[i]) + " cannot move while another stone is on top of it.",{stack.cell});
            }
            const auto top = stack.pieces.back();
            if (top.bug != Bug::queen && top != e.move.piece) continue;
            if (!queen(after,top.color)) {
                fact(e,"queen_lock",piece_name(top) + " cannot move until its own Queen has been placed.",{stack.cell});
            } else if (disconnects(after,stack.cell)) {
                fact(e,"hive_connection",piece_name(top) + " cannot leave this space because lifting it would split the hive. The hive must remain connected.",{stack.cell});
            } else if (after.movement_moves(top.color,stack.cell).empty()) {
                if (top.bug == Bug::queen) {
                    unsigned empty = 0, gated = 0;
                    for (unsigned j=0;j<6;++j) if (!at(after,add(stack.cell,directions[j]))) {
                        ++empty;
                        if (at(after,add(stack.cell,directions[(j+5)%6])) && at(after,add(stack.cell,directions[(j+1)%6]))) ++gated;
                    }
                    if (empty && gated == empty) fact(e,"closed_gates",piece_name(top) + " has no sliding exit: every empty neighbouring space has a closed two-stone gate.",{stack.cell});
                    else fact(e,"no_legal_movement",piece_name(top) + " has no legal movement from this position.",{stack.cell});
                } else fact(e,"no_legal_movement",piece_name(top) + " has no legal movement from this position.",{stack.cell});
            }
        }
        check(&limit);
        e.tactical_complete = true;
    } catch (const Interrupted&) {
        // Positive witnesses stay valid; absence of a witness is never a safety claim.
    }
    e.explanation = explain(e);
}

std::string explain(const Entry& e) {
    auto special = std::find_if(e.facts.begin(),e.facts.end(),[](const Fact& f){return f.kind == "natural_win" || f.kind == "natural_draw" || f.kind == "winning_reply" || f.kind == "missed_win" || f.kind == "mandatory_defense";});
    std::string text;
    if (!e.facts.empty()) text = e.facts.front().english;
    if (special != e.facts.end() && special != e.facts.begin()) text += " " + special->english;
    if (e.preferred && e.preferred->move != e.notation)
    {
        text += " Alpha preferred the highlighted alternative. That preference is an estimate, not proof of a longer-term result.";
        if(!e.alternative_facts.empty())text += " In that alternative: " + e.alternative_facts.front().english;
    }
    if (!e.tactical_complete && e.status != "unanalysed")
        text += " The tactical checks are incomplete; no claim of safety is being made.";
    return text;
}

std::expected<void,std::string> validate_evidence(const Entry& entry,const Board& before,Clock::time_point deadline) {
    if(!before.is_legal(entry.move))return std::unexpected("Evidence references an illegal played move.");
    auto expected=describe(before,entry.move);
    if(entry.ply!=expected.ply||entry.notation!=expected.notation||entry.before_game!=expected.before_game||entry.after_game!=expected.after_game)
        return std::unexpected("Evidence replay identity does not match the played move.");
    inspect_tactics(expected,before,deadline);
    auto same=[](const Fact& a,const Fact& b){return a.kind==b.kind&&a.english==b.english&&a.cells==b.cells&&a.witness==b.witness;};
    for(const auto& claim:entry.facts){
        if(!std::ranges::any_of(expected.facts,[&](const Fact& f){return same(f,claim);}))
            return std::unexpected("A definite sentence has no matching rule evidence.");
    }
    if(entry.tactical_complete&&!expected.tactical_complete)return std::unexpected("Tactical completeness could not be verified.");
    if(entry.immediate_win){auto b=before;auto m=b.parse_uhp_move(*entry.immediate_win);
        if(!m||!b.play(*m)||!wins(b.result(),before.side_to_move()))return std::unexpected("Invalid winning witness.");}
    if(entry.winning_reply){auto b=before;(void)b.make_generated_move(entry.move);auto m=b.parse_uhp_move(*entry.winning_reply);
        if(!m||!b.play(*m)||!wins(b.result(),other(before.side_to_move())))return std::unexpected("Invalid opponent winning witness.");}
    if(entry.preferred){
        auto move=before.parse_uhp_move(entry.preferred->move);
        if(!move)return std::unexpected("Invalid suggested move.");
        if(!entry.variation.empty()){auto first=before.parse_uhp_move(entry.variation.front());if(!first||*first!=*move)return std::unexpected("Continuation does not start with the suggested move.");}
        auto alternative=describe(before,*move);
        for(const auto& claim:entry.alternative_facts)if(!std::ranges::any_of(alternative.facts,[&](const Fact& f){return same(f,claim);}))
            return std::unexpected("An alternative sentence has no matching rule evidence.");
    }else if(!entry.alternative_facts.empty())return std::unexpected("Alternative facts lack a suggested move.");
    auto line=before;
    for(const auto& token:entry.variation){auto move=line.parse_uhp_move(token);if(!move||!line.play(*move))return std::unexpected("Illegal continuation evidence.");}
    if(entry.explanation!=explain(entry))return std::unexpected("Explanation contains an unverified sentence.");
    return {};
}

Report analyse(Report report, const Settings& requested, std::stop_token stop, Publish publish, Search search, Guard guard) {
    auto settings=requested;
    settings.search_ms=std::clamp(settings.search_ms,4u,2000u);
    settings.tactical_ms=std::min(settings.tactical_ms,200u);
    settings.game_ms=std::min(settings.game_ms,600000u);
    report.settings = settings;
    const auto deadline=Clock::now()+std::chrono::milliseconds(settings.game_ms);
    AlphaProcess engine;
    if (!guard) guard = [&]{return resources_available(engine.process_id());};
    report.engine_sha256 = file_sha256(settings.engine);
    auto emit = [&]{if(publish)publish(report);};
    auto failure_status=[&]{return Clock::now()>=deadline?"budget_exhausted":stop.stop_requested()?"cancelled":"error";};
    if(stop.stop_requested()||Clock::now()>=deadline){report.status=failure_status();emit();return report;}
    if (!guard()) { report.status="deferred";report.message="Deeper review is waiting for enough memory and an idle training/match slot.";emit();return report; }
    const auto user_stop=stop;
    std::stop_source bounded_stop;
    std::stop_callback relay(user_stop,[&]{bounded_stop.request_stop();});
    std::jthread watchdog([&](std::stop_token done){
        while(!done.stop_requested()&&!bounded_stop.stop_requested()){
            if(Clock::now()>=deadline){bounded_stop.request_stop();return;}
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    });
    stop=bounded_stop.get_token();
    if (!search) {
        auto started=engine.start(settings.engine,stop);
        if (!started) {report.status=Clock::now()>=deadline?"budget_exhausted":user_stop.stop_requested()?"cancelled":"error";report.message=started.error();emit();return report;}
        search=[&](const Board& b,unsigned ms,std::stop_token token){return engine.search(b,ms,token);};
    }
    report.status="analysing";emit();
    for (auto& entry : report.moves) {
        if (stop.stop_requested()) {report.status=Clock::now()>=deadline?"budget_exhausted":"cancelled";break;}
        if (Clock::now()>=deadline) {report.status="budget_exhausted";break;}
        if (!guard()) {report.status="resource_stopped";break;}
        auto parsed=Board::from_game_string(entry.before_game);
        if (!parsed) {report.status="error";report.message="Review replay integrity failed.";break;}
        auto before=*parsed; entry.status="analysing";
        inspect_tactics(entry,before,std::min(deadline,Clock::now()+std::chrono::milliseconds(settings.tactical_ms)),stop);
        auto budget=[&](unsigned amount)->unsigned {
            auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
            return remaining>0 ? static_cast<unsigned>(std::min<long long>(amount,remaining)) : 0;
        };
        auto request=[&](const Board& board,unsigned amount)->std::expected<SearchAnswer,std::string> {
            auto ms=budget(amount);
            if (!ms || stop.stop_requested()) return std::unexpected("Review was interrupted.");
            auto response=search(board,ms,stop);
            if(stop.stop_requested()||Clock::now()>=deadline)return std::unexpected("Review was interrupted.");
            if(response&&response->score==std::numeric_limits<int>::min())return std::unexpected("Unsupported analysis score.");
            if (response && !board.parse_uhp_move(response->move)) return std::unexpected("The analysis engine suggested an illegal move.");
            return response;
        };
        auto preferred=request(before,settings.search_ms/2);
        if (!preferred) {entry.status="incomplete";report.status=failure_status();report.message="Analysis stopped before this move's suggestions were complete.";entry.explanation=explain(entry);emit();break;}
        entry.preferred=*preferred;
        // Normalize legal notation aliases before comparing choices.
        auto preferred_move=*before.parse_uhp_move(preferred->move);
        entry.preferred->move=*before.uhp_move_string(preferred_move);
        entry.alternative_facts=describe(before,preferred_move).facts;
        auto after=before;(void)after.make_generated_move(entry.move);
        if (!after.is_terminal()) {
            auto played=request(after,settings.search_ms/4);
            if (!played) {entry.status="incomplete";report.status=failure_status();report.message="Analysis stopped before the played continuation was complete.";entry.explanation=explain(entry);emit();break;}
            entry.played_score=-played->score;
        }
        auto alternative=before; (void)alternative.make_generated_move(preferred_move);
        entry.variation={entry.preferred->move};
        if (!alternative.is_terminal()) {
            auto continuation=request(alternative,settings.search_ms/4);
            if (!continuation) {entry.status="incomplete";report.status=failure_status();report.message="Analysis stopped before the suggested continuation was complete.";entry.explanation=explain(entry);emit();break;}
            entry.preferred_score=-continuation->score;
            auto response=*alternative.parse_uhp_move(continuation->move);
            entry.variation.push_back(*alternative.uhp_move_string(response));
        }
        entry.status=entry.tactical_complete?"complete":"tactics_incomplete";
        entry.explanation=explain(entry);++report.completed;emit();
    }
    if (report.status=="analysing") report.status="complete";
    emit();return report;
}

std::string json(const Report& r) {
    std::ostringstream out;
    out << "{\"version\":1,\"replay\":"<<escaped(r.replay)<<",\"game_sha256\":"<<escaped(r.game_sha256)
        <<",\"engine_sha256\":"<<escaped(r.engine_sha256)<<",\"status\":"<<escaped(r.status)
        <<",\"message\":"<<escaped(r.message)<<",\"partial_game\":"<<(r.partial_game?"true":"false")
        <<",\"completed\":"<<r.completed<<",\"settings\":{\"threads\":1,\"table_mib\":32,\"pondering\":false,\"random_opening\":false,\"search_ms\":"
        <<r.settings.search_ms<<",\"tactical_ms\":"<<r.settings.tactical_ms<<",\"game_ms\":"<<r.settings.game_ms<<"},\"moves\":[";
    bool first=true;
    for (const auto& e:r.moves) {
        if(!first)out<<',';first=false;
        out<<"{\"ply\":"<<e.ply<<",\"notation\":"<<escaped(e.notation)<<",\"before\":"<<escaped(e.before_game)
           <<",\"after\":"<<escaped(e.after_game)<<",\"status\":"<<escaped(e.status)<<",\"explanation\":"<<escaped(e.explanation)
           <<",\"tactical_complete\":"<<(e.tactical_complete?"true":"false")<<",\"facts\":[";
        bool f=true;
        for(const auto& item:e.facts) {
            if(!f)out<<',';f=false;
            out<<"{\"kind\":"<<escaped(item.kind)<<",\"english\":"<<escaped(item.english)<<",\"witness\":"<<escaped(item.witness)<<",\"cells\":[";
            bool c=true;for(auto cell:item.cells){if(!c)out<<',';c=false;out<<'['<<cell.q<<','<<cell.r<<']';}out<<"]}";
        }
        out<<"],\"alternative_facts\":[";
        bool a=true;for(const auto& item:e.alternative_facts){
            if(!a)out<<',';a=false;
            out<<"{\"kind\":"<<escaped(item.kind)<<",\"english\":"<<escaped(item.english)<<",\"cells\":[";
            bool c=true;for(auto cell:item.cells){if(!c)out<<',';c=false;out<<'['<<cell.q<<','<<cell.r<<']';}out<<"]}";
        }
        out<<"],\"preferred_move\":"<<(e.preferred?escaped(e.preferred->move):"null")
           <<",\"root_score\":"<<(e.preferred?std::to_string(e.preferred->score):"null")
           <<",\"played_score\":"<<(e.played_score?std::to_string(*e.played_score):"null")
           <<",\"preferred_score\":"<<(e.preferred_score?std::to_string(*e.preferred_score):"null")
           <<",\"variation_label\":\"One possible continuation\",\"variation\":[";
        bool v=true;for(const auto& line:e.variation){if(!v)out<<',';v=false;out<<escaped(line);}out<<"]}";
    }
    out<<"]}\n";return out.str();
}

std::string sha256(std::string_view value) {
#ifdef _WIN32
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)return {};
    std::array<unsigned char,32> bytes{};
    bool ok=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0;
    if(ok)ok=BCryptHashData(hash,reinterpret_cast<PUCHAR>(const_cast<char*>(value.data())),static_cast<ULONG>(value.size()),0)>=0;
    if(ok)ok=BCryptFinishHash(hash,bytes.data(),bytes.size(),0)>=0;
    if(hash)BCryptDestroyHash(hash);BCryptCloseAlgorithmProvider(algorithm,0);
    if(!ok)return {};
    std::ostringstream out;for(auto b:bytes)out<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(b);return out.str();
#else
    (void)value;return {};
#endif
}
std::string file_sha256(const std::filesystem::path& path) {
    std::error_code ec;if(std::filesystem::file_size(path,ec)>67108864||ec)return {};
    std::ifstream file(path,std::ios::binary);if(!file)return {};
    return sha256(std::string(std::istreambuf_iterator<char>(file),{}));
}
bool claim_job() {
#ifdef _WIN32
    if(job_mutex)return false;
    job_mutex=CreateMutexW(nullptr,TRUE,L"Local\\GensekiEnglishReview");
    if(!job_mutex)return false;
    if(GetLastError()==ERROR_ALREADY_EXISTS){CloseHandle(job_mutex);job_mutex=nullptr;return false;}
#endif
    return true;
}
void release_job() {
#ifdef _WIN32
    if(job_mutex){ReleaseMutex(job_mutex);CloseHandle(job_mutex);job_mutex=nullptr;}
#endif
}
bool process_slots_available(const std::vector<ProcessUsage>& processes,unsigned self,unsigned owned_engine) {
    unsigned engines=0,guis=0;
    for(const auto& process:processes){
        if(process.id==self||process.id==owned_engine)continue;
        auto exe=process.executable;
        std::transform(exe.begin(),exe.end(),exe.begin(),[](wchar_t c){return static_cast<wchar_t>(towlower(c));});
        if(exe==L"genseki_gui.exe"){++guis;continue;}
        if(exe.starts_with(L"python")||exe==L"genseki_review.exe")return false;
        if(exe==L"genseki.exe"||exe==L"alpha_nokamute_mit.exe"||exe==L"nu.exe"||exe==L"nokamute.exe"||exe==L"mzinga.exe"||exe==L"mzingacpp.exe"||exe==L"genseki_rules.exe"){
            ++engines;
            if(process.cpu_ticks>250000)return false;
        }else if(process.project_process&&exe.ends_with(L".exe")&&process.cpu_ticks>250000){
            // Unknown native heavy jobs are detected by measured CPU, not name alone.
            return false;
        }
    }
    return engines<=1&&guis<=2;
}

bool resources_available(unsigned owned_engine) {
#ifdef _WIN32
    MEMORYSTATUSEX memory{sizeof(memory)};
    if(!GlobalMemoryStatusEx(&memory)||memory.ullAvailPhys<536870912)return false;
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snapshot==INVALID_HANDLE_VALUE)return false;
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
    std::vector<ProcessUsage> processes;
    static thread_local std::map<unsigned,std::uint64_t> previous;
    static thread_local Clock::time_point sampled{};
    std::map<unsigned,std::uint64_t> current;
    const auto now=Clock::now();
    wchar_t module[32768]{};GetModuleFileNameW(nullptr,module,32768);
    auto root=std::filesystem::path(module).parent_path().parent_path().wstring()+L"\\";
    std::transform(root.begin(),root.end(),root.begin(),[](wchar_t c){return static_cast<wchar_t>(towlower(c));});
    if(Process32FirstW(snapshot,&entry))do {
        std::uint64_t delta=0;bool project=false;
        HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,entry.th32ProcessID);
        if(process){
            wchar_t image[32768]{};DWORD size=32768;
            if(QueryFullProcessImageNameW(process,0,image,&size)){
                std::wstring full(image,size);std::transform(full.begin(),full.end(),full.begin(),[](wchar_t c){return static_cast<wchar_t>(towlower(c));});
                project=full.starts_with(root);
            }
            FILETIME created{},exit{},kernel{},user{};
            if(GetProcessTimes(process,&created,&exit,&kernel,&user)){
                auto ticks=[](FILETIME f){return (std::uint64_t(f.dwHighDateTime)<<32)|f.dwLowDateTime;};
                auto total=ticks(kernel)+ticks(user);current[entry.th32ProcessID]=total;
                auto old=previous.find(entry.th32ProcessID);
                if(old!=previous.end()&&total>=old->second){
                    auto span=std::chrono::duration<double>(now-sampled).count();
                    if(span>0)delta=std::uint64_t(double(total-old->second)/span*.1);
                }
            }CloseHandle(process);
        }
        processes.push_back({entry.th32ProcessID,entry.szExeFile,delta,project});
    }while(Process32NextW(snapshot,&entry));
    CloseHandle(snapshot);
    if(sampled==Clock::time_point{}){previous=std::move(current);sampled=now;Sleep(100);return resources_available(owned_engine);}
    previous=std::move(current);sampled=now;
    return process_slots_available(processes,GetCurrentProcessId(),owned_engine);
#else
    (void)owned_engine;return false;
#endif
}
std::expected<void,std::string> save(const Report& report,const std::filesystem::path& path) {
    auto temporary=path;temporary+=L".partial";
    {std::ofstream out(temporary,std::ios::binary|std::ios::trunc);if(!out)return std::unexpected("Could not create the review export.");out<<json(report);out.flush();if(!out)return std::unexpected("Could not write the review export.");}
#ifdef _WIN32
    if(!MoveFileExW(temporary.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return std::unexpected("Could not finish the review export.");
#else
    std::error_code error;std::filesystem::rename(temporary,path,error);if(error)return std::unexpected("Could not finish the review export.");
#endif
    return {};
}
}
