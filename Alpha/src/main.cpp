#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace alpha {
struct Hex {
    int q = 0, r = 0;
    auto operator<=>(const Hex&) const = default;
    Hex operator+(Hex x) const { return {q+x.q, r+x.r}; }
};
// The direction order matches the six UHP relative-position spellings.
constexpr std::array<Hex,6> directions{{{-1,-1},{0,-1},{1,0},{1,1},{0,1},{-1,0}}};
Hex neighbor(Hex h, int d) { return h + directions[d]; }
int direction(Hex from, Hex to) {
    for (int d=0;d<6;++d) if (neighbor(from,d)==to) return d;
    return -1;
}
char up(char c) { return static_cast<char>(std::toupper(static_cast<unsigned char>(c))); }
struct Piece {
    int color = 0; // White 0, Black 1
    char kind = 'Q';
    int number = 0;
    auto operator<=>(const Piece&) const = default;
};
struct Move {
    bool pass = false, placement = false, ability = false;
    Piece piece{};
    Hex from{}, to{}, actor{};
    auto operator<=>(const Move&) const = default;
};
constexpr std::array<char,8> kinds{{'Q','G','S','A','B','M','L','P'}};
constexpr std::array<int,8> limits{{1,3,2,3,2,1,1,1}};
int kind_index(char k) {
    for(int i=0;i<8;++i) if(kinds[i]==k) return i;
    return -1;
}
bool numbered(char k) { return k=='G'||k=='S'||k=='A'||k=='B'; }
std::string piece_name(Piece p) {
    std::string s;
    s += p.color ? 'b':'w'; s += p.kind;
    if(numbered(p.kind)) s += static_cast<char>('0'+p.number);
    return s;
}
std::optional<Piece> parse_piece(std::string s) {
    if(s.size()<2 || s.size()>3 || (s[0]!='w'&&s[0]!='b')) return std::nullopt;
    char k=up(s[1]); int ix=kind_index(k);
    if(ix<0) return std::nullopt;
    int number=0;
    if(numbered(k)) {
        if(s.size()!=3 || s[2]<'1'||s[2]>'0'+limits[ix]) return std::nullopt;
        number=s[2]-'0';
    } else if(s.size()!=2) return std::nullopt;
    return Piece{s[0]=='b',k,number};
}
class Board {
public:
    std::map<Hex,std::vector<Piece>> cells;
    std::vector<Move> history;
    std::set<char> expansions;
    std::string type="Base";

    explicit Board(std::string game_type="Base") {
        if(game_type.substr(0,4)!="Base") throw std::runtime_error("invalid game type");
        if(game_type.size()>4) {
            if(game_type[4]!='+' || game_type.size()>8) throw std::runtime_error("invalid game type");
            for(size_t i=5;i<game_type.size();++i) {
                if(std::string("MLP").find(game_type[i])==std::string::npos || !expansions.insert(game_type[i]).second)
                    throw std::runtime_error("invalid game type");
            }
        }
        for(char k:std::string("MLP")) if(expansions.count(k)) type += (type=="Base"?"+":"")+std::string(1,k);
    }
    int side() const { return static_cast<int>(history.size()%2); }
    int turn_for(int color) const { return static_cast<int>(history.size()/2)+1-(side()!=color); }
    bool occupied(Hex h) const { auto i=cells.find(h); return i!=cells.end()&&!i->second.empty(); }
    int height(Hex h) const { auto i=cells.find(h); return i==cells.end()?0:static_cast<int>(i->second.size()); }
    const Piece& top(Hex h) const { return cells.at(h).back(); }
    std::optional<Hex> locate(Piece p) const {
        for(auto& [h,stack]:cells) for(auto x:stack) if(x==p) return h;
        return std::nullopt;
    }
    bool placed(Piece p) const { return locate(p).has_value(); }
    int count_on_board(int c,char k) const {
        int n=0; for(auto& [h,stack]:cells) for(auto p:stack) if(p.color==c&&p.kind==k) ++n;
        return n;
    }
    bool queen_placed(int c) const { return placed({c,'Q',0}); }
    int neighbors(Hex h) const { int n=0;for(int d=0;d<6;++d)n+=occupied(neighbor(h,d));return n; }
    bool touches(Hex h,int c) const {
        for(int d=0;d<6;++d) {Hex a=neighbor(h,d);if(occupied(a)&&top(a).color==c)return true;}
        return false;
    }
    bool linked() const {
        if(cells.size()<2)return true;
        std::set<Hex> visited, frontier;
        frontier.insert(cells.begin()->first);
        while(!frontier.empty()) {
            Hex h=*frontier.begin();frontier.erase(frontier.begin());
            if(!visited.insert(h).second)continue;
            for(int d=0;d<6;++d) { Hex a=neighbor(h,d);if(occupied(a)&&!visited.count(a))frontier.insert(a); }
        }
        return visited.size()==cells.size();
    }
    bool free_gate(Hex from,Hex to,int from_height=1,int to_height=0) const {
        int d=direction(from,to); if(d<0)return false;
        // On a stacked climb, gates block only when both flanks reach the path height.
        int level=std::max(from_height,to_height+1);
        return !(height(neighbor(from,(d+5)%6))>=level && height(neighbor(from,(d+1)%6))>=level);
    }
    bool queen_surrounded(int c) const { auto q=locate({c,'Q',0}); return q&&neighbors(*q)==6; }
    std::string state() const {
        if(history.empty())return "NotStarted";
        bool w=queen_surrounded(0),b=queen_surrounded(1);
        if(w&&b)return "Draw";
        if(w)return "BlackWins";
        if(b)return "WhiteWins";
        return "InProgress";
    }
    void apply(const Move& m) {
        if(!m.pass) {
            if(!m.placement) {
                auto& st=cells.at(m.from); st.pop_back();if(st.empty())cells.erase(m.from);
            }
            cells[m.to].push_back(m.piece);
        }
        history.push_back(m);
    }
    void undo() {
        if(history.empty())throw std::runtime_error("too many undos");
        Move m=history.back();history.pop_back();
        if(!m.pass) {
            auto& st=cells.at(m.to);st.pop_back();if(st.empty())cells.erase(m.to);
            if(!m.placement)cells[m.from].push_back(m.piece);
        }
    }
    std::string move_string(const Move& m) const {
        if(m.pass)return "pass";
        std::string s=piece_name(m.piece);
        if(history.empty())return s;
        s+=' ';
        if(occupied(m.to))return s+piece_name(top(m.to));
        for(int d=0;d<6;++d) {
            Hex a=neighbor(m.to,d);
            if(!occupied(a))continue;
            if(d==3)s+='\\';else if(d==2)s+='-';else if(d==1)s+='/';
            s+=piece_name(top(a));
            if(d==4)s+='/';else if(d==5)s+='-';else if(d==0)s+='\\';
            return s;
        }
        return s+"??";
    }
    std::optional<Hex> parse_destination(std::string ref) const {
        if(ref.empty())return std::nullopt;
        char prefix=0,suffix=0;
        if(ref[0]=='-'||ref[0]=='/'||ref[0]=='\\') {prefix=ref[0];ref.erase(0,1);}
        if(!ref.empty()&&(ref.back()=='-'||ref.back()=='/'||ref.back()=='\\')) {suffix=ref.back();ref.pop_back();}
        auto p=parse_piece(ref);if(!p)return std::nullopt;
        auto h=locate(*p);if(!h)return std::nullopt;
        if(!prefix&&!suffix)return *h;
        int d=-1;
        if(prefix=='\\')d=0;else if(prefix=='-')d=5;else if(prefix=='/')d=4;
        else if(suffix=='/')d=1;else if(suffix=='-')d=2;else if(suffix=='\\')d=3;
        return neighbor(*h,d);
    }
    std::optional<Move> parse_move(const std::string& text) const {
        if(text=="pass")return Move{.pass=true};
        std::istringstream in(text);std::string name,ref,extra;in>>name;
        auto p=parse_piece(name);if(!p)return std::nullopt;
        if(!(in>>ref)) {
            if(history.empty()&&p->color==side())return Move{.placement=true,.piece=*p,.to={0,0}};
            return std::nullopt;
        }
        if(in>>extra)return std::nullopt;
        auto to=parse_destination(ref);if(!to)return std::nullopt;
        auto from=locate(*p);
        return Move{.placement=!from,.piece=*p,.from=from.value_or(Hex{}),.to=*to};
    }
    bool is_legal(const Move& m) const {
        for(auto x:legal_moves())if(x.pass==m.pass && x.placement==m.placement && x.piece==m.piece && x.from==m.from && x.to==m.to && x.ability==m.ability)return true;
        return false;
    }
    std::vector<Move> legal_moves() const {
        if(state()!="InProgress"&&state()!="NotStarted")return {};
        int c=side();std::set<Hex> placements;
        if(cells.empty())placements.insert({0,0});
        else {
            for(auto& [h,stack]:cells)for(int d=0;d<6;++d) {
                Hex x=neighbor(h,d);if(occupied(x))continue;
                if(history.size()<2 || !touches(x,1-c))placements.insert(x);
            }
        }
        std::set<Move> out;
        bool force_queen=turn_for(c)>=4&&!queen_placed(c);
        for(char k:kinds) {
            int ix=kind_index(k);
            if(history.size()<2&&k=='Q')continue;
            if(force_queen&&k!='Q')continue;
            if(ix>=5&&!expansions.count(k))continue;
            int used=count_on_board(c,k),max=limits[ix];
            if(used>=max)continue;
            Piece p{c,k,numbered(k)?used+1:0};
            for(Hex h:placements)out.insert(Move{.placement=true,.piece=p,.to=h});
        }
        if(queen_placed(c)) {
            for(auto& [h,stack]:cells) {
                Piece p=stack.back();if(p.color!=c)continue;
                if(!history.empty()&&!history.back().placement&&!history.back().pass&&history.back().to==h)continue;
                int old_height=height(h);
                if(p.kind=='P' || (p.kind=='M'&&old_height==1&&mimics_pillbug(h)))
                    pillbug_destinations(p,h,out);
                Board lifted=*this;lifted.cells[h].pop_back();if(lifted.cells[h].empty())lifted.cells.erase(h);
                if(!lifted.linked())continue;
                std::set<Hex> destinations;
                lifted.piece_destinations(p,h,old_height,destinations);
                for(Hex to:destinations)out.insert(Move{.piece=p,.from=h,.to=to});
            }
        }
        if(out.empty())out.insert(Move{.pass=true});
        return {out.begin(),out.end()};
    }
private:
    bool mimics_pillbug(Hex h) const {
        for(int d=0;d<6;++d) {Hex x=neighbor(h,d);if(occupied(x)&&top(x).kind=='P')return true;}
        return false;
    }
    bool slide(Hex from,Hex to,int start_height=1) const {
        int d=direction(from,to);
        if(d<0||occupied(to))return false;
        bool left=occupied(neighbor(from,(d+5)%6));
        bool right=occupied(neighbor(from,(d+1)%6));
        (void)start_height;
        return left!=right;
    }
    void crawl(Hex start,int steps,std::set<Hex>& result) const {
        std::set<Hex> path{start};
        std::function<void(Hex,int)> visit=[&](Hex h,int left) {
            if(!left){if(h!=start)result.insert(h);return;}
            for(int d=0;d<6;++d) {Hex to=neighbor(h,d);if(path.count(to)||!slide(h,to))continue;
                path.insert(to);visit(to,left-1);path.erase(to);
            }
        };visit(start,steps);
    }
    void ant(Hex start,std::set<Hex>& result) const {
        std::set<Hex> seen{start},todo{start};
        while(!todo.empty()) {Hex h=*todo.begin();todo.erase(todo.begin());
            for(int d=0;d<6;++d) {Hex to=neighbor(h,d);if(seen.count(to)||!slide(h,to))continue;
                seen.insert(to);todo.insert(to);result.insert(to);
            }
        }
    }
    void grasshopper(Hex h,std::set<Hex>& result) const {
        for(int d=0;d<6;++d) {Hex x=neighbor(h,d);if(!occupied(x))continue;
            while(occupied(x))x=neighbor(x,d);
            result.insert(x);
        }
    }
    void beetle(Hex h,int old_height,std::set<Hex>& result) const {
        for(int d=0;d<6;++d) {Hex to=neighbor(h,d);
            if(old_height==1&&!occupied(to)) {
                if(slide(h,to))result.insert(to);
            } else if(free_gate(h,to,old_height,height(to)))result.insert(to);
        }
    }
    void ladybug(Hex start,std::set<Hex>& result) const {
        for(int a=0;a<6;++a) {Hex x=neighbor(start,a);if(!occupied(x)||!free_gate(start,x,1,height(x)))continue;
            for(int b=0;b<6;++b) {Hex y=neighbor(x,b);if(y==start||!occupied(y)||!free_gate(x,y,height(x)+1,height(y)))continue;
                for(int c=0;c<6;++c) {Hex z=neighbor(y,c);if(z==start||occupied(z)||!free_gate(y,z,height(y)+1,0))continue;
                    if(neighbors(z)>0)result.insert(z);
                }
            }
        }
    }
    void piece_destinations(Piece p,Hex h,int old_height,std::set<Hex>& result) const {
        if(old_height>1){beetle(h,old_height,result);return;}
        auto single=[&](){for(int d=0;d<6;++d){Hex to=neighbor(h,d);if(slide(h,to,old_height))result.insert(to);}};
        switch(p.kind) {
            case 'Q':case 'P': single();break;
            case 'S':crawl(h,3,result);break;
            case 'A':ant(h,result);break;
            case 'G':grasshopper(h,result);break;
            case 'B':beetle(h,old_height,result);break;
            case 'L':ladybug(h,result);break;
            case 'M': {
                if(old_height>1){beetle(h,old_height,result);break;}
                std::set<char> copied;
                for(int d=0;d<6;++d){Hex x=neighbor(h,d);if(occupied(x)&&top(x).kind!='M')copied.insert(top(x).kind);}
                for(char k:copied){Piece q=p;q.kind=k;piece_destinations(q,h,old_height,result);}
                break;
            }
        }
    }
    void pillbug_destinations(Piece actor,Hex h,std::set<Move>& out) const {
        if(height(h)!=1)return;
        for(int d=0;d<6;++d) {Hex from=neighbor(h,d);if(!occupied(from)||height(from)!=1)continue;
            Piece victim=top(from);
            // A piece moved on the previous ply cannot be picked up.
            if(!history.empty()&&history.back().piece==victim)continue;
            Board lifted=*this;lifted.cells.erase(from);if(!lifted.linked())continue;
            if(!free_gate(from,h,1,1))continue;
            for(int e=0;e<6;++e) {Hex to=neighbor(h,e);if(to==from||occupied(to))continue;
                if(!free_gate(h,to,2,0))continue;
                out.insert(Move{.ability=true,.piece=victim,.from=from,.to=to,.actor=h});
            }
        }
        (void)actor;
    }
};

#include "search.hpp"
#include "perft.hpp"
std::string trim(std::string s) {
    auto a=s.find_first_not_of(" \t\r\n");if(a==std::string::npos)return "";
    auto b=s.find_last_not_of(" \t\r\n");return s.substr(a,b-a+1);
}
void apply_text(Board& board,const std::string& text) {
    auto move=board.parse_move(trim(text));if(!move)throw std::runtime_error("invalid move");
    for(auto legal:board.legal_moves()) {
        if(legal.pass==move->pass&&legal.placement==move->placement&&legal.piece==move->piece&&legal.from==move->from&&legal.to==move->to&&legal.ability==move->ability) {
            board.apply(legal);return;
        }
    }
    throw std::runtime_error("invalid move");
}
Board board_from_string(const std::string& text) {
    std::istringstream in(text);std::string type,state,turn,move;
    std::getline(in,type,';');
    Board board(type.empty()?"Base":type);
    if(std::getline(in,state,';')) {
        if(!std::getline(in,turn,';'))throw std::runtime_error("invalid game string");
        while(std::getline(in,move,';'))apply_text(board,move);
        if(!state.empty()&&state!=board.state())throw std::runtime_error("game-state mismatch");
    }
    return board;
}
class Server {
    std::optional<Board> board;
    int aggression=50,threads=1,table=64;
    bool verbose=false,random_opening=false,ponder=false;
    std::optional<SearchResult> last_search;
    std::jthread ponder_thread;
    std::mutex ponder_mutex;
    std::optional<SearchResult> ponder_result;
    std::string ponder_position;
    std::string option_line(std::string name) const {
        if(name=="Aggression")return "Aggression;int;"+std::to_string(aggression)+";50;0;100";
        if(name=="BackgroundPondering")return std::string("BackgroundPondering;bool;")+(ponder?"True":"False")+";False";
        if(name=="NumThreads")return "NumThreads;int;"+std::to_string(threads)+";1;1;12";
        if(name=="RandomOpening")return std::string("RandomOpening;bool;")+(random_opening?"True":"False")+";False";
        if(name=="TableSizeMiB")return "TableSizeMiB;int;"+std::to_string(table)+";64;1;4096";
        if(name=="Verbose")return std::string("Verbose;bool;")+(verbose?"True":"False")+";False";
        throw std::runtime_error("invalid option");
    }
    std::string game_string() const {
        if(!board)throw std::runtime_error("game not started");
        Board replay(board->type);std::string log;
        for(auto m:board->history) {if(!log.empty())log+=';';log+=replay.move_string(m);replay.apply(m);}
        std::string s=board->type+";"+board->state()+";"+(board->side()?"Black":"White")+"["+std::to_string(board->history.size()/2+1)+"]";
        if(!log.empty())s+=';'+log;
        return s;
    }
    void play(std::string text) {
        apply_text(*board,text);
    }
    void stop_ponder() {
        if(ponder_thread.joinable()) {
            ponder_thread.request_stop();
            ponder_thread.join();
        }
    }
    void start_ponder() {
        if(!ponder||!board||board->state()=="WhiteWins"||board->state()=="BlackWins"||board->state()=="Draw")return;
        stop_ponder();
        const Board position=*board;
        const std::string key=game_string();
        const int configured_threads=threads,configured_table=table,configured_aggression=aggression;
        ponder_thread=std::jthread([this,position,key,configured_threads,configured_table,configured_aggression](std::stop_token token) mutable {
            try {
                Search search(static_cast<std::size_t>(configured_table),configured_aggression,false);
                auto result=search.best(position,64,30.0,configured_threads,token);
                if(result.depth>0) {
                    std::scoped_lock lock(ponder_mutex);
                    ponder_position=key;
                    ponder_result=std::move(result);
                }
            } catch(...) {}
        });
    }
public:
    ~Server(){stop_ponder();}
    void info() const {std::cout<<"id alpha_nokamute 0.1\nMosquito;Ladybug;Pillbug\n";}
    bool run(std::string line) {
        stop_ponder();
        line=trim(line);auto space=line.find(' ');
        std::string cmd=line.substr(0,space),arg=space==std::string::npos?"":trim(line.substr(space+1));
        try {
            if(cmd=="exit"||cmd=="quit")return false;
            if(cmd=="info")info();
            else if(cmd=="newgame") {
                board=board_from_string(arg.empty()?"Base":arg);
                last_search.reset();
                std::cout<<game_string()<<'\n';
            } else if(cmd=="play") {
                if(!board)throw std::runtime_error("game not started");
                play(arg);last_search.reset();std::cout<<game_string()<<'\n';start_ponder();
            } else if(cmd=="validmoves") {
                if(!board)throw std::runtime_error("game not started");
                bool first=true;for(auto m:board->legal_moves()) {if(!first)std::cout<<';';first=false;std::cout<<board->move_string(m);}std::cout<<'\n';
            } else if(cmd=="undo") {
                if(!board)throw std::runtime_error("game not started");
                int count=arg.empty()?1:std::stoi(arg);
                if(count<0||count>static_cast<int>(board->history.size()))throw std::runtime_error("too many undos");
                while(count--)board->undo();
                last_search.reset();
                std::cout<<game_string()<<'\n';
            } else if(cmd=="bestmove") {
                if(!board)throw std::runtime_error("game not started");
                int depth=4;double seconds=5;
                auto exact_limit=[&](const std::string& value,auto& destination) {
                    std::istringstream in(value);std::string extra;
                    if(!(in>>destination)||in>>extra)throw std::runtime_error("invalid bestmove limit");
                };
                if(arg.starts_with("depth ")) {exact_limit(arg.substr(6),depth);seconds=30;}
                else if(arg.starts_with("seconds ")) {
                    depth=64;exact_limit(arg.substr(8),seconds);
                }
                else if(arg.starts_with("time ")) {
                    depth=64;
                    std::string t=arg.substr(5);int h=0,m=0;double s=0;char a=0,b=0;
                    std::istringstream in(t);
                    if(!(in>>h>>a>>m>>b>>s)||a!=':'||b!=':'||h<0||m<0||m>59||s<0||s>=60)
                        throw std::runtime_error("invalid bestmove limit");
                    in>>std::ws;if(!in.eof())throw std::runtime_error("invalid bestmove limit");
                    seconds=h*3600+m*60+s;
                }
                else if(arg.starts_with("depthorseconds ")) {
                    std::istringstream in(arg.substr(15));std::string extra;
                    if(!(in>>depth>>seconds)||in>>extra)throw std::runtime_error("invalid bestmove limit");
                }
                else throw std::runtime_error("invalid bestmove limit");
                if(depth<1||seconds<=0)throw std::runtime_error("invalid bestmove limit");
                {
                    std::scoped_lock lock(ponder_mutex);
                    if(ponder_result&&ponder_position==game_string())last_search=ponder_result;
                }
                if(random_opening&&board->history.size()<2) {
                    auto moves=board->legal_moves();
                    std::mt19937 generator(std::random_device{}());
                    SearchResult opening{};opening.move=moves[generator()%moves.size()];last_search=opening;
                } else {
                    Search search(static_cast<std::size_t>(table),aggression,verbose);
                    auto fresh=search.best(*board,std::min(depth,64),std::min(seconds,30.0),threads);
                    if(!last_search||fresh.depth>=last_search->depth)last_search=std::move(fresh);
                }
                std::cout<<board->move_string(last_search->move)<<'\n';
            } else if(cmd=="perft") {
                if(!board)throw std::runtime_error("game not started");
                unsigned depth=0;std::string extra;std::istringstream in(arg);
                if(!(in>>depth)||in>>extra)throw std::runtime_error("invalid perft depth");
                std::cout<<perft(*board,depth)<<'\n';
            } else if(cmd=="alpha-searchinfo") {
                if(!board||!last_search)throw std::runtime_error("no completed search");
                std::cout<<"depth="<<last_search->depth<<" score="<<last_search->score
                         <<" nodes="<<last_search->nodes<<" seconds="<<last_search->seconds
                         <<" pv=";
                Board replay=*board;bool first=true;
                for(const auto& move:last_search->pv) {
                    if(!first)std::cout<<'|';
                    first=false;
                    std::cout<<replay.move_string(move);replay.apply(move);
                }
                std::cout<<'\n';
            } else if(cmd=="options") {
                static const std::array<std::string,6> names{{"Aggression","BackgroundPondering","NumThreads","RandomOpening","TableSizeMiB","Verbose"}};
                if(arg.empty())for(auto& name:names)std::cout<<option_line(name)<<'\n';
                else {
                    std::istringstream in(arg);std::string action,name,value,extra;in>>action>>name;
                    if(action=="get"&&!(in>>extra))std::cout<<option_line(name)<<'\n';
                    else if(action=="set"&&(in>>value)&&!(in>>extra)) {
                        if(name=="Aggression"||name=="NumThreads"||name=="TableSizeMiB") {
                            int x=std::stoi(value);
                            if(name=="Aggression"&&x>=0&&x<=100)aggression=x;
                            else if(name=="NumThreads"&&x>=1&&x<=12)threads=x;
                            else if(name=="TableSizeMiB"&&x>=1&&x<=4096)table=x;
                            else throw std::runtime_error("invalid option");
                        } else {
                            if(value!="True"&&value!="False")throw std::runtime_error("invalid option");
                            bool x=value=="True";
                            if(name=="BackgroundPondering")ponder=x;
                            else if(name=="RandomOpening")random_opening=x;
                            else if(name=="Verbose")verbose=x;
                            else throw std::runtime_error("invalid option");
                        }
                        std::cout<<option_line(name)<<'\n';
                    } else throw std::runtime_error("invalid option");
                }
            } else if(cmd=="pass") {
                if(!board)throw std::runtime_error("game not started");
                play("pass");last_search.reset();std::cout<<game_string()<<'\n';start_ponder();
            }
            else throw std::runtime_error("unrecognized command");
        } catch(const std::exception& e) {std::cout<<"err "<<e.what()<<'\n';}
        std::cout<<"ok\n"<<std::flush;return true;
    }
};

int standalone_perft(int argc,char** argv) {
    if(argc<3)throw std::runtime_error("usage: alpha_nokamute perft DEPTH [GAMESTRING] [--divide]");
    const int parsed=std::stoi(argv[2]);if(parsed<0)throw std::runtime_error("invalid depth");
    const unsigned depth=static_cast<unsigned>(parsed);
    std::string game="Base";bool divide=false;
    for(int i=3;i<argc;++i)if(std::string(argv[i])=="--divide")divide=true;else game=argv[i];
    Board board=board_from_string(game);
    if(divide&&depth>0) {
        std::uint64_t total=0;
        for(const auto& move:board.legal_moves()) {
            const auto notation=board.move_string(move);board.apply(move);
            const auto nodes=perft(board,depth-1);board.undo();total+=nodes;
            std::cout<<notation<<" "<<nodes<<'\n';
        }
        std::cout<<"total "<<total<<'\n';
    } else std::cout<<perft(board,depth)<<'\n';
    return 0;
}
int self_play(int argc,char** argv) {
    const int cap=argc>2?std::stoi(argv[2]):160;
    const double seconds=argc>3?std::stod(argv[3]):0.05;
    Board board(argc>4?argv[4]:"Base");
    for(int ply=0;ply<cap&&board.state()!="WhiteWins"&&board.state()!="BlackWins"&&board.state()!="Draw";++ply) {
        Search search(64,50,false);auto result=search.best(board,64,seconds,1);
        std::cout<<(ply+1)<<". "<<board.move_string(result.move)<<" depth="<<result.depth<<" nodes="<<result.nodes<<'\n';
        board.apply(result.move);
    }
    std::cout<<"result "<<board.state()<<" plies="<<board.history.size()<<'\n';
    return 0;
}
int uhp_debug(int argc,char** argv) {
    Board board=board_from_string(argc>2?argv[2]:"Base");
    const unsigned depth=argc>3?static_cast<unsigned>(std::stoul(argv[3])):2;
    const auto original_cells=board.cells;const auto original_history=board.history;
    const auto moves=board.legal_moves();
    for(const auto& move:moves) {
        board.apply(move);board.undo();
        if(board.cells!=original_cells||board.history!=original_history)throw std::runtime_error("make/unmake mismatch");
        const auto notation=board.move_string(move);
        auto parsed=board.parse_move(notation);
        if(!parsed||!board.is_legal(*parsed))throw std::runtime_error("notation round-trip mismatch: "+notation);
    }
    std::cout<<"state "<<board.state()<<"\nlegal "<<moves.size()<<"\nperft "<<depth<<" "<<perft(board,depth)<<"\nstatus ok\n";
    return 0;
}
} // namespace alpha
int main(int argc,char** argv) {
    try {
        const std::string mode=argc>1?argv[1]:"uhp";
        if(mode=="perft")return alpha::standalone_perft(argc,argv);
        if(mode=="play")return alpha::self_play(argc,argv);
        if(mode=="uhp-debug")return alpha::uhp_debug(argc,argv);
        if(mode!="uhp"&&mode!="cli")throw std::runtime_error("usage: alpha_nokamute [uhp|cli|perft|play|uhp-debug]");
        alpha::Server server;std::string line;
        server.info();std::cout<<"ok\n"<<std::flush;
        while(std::getline(std::cin,line))if(!server.run(line))break;
    } catch(const std::exception& e) {std::cerr<<"error: "<<e.what()<<'\n';return 2;}
}
