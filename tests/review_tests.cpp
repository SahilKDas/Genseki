#include "genseki/review/review.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <fstream>
#include <random>
#include <limits>
#include <thread>
using namespace genseki;
using namespace genseki::review;
void require(bool ok,const char* text){if(!ok){std::cerr<<text<<'\n';std::exit(1);}}
bool has(const Entry& e,std::string_view kind){return std::ranges::any_of(e.facts,[&](const Fact& f){return f.kind==kind;});}
Board position(std::string_view s){auto b=Board::from_position_string(s);require(bool(b),"fixture valid");return *b;}
Search reference=[](const Board& b,unsigned,std::stop_token)->std::expected<SearchAnswer,std::string>{return SearchAnswer{*b.uhp_move_string(b.legal_moves().front()),17};};
int main(int argc,char** argv){
    auto report=prepare("Base;InProgress;White[2];wS1;bS1 wS1-");require(report&&report->moves.size()==2&&report->partial_game,"replay validated");
    auto alias_a=prepare("Base;InProgress;Black[3];wS1;bS1 wS1-;wQ -wS1;bQ bS1-;wA1 \\wS1");
    auto alias_b=prepare("Base;InProgress;Black[3];wS1;bS1 wS1-;wQ -wS1;bQ bS1-;wA1 wQ/");
    require(alias_a&&alias_b&&alias_a->replay==alias_b->replay&&alias_a->game_sha256==alias_b->game_sha256,"equivalent replay aliases canonicalize identically");
    auto invalid=prepare("Base;InProgress;White[2];wS1;bS1 missing");require(!invalid&&invalid.error().find("move 2")!=std::string::npos,"first illegal ply identified");
    require(!prepare("Base+M;NotStarted;White[1]"),"expansion rejected");
    require(!prepare("Base;WhiteWins;White[2];wS1;bS1 wS1-"),"false result rejected");
    require(report->moves[0].explanation.find("White's Spider")!=std::string::npos,"English piece names");
    Settings settings;settings.engine="missing.exe";
    auto result=analyse(*report,settings,{}, {},reference,[]{return true;});
    require(result.completed==2&&result.status=="complete"&&result.replay==report->replay,"entire replay analysed without mutation");
    require(result.moves[0].played_score== -17,"score perspective normalized");
    require(!result.moves[0].alternative_facts.empty(),"suggestions have rules-backed consequences");
    for(const auto& e:result.moves){auto b=*Board::from_game_string(e.before_game);for(auto line:e.variation){auto m=b.parse_uhp_move(line);require(m&&b.play(*m),"legal variation replay");}}
    auto bad=analyse(*report,settings,{}, {},[](const Board&,unsigned,std::stop_token)->std::expected<SearchAnswer,std::string>{return SearchAnswer{"wQ missing",0};},[]{return true;});
    require(bad.status=="error"&&bad.completed==0,"illegal suggestion rejected");
    auto deferred=analyse(*report,settings,{}, {},reference,[]{return false;});require(deferred.status=="deferred"&&deferred.moves.size()==2,"facts survive deferral");
    unsigned checks=0;auto stopped=analyse(*report,settings,{}, {},reference,[&]{return ++checks<3;});require(stopped.status=="resource_stopped"&&stopped.completed==1,"resource stop preserves progress");
    std::stop_source stop;stop.request_stop();auto cancel=analyse(*report,settings,stop.get_token(),{},reference,[]{return true;});require(cancel.status=="cancelled","cancelled review retained");
    require(!prepare(report->replay,stop.get_token()),"replay validation cancellation");
    auto leaked=analyse(*report,settings,{}, {},[](const Board&,unsigned,std::stop_token)->std::expected<SearchAnswer,std::string>{return std::unexpected("C:/Users/private/Traceback");},[]{return true;});
    require(json(leaked).find("private")==std::string::npos,"callback failures sanitized");
    Settings oversized=settings;oversized.search_ms=4000;oversized.tactical_ms=1000;oversized.game_ms=700000;
    auto clamped=analyse(*report,oversized,{}, {},reference,[]{return true;});
    require(clamped.settings.search_ms==2000&&clamped.settings.tactical_ms==200&&clamped.settings.game_ms==600000,"hard review budgets enforced");
    auto extreme=analyse(*report,settings,{}, {},[](const Board& b,unsigned,std::stop_token)->std::expected<SearchAnswer,std::string>{return SearchAnswer{*b.uhp_move_string(b.legal_moves()[0]),std::numeric_limits<int>::min()};},[]{return true;});
    require(extreme.status=="error","unnegatable score rejected");
    auto brief=settings;brief.game_ms=20;
    auto elapsed=analyse(*report,brief,{}, {},[](const Board&,unsigned,std::stop_token token)->std::expected<SearchAnswer,std::string>{while(!token.stop_requested())std::this_thread::sleep_for(std::chrono::milliseconds(1));return std::unexpected("stopped");},[]{return true;});
    require(elapsed.status=="budget_exhausted","overall deadline cancels an in-flight search");
    settings.game_ms=0;auto bounded=analyse(*report,settings,{}, {},reference,[]{return true;});require(bounded.status=="budget_exhausted","deadline respected");
    auto e=report->moves[0];auto before=*Board::from_game_string(e.before_game);inspect_tactics(e,before,std::chrono::steady_clock::now());require(!e.tactical_complete,"interrupted enumeration unknown");
    e.status="incomplete";require(explain(e).find("no claim of safety")!=std::string::npos,"unknown is not safe");
    require(json(result).find("missing.exe")==std::string::npos,"engine paths excluded");
#ifdef _WIN32
    require(sha256("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 correct");
#endif
    auto beetle=position("G1|w|8|4|4|-1,0=wQ;-1,1=wA1;0,1=wA2;0,0=wB1;1,0=bQ");auto legal=beetle.legal_moves();
    auto climb=std::ranges::find_if(legal,[](const Move& m){return m.from==Hex{0,0}&&m.to==Hex{1,0};});require(climb!=legal.end(),"legal climb");
    auto cover=describe(beetle,*climb);require(has(cover,"cover")&&has(cover,"stack_control"),"cover/control facts");
    inspect_tactics(cover,beetle,std::chrono::steady_clock::now()+std::chrono::seconds(2));require(has(cover,"covered_queen"),"covered Queen restricted");
    (void)beetle.make_generated_move(*climb);beetle=beetle.with_side_to_move(Color::white);auto descend=beetle.movement_moves(Color::white,Hex{1,0});require(!descend.empty(),"descent exists");auto uncovered=describe(beetle,descend[0]);require(has(uncovered,"uncover"),"uncover fact");
    Board deadline;for(int i=0;i<6;++i){auto m=deadline.legal_moves();auto choice=std::ranges::find_if(m,[](const Move& x){return x.piece.bug!=Bug::queen;});require(choice!=m.end(),"opening choice");(void)deadline.make_generated_move(*choice);}
    require(has(describe(deadline,deadline.legal_moves()[0]),"queen_deadline"),"Queen deadline explained");
    auto forced=position("G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ");
    auto passes=forced.legal_moves();require(passes.size()==1&&passes[0].kind==MoveKind::pass,"forced pass fixture");
    require(has(describe(forced,passes[0]),"forced_pass"),"forced pass explained");
    auto bridge=position("G1|w|8|4|4|-1,0=bQ;0,0=wQ;1,0=wA1");
    auto bridge_entry=describe(bridge,bridge.legal_moves()[0]);inspect_tactics(bridge_entry,bridge,std::chrono::steady_clock::now()+std::chrono::seconds(2));
    require(has(bridge_entry,"hive_connection"),"articulation restriction verified");
    auto lock=report->moves[0];inspect_tactics(lock,Board{},std::chrono::steady_clock::now()+std::chrono::seconds(2));require(has(lock,"queen_lock"),"pre-Queen movement lock verified");
    auto draw=position("G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,2=bB1,wB2;2,0=bA1;2,-1=bA2;1,1=bA3;1,2=bB2;2,1=bG1");
    auto drawing=draw.legal_moves();auto draw_move=std::ranges::find_if(drawing,[](const Move& m){return m.from==Hex{0,2}&&m.to==Hex{0,1};});require(draw_move!=drawing.end(),"drawing move legal");
    require(has(describe(draw,*draw_move),"natural_draw"),"simultaneous surround explained");
    auto win=position("G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,2=bB1,wB2;2,-1=bA2;1,1=bA3;1,2=bB2;2,1=bG1");
    auto winning=win.legal_moves();auto won=std::ranges::find_if(winning,[](const Move& m){return m.from==Hex{0,2}&&m.to==Hex{0,1};});require(won!=winning.end(),"winning move legal");
    auto actual_win=describe(win,*won);require(has(actual_win,"natural_win"),"natural win explained");
    inspect_tactics(actual_win,win,std::chrono::steady_clock::now()+std::chrono::seconds(2));require(!has(actual_win,"missed_win"),"played win not called missed");
    auto missed=std::ranges::find_if(winning,[&](const Move& m){auto b=win;(void)b.make_generated_move(m);return !b.is_terminal();});require(missed!=winning.end(),"nonwinning choice exists");
    auto miss=describe(win,*missed);inspect_tactics(miss,win,std::chrono::steady_clock::now()+std::chrono::seconds(2));require(has(miss,"missed_win")&&miss.immediate_win,"missed immediate win proved");
    auto witness=win.parse_uhp_move(*miss.immediate_win);require(witness&&win.play(*witness)&&win.result()==GameResult::white_win,"winning witness replayed");
    auto threatened=position("G1|w|8|4|4|0,0=wQ;1,0=bQ;1,-1=bA1;0,-1=bA2;-1,0=bA3;-1,1=bB1;1,1=bB2");
    auto threat_moves=threatened.legal_moves();auto threat=describe(threatened,threat_moves[0]);inspect_tactics(threat,threatened,std::chrono::steady_clock::now()+std::chrono::seconds(2));require(threat.winning_reply&&has(threat,"winning_reply"),"opponent winning reply proved");
    require(has(threat,"closed_gates"),"Queen closed sliding gates explained");
    auto defense_board=position("G1|w|12|6|6|0,0=wQ;1,0=bQ,wB1;1,-1=bB2;0,-1=bA1;-1,0=bG1;-1,1=bS2;1,1=bB1;0,-2=bS1");
    auto defenses=defense_board.legal_moves();auto defense_move=std::ranges::find_if(defenses,[](const Move& m){return m.from==Hex{1,0}&&m.to==Hex{1,1};});
    require(defense_move!=defenses.end(),"defense fixture legal");
    auto defense=describe(defense_board,*defense_move);inspect_tactics(defense,defense_board,std::chrono::steady_clock::now()+std::chrono::seconds(2));
    require(has(defense,"mandatory_defense")&&defense.tactical_complete,"unique mandatory defense explained after complete enumeration");
    unsigned safe=0;
    for(const auto& candidate:defenses){auto b=defense_board;(void)b.make_generated_move(candidate);bool loses=b.result()==GameResult::black_win;
        if(!b.is_terminal())for(const auto& r:b.legal_moves()){auto next=b;(void)next.make_generated_move(r);if(next.result()==GameResult::black_win){loses=true;break;}}
        if(!loses)++safe;
    }
    require(safe==1,"independent enumeration confirms exactly one defense");
    auto unfinished_defense=describe(defense_board,*defense_move);inspect_tactics(unfinished_defense,defense_board,std::chrono::steady_clock::now());
    require(!has(unfinished_defense,"mandatory_defense"),"incomplete enumeration cannot assert mandatory defense");
    std::vector<std::pair<Entry,Board>> audits{{cover,position("G1|w|8|4|4|-1,0=wQ;-1,1=wA1;0,1=wA2;0,0=wB1;1,0=bQ")},{bridge_entry,bridge},{lock,Board{}},{actual_win,position("G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,2=bB1,wB2;2,-1=bA2;1,1=bA3;1,2=bB2;2,1=bG1")},{threat,threatened},{defense,defense_board},{describe(draw,*draw_move),draw},{describe(forced,passes[0]),forced},{describe(deadline,deadline.legal_moves()[0]),deadline}};
    for(const auto& entry:result.moves)audits.push_back({entry,*Board::from_game_string(entry.before_game)});
    audits.push_back({uncovered,beetle});
    audits.push_back({miss,position("G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,2=bB1,wB2;2,-1=bA2;1,1=bA3;1,2=bB2;2,1=bG1")});
    for(const auto& [entry,b]:audits){
        require(bool(validate_evidence(entry,b,std::chrono::steady_clock::now()+std::chrono::seconds(2))),"every definite sentence matches reconstructed rule evidence");
        for(unsigned i=0;i<entry.facts.size();++i){auto corrupted=entry;corrupted.facts[i].english+=" This guarantees a win.";corrupted.explanation=explain(corrupted);
            require(!validate_evidence(corrupted,b,std::chrono::steady_clock::now()+std::chrono::seconds(2)),"tampered fact sentence rejected");}
        auto invented=entry;invented.explanation+=" The player intended to attack.";
        require(!validate_evidence(invented,b,std::chrono::steady_clock::now()+std::chrono::seconds(2)),"invented explanation rejected");
    }
    auto fake_defense=threat;fake_defense.facts.push_back({"mandatory_defense","This was the only legal move that avoided an immediate Queen-surround win for the opponent.",{fake_defense.move.to},{}});fake_defense.explanation=explain(fake_defense);
    require(!validate_evidence(fake_defense,threatened,std::chrono::steady_clock::now()+std::chrono::seconds(2)),"unsupported mandatory-defense certainty rejected");
    require(process_slots_available({{1,L"Genseki_GUI.exe",0},{2,L"genseki.exe",0},{3,L"genseki_review.exe",0}},3),"own reviewer and idle GUI engine allowed");
    require(!process_slots_available({{1,L"alpha_nokamute_mit.exe",500000}},3),"native Alpha search blocks review");
    require(!process_slots_available({{1,L"renamed-training.exe",5000000}},3),"unknown CPU-heavy executable blocks review");
    require(process_slots_available({{1,L"editor.exe",5000000,false}},3),"unrelated desktop application is not classified as a project job");
    require(!process_slots_available({{1,L"nu.exe",0},{2,L"nokamute.exe",0}},3),"two unrelated native engines block extra review engine");
    require(process_slots_available({{4,L"alpha_nokamute_mit.exe",9000000}},3,4),"owned analysis engine excluded from competing-job guard");
    (void)threatened.make_generated_move(threat_moves[0]);auto reply=threatened.parse_uhp_move(*threat.winning_reply);require(reply&&threatened.play(*reply)&&threatened.result()==GameResult::black_win,"losing reply witness verified");
    std::cout<<"Review tests passed\n";
    if(argc==2){
        std::mt19937 rng(719);
        for(unsigned game=0;game<64;++game){
            Board board;
            for(unsigned ply=0;ply<160&&!board.is_terminal();++ply){
                auto moves=board.legal_moves();auto chosen=moves[rng()%moves.size()];
                for(const auto& move:moves){auto child=board;(void)child.make_generated_move(move);if(child.is_terminal()){chosen=move;break;}}
                (void)board.make_generated_move(chosen);
            }
            if(board.is_terminal()){
                auto full=prepare(board.game_string());require(full&&!full->partial_game,"completed game replay validated");
                auto reviewed=analyse(*full,Settings{}, {},{},reference,[]{return true;});
                require(reviewed.status=="complete"&&reviewed.completed==full->moves.size(),"completed game fully reviewed");
                std::ofstream output(argv[1]);output<<board.game_string();require(output.good(),"completed fixture saved");
                std::cout<<"Completed review fixture: "<<board.ply()<<" plies\n";return 0;
            }
        }
        require(false,"naturally completed fixture found");
    }
}
