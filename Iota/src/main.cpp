#include "search.hpp"
#include <charconv>
#include <iomanip>
#include <iostream>
#include <sstream>

using namespace iota;
int number(const std::string& s,int lo,int hi){int n;auto [p,e]=std::from_chars(s.data(),s.data()+s.size(),n);if(e!=std::errc{}||p!=s.data()+s.size()||n<lo||n>hi)throw std::runtime_error("invalid number");return n;}
int main(int argc,char** argv){try {
    if(argc>1&&std::string(argv[1])=="--selftest"){
        Board b;if(b.perft(0)!=1||b.perft(1)!=4||b.perft(2)!=96||b.perft(3)!=1440)throw std::runtime_error("perft failure");auto original=b.position_string();auto moves=b.legal_moves();for(auto m:moves){auto before=hash(b);auto u=b.make_generated_move(m);b.unmake_move(u);if(b.position_string()!=original||hash(b)!=before)throw std::runtime_error("undo failure");}
        auto e=encode(b,true),g=encode(b,false);if(e.cells.size()!=2025||g.cells.size()!=1)throw std::runtime_error("encoding failure");
        for(int ply=0;ply<80&&!b.is_terminal();++ply){auto legal=b.legal_moves();for(auto m:legal){auto u=b.make_generated_move(m);b.unmake_move(u);}auto cnn=encode(b,true),gnn=encode(b,false);for(auto m:legal)if(m.kind!=MoveKind::pass&&(!cnn.index.contains(m.to)||!gnn.index.contains(m.to)))throw std::runtime_error("destination omitted");(void)b.make_generated_move(legal[(ply*17)%legal.size()]);auto parsed=Board::from_position_string(b.position_string());if(!parsed||parsed->position_string()!=b.position_string())throw std::runtime_error("roundtrip failure");}
        Model m;m.width=32;m.blocks=4;m.weights.assign(features*32+32+4*(7*32*32+32)+3*32+3+(3*32+action_features)+1,0);
        m.weights[features*32+32+4*(7*32*32+32)+3*32]=1;
        Board opening;Search test(m,1);test.table.resize(1);
        auto expected=m.predict(opening,opening.legal_moves()).value*1000;
        auto one=test.run(opening,10000,1,"alphabeta"),two=test.run(opening,10000,2,"alphabeta");
        if(one.depth!=1||two.depth!=2||std::abs(one.value+expected)>.01||std::abs(two.value-expected)>.01)throw std::runtime_error("shallow minimax/collision mismatch");
        auto repeated=test.run(opening,10000,2,"alphabeta");if(repeated.move!=two.move||std::abs(repeated.value-two.value)>.01)throw std::runtime_error("TT repeatability mismatch");
        auto fallback=test.run(opening,0,64,"alphabeta");if(!opening.is_legal(fallback.move)||fallback.depth!=0)throw std::runtime_error("deadline fallback failure");
        for(auto move:two.pv)if(!opening.play(move))throw std::runtime_error("illegal principal variation");
        std::cout<<"native foundations pass\n";return 0;
    }
    Model model;std::string mode="alphabeta";size_t memory=16;int threads=1;std::unique_ptr<Search> search;
    for(int i=1;i<argc;++i)if(std::string(argv[i])=="--model"&&i+1<argc)model.load(argv[++i]);else throw std::runtime_error("usage: iota --model FILE");
    if(!model.weights.empty())search=std::make_unique<Search>(model,memory);
    Board board;bool started=false,diagnostic=false;std::vector<uint64_t> hashes;std::vector<Board> undo_states;SearchResult last;std::string searched_position;
    auto rebuild=[&]{hashes.clear();undo_states.clear();Board b;hashes.push_back(hash(b));for(auto m:board.history()){undo_states.push_back(b);(void)b.make_generated_move(m);hashes.push_back(hash(b));}};
    std::cout<<"id Iota independent experimental v0.1\nok\n"<<std::flush;
    for(std::string line;std::getline(std::cin,line);){try {auto space=line.find(' ');std::string cmd=line.substr(0,space),args=space==std::string::npos?"":line.substr(space+1);
        if(cmd=="exit")break;
        if(cmd=="newgame"||cmd=="play"||cmd=="pass"||cmd=="undo"||cmd=="iota-playindex"||cmd=="iota-loadposition"||(cmd=="options"&&args.starts_with("set ")))searched_position.clear();
        if(cmd=="info")std::cout<<"id Iota independent experimental v0.1\n";
        else if(cmd=="newgame"){auto b=args.empty()||args=="Base"?std::expected<Board,std::string>(Board{}):Board::from_game_string(args);if(!b)throw std::runtime_error(b.error());board=*b;started=true;diagnostic=false;rebuild();std::cout<<board.game_string()<<'\n';}
        else if(cmd=="options"){
            if(args.starts_with("get ")){
                auto name=args.substr(4);
                if(name=="Search")std::cout<<"Search;enum;"<<mode<<";alphabeta;alphabeta;mcts\n";
                else if(name=="Threads")std::cout<<"Threads;int;"<<threads<<";1;1;12\n";
                else if(name=="HashMB")std::cout<<"HashMB;int;"<<memory<<";16;1;128\n";
                else if(name=="Model")std::cout<<"Model;string;"<<(model.weights.empty()?"none":"loaded")<<";none\n";
                else throw std::runtime_error("unsupported option");
                std::cout<<"ok\n"<<std::flush;continue;
            }
            if(args.empty())std::cout<<"Search;enum;"<<mode<<";alphabeta;alphabeta;mcts\nThreads;int;"<<threads<<";1;1;12\nHashMB;int;"<<memory<<";16;1;128\nModel;string;"<<(model.weights.empty()?"none":"loaded")<<";none\n";
            else {std::istringstream in(args);std::string op,name,value;in>>op>>name;std::getline(in,value);if(!value.empty()&&value[0]==' ')value.erase(0,1);if(op!="set")throw std::runtime_error("options set NAME VALUE required");if(name=="Search"&&(value=="alphabeta"||value=="mcts"))mode=value;else if(name=="Threads"){threads=number(value,1,12);model.threads=threads;}else if(name=="HashMB"){memory=number(value,1,128);if(search)search=std::make_unique<Search>(model,memory);}else if(name=="Model"){model.load(value);search=std::make_unique<Search>(model,memory);}else throw std::runtime_error("unsupported option");}
        }
        else {if(!started)throw std::runtime_error("newgame required");
            if(cmd=="iota-encode"&&args!="cnn"&&args!="gnn"&&args!="cnn2"&&args!="gnn2"&&args!="cnn3")throw std::runtime_error("encoding must be cnn, gnn, cnn2, gnn2 or cnn3");
            if(cmd=="validmoves"){bool first=true;for(auto m:board.legal_moves()){if(!first)std::cout<<';';first=false;std::cout<<*board.uhp_move_string(m);}std::cout<<'\n';}
            else if(cmd=="play"||cmd=="pass"){if(diagnostic)throw std::runtime_error("loaded diagnostic position: use iota-playindex");auto m=board.parse_uhp_move(cmd=="pass"?"pass":args);if(!m)throw std::runtime_error(m.error());auto previous=board;if(!board.play(*m))throw std::runtime_error("illegal move");undo_states.push_back(std::move(previous));hashes.push_back(hash(board));std::cout<<board.game_string()<<'\n';}
            else if(cmd=="iota-playindex"){auto moves=board.legal_moves();if(moves.empty())throw std::runtime_error("terminal position");auto index=number(args,0,int(moves.size())-1);undo_states.push_back(board);(void)board.make_generated_move(moves[index]);hashes.push_back(hash(board));std::cout<<board.position_string()<<'\n';}
            else if(cmd=="undo"){size_t count=args.empty()?1:number(args,1,100000);if(count>undo_states.size())throw std::runtime_error("cannot undo");while(count--){board=std::move(undo_states.back());undo_states.pop_back();hashes.pop_back();}std::cout<<(diagnostic?board.position_string():board.game_string())<<'\n';}
            else if(cmd=="bestmove"){
                if(!search)throw std::runtime_error("neural model required");int ms=230,depth=64;std::istringstream in(args);std::string kind,value,extra;in>>kind>>value;if(in>>extra)throw std::runtime_error("extra arguments");if(kind=="depth"){depth=number(value,1,64);ms=1000;}else if(kind=="time"){int h,m;double s;char c,d;std::istringstream t(value);if(!(t>>h>>c>>m>>d>>s)||c!=':'||d!=':'||h<0||m<0||m>=60||s<0||s>=60||!std::isfinite(s)||t.peek()!=EOF)throw std::runtime_error("invalid time");double total=(h*3600.0+m*60+s)*1000;if(total>3600000)throw std::runtime_error("time too large");ms=std::max(0,int(total)-20);}else if(!kind.empty())throw std::runtime_error("invalid bestmove arguments");
                auto result=search->run(board,ms,depth,mode,hashes);last=result;searched_position=board.position_string();std::cout<<*board.uhp_move_string(result.move)<<'\n';std::cerr<<"nodes="<<result.nodes<<" depth="<<result.depth<<" value="<<result.value<<'\n';
            }
            else if(cmd=="iota-searchinfo"||cmd=="iota-stats"){
                if(searched_position!=board.position_string())throw std::runtime_error("no search for current position");
                std::cout<<"nodes "<<last.nodes<<" depth "<<last.depth<<" value "<<last.value<<'\n';
                if(cmd=="iota-stats"){std::cout<<"ok\n"<<std::flush;continue;}
                if(last.nodes<2||last.policy.empty())throw std::runtime_error("no completed MCTS visit target");
                for(auto p:last.policy)std::cout<<p<<'\n';
            }
            else if(cmd=="iota-tactics"){
                if(!search)throw std::runtime_error("model required for bounded tactical diagnostics");
                search->deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(args.empty()?500:number(args,1,2000));Search::Hook hook(*search);
                auto moves=board.legal_moves();auto own=board.side_to_move();
                for(size_t i=0;i<moves.size();++i){auto m=moves[i];auto child=board;auto undo=child.make_generated_move(m);(void)undo;bool win=child.result()==(own==Color::white?GameResult::white_win:GameResult::black_win),unsafe=false;
                    if(!child.is_terminal())for(auto reply:child.legal_moves()){auto u=child.make_generated_move(reply);auto r=child.result();child.unmake_move(u);if(r==(own==Color::white?GameResult::black_win:GameResult::white_win)){unsafe=true;break;}}
                    auto neighbors=[&](const Board& b,Hex h){int count=0;for(auto d:directions)for(auto& s:b.stacks())if(s.cell==add(h,d))++count;return count;};
                    bool escape=m.from&&m.piece.bug==Bug::queen&&neighbors(child,m.to)<neighbors(board,*m.from);bool stack=false;for(auto& s:board.stacks())if((m.from&&s.cell==*m.from&&s.pieces.size()>1)||(s.cell==m.to&&m.kind==MoveKind::movement))stack=true;
                    std::cout<<i<<' '<<win<<' '<<unsafe<<' '<<escape<<' '<<stack<<'\n';
                }
            }
            else if(cmd=="iota-position")std::cout<<board.position_string()<<'\n';
            else if(cmd=="iota-result")std::cout<<name(board.result())<<'\n';
            else if(cmd=="iota-modelinfo")std::cout<<"version "<<model.version<<" architecture "<<(model.cnn?"cnn":"gnn")<<" width "<<model.width<<" blocks "<<model.blocks<<" checksum "<<model.checksum<<'\n';
            else if(cmd=="iota-actions")for(auto m:board.legal_moves())std::cout<<int(m.kind)<<' '<<int(m.piece.color)<<' '<<int(m.piece.bug)<<' '<<int(m.piece.id)<<' '<<(m.from?m.from->q:99999)<<' '<<(m.from?m.from->r:99999)<<' '<<m.to.q<<' '<<m.to.r<<'\n';
            else if(cmd=="iota-repetition"){
                auto identity=board.position_string();auto last=identity.rfind('|');
                std::cout<<int(board.side_to_move())<<':'<<std::min(size_t(8),board.ply())<<':'<<identity.substr(last+1)<<'\n';
            }
            else if(cmd=="iota-loadposition"){auto parsed=Board::from_position_string(args);if(!parsed)throw std::runtime_error(parsed.error());board=*parsed;diagnostic=true;undo_states.clear();hashes={hash(board)};std::cout<<board.position_string()<<'\n';}
            else if(cmd=="iota-divide"){unsigned depth=number(args,1,4);for(auto m:board.legal_moves()){auto notation=board.uhp_move_string(m);auto u=board.make_generated_move(m);auto count=board.perft(depth-1);board.unmake_move(u);std::cout<<*notation<<'\t'<<count<<'\n';}}
            else if(cmd=="iota-index"){auto parsed=board.parse_uhp_move(args);if(!parsed)throw std::runtime_error(parsed.error());auto moves=board.legal_moves();auto it=std::find(moves.begin(),moves.end(),*parsed);if(it==moves.end())throw std::runtime_error("illegal move");std::cout<<(it-moves.begin())<<'\n';}
            else if(cmd=="iota-canonical")std::cout<<canonical(board)<<'\n';
            else if(cmd=="iota-perft")std::cout<<board.perft(number(args,0,4))<<'\n';
            else if(cmd=="iota-encode"){bool modern=args.ends_with('2')||args.ends_with('3'),cnn=args.starts_with("cnn");auto e=encode(board,cnn,modern,args=="cnn3");std::cout<<e.cells.size()<<' '<<features;if(modern)std::cout<<" 2 "<<e.links.size();std::cout<<'\n';for(size_t i=0;i<e.cells.size();++i){std::cout<<e.cells[i].q<<' '<<e.cells[i].r;for(int j=0;j<features;++j)std::cout<<' '<<e.x[i*features+j];if(!modern)for(auto n:e.edges[i])std::cout<<' '<<n;std::cout<<'\n';}if(modern)for(auto link:e.links)std::cout<<"edge "<<link[0]<<' '<<link[1]<<' '<<link[2]<<'\n';for(auto m:board.legal_moves()){auto src=m.from?e.index.find(*m.from):e.index.end(),dst=(modern&&m.kind==MoveKind::pass)?e.index.end():e.index.find(m.to);int si=src==e.index.end()?-1:src->second;if(modern&&!cnn&&m.from)si=e.stones.at(m.piece);std::cout<<"action "<<si<<' '<<(dst==e.index.end()?-1:dst->second);for(auto x:action(board,m,modern))std::cout<<' '<<x;std::cout<<'\n';}}
            else if(cmd=="iota-eval"){auto moves=board.legal_moves();auto p=model.predict(board,moves);std::cout<<std::setprecision(9)<<p.value;for(auto v:p.wdl)std::cout<<' '<<v;std::cout<<'\n';for(auto v:p.policy)std::cout<<v<<'\n';}
            else throw std::runtime_error("unknown command");
        }
        std::cout<<"ok\n"<<std::flush;
    }catch(const Interrupted&){std::cout<<"err tactical diagnostic deadline\nok\n"<<std::flush;}catch(const std::exception& e){std::cout<<"err "<<e.what()<<"\nok\n"<<std::flush;}}
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
