#pragma once

#include "genseki/review/review.hpp"
#include <commctrl.h>
#include <fstream>
#include <future>
#include <memory>
#include <mutex>

namespace genseki::review {

class ReviewWindow {
public:
    ~ReviewWindow(){stop_.request_stop();if(worker_.valid())worker_.wait();if(hwnd_)DestroyWindow(hwnd_);if(font_)DeleteObject(font_);if(background_)DeleteObject(background_);}
    bool active()const{return hwnd_!=nullptr;}
    bool open(HINSTANCE instance,HWND owner,std::string replay,std::filesystem::path engine,bool testing=false,bool hidden=false){
        instance_=instance;owner_=owner;testing_=testing;
        WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=instance;wc.lpszClassName=L"GensekiEnglishReview";wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);
        RegisterClassW(&wc);
        hwnd_=CreateWindowExW(0,wc.lpszClassName,L"Genseki - Game Review",WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,1120,760,owner,nullptr,instance,this);
        if(!hwnd_)return false;
        icons_.load(instance);refresh_font();
        shared_=std::make_shared<Shared>();shared_->report.status="validating";
        auto shared=shared_;auto token=stop_.get_token();
        worker_=std::async(std::launch::async,[shared,token,replay=std::move(replay),engine=std::move(engine),testing]{
            Report result;
            auto publish=[shared](const Report& report){std::lock_guard lock(shared->mutex);shared->report=report;++shared->version;};
            try {
                auto prepared=prepare(replay,token);
                if(!prepared){result.status=token.stop_requested()?"cancelled":"error";result.message=prepared.error();publish(result);return result;}
                result=std::move(*prepared);publish(result);
                if(token.stop_requested()){result.status="cancelled";publish(result);return result;}
                if(!claim_job()){result.status="deferred";result.message="Another game review is active.";publish(result);return result;}
                struct Release{~Release(){release_job();}} release;
                Settings settings;settings.engine=engine;
                if(testing){
                    Search reference=[](const Board& b,unsigned,std::stop_token)->std::expected<SearchAnswer,std::string>{return SearchAnswer{*b.uhp_move_string(b.legal_moves().front()),0};};
                    return analyse(std::move(result),settings,token,publish,reference,[]{return true;});
                }
                return analyse(std::move(result),settings,token,publish);
            }catch(...){
                {std::lock_guard lock(shared->mutex);result=shared->report;}
                result.status="error";result.message="The review stopped unexpectedly.";publish(result);return result;
            }
        });
        if(owner_)EnableWindow(owner_,FALSE);
        if(!testing&&!hidden)ShowWindow(hwnd_,SW_SHOW);
        layout();SetTimer(hwnd_,1,30,nullptr);return true;
    }

    const Report& report()const{return report_;}
    int acceptance(const std::filesystem::path& directory,bool cancel=false){
        auto deadline=GetTickCount64()+120000;bool clicked=false;
        while(worker_.valid()&&GetTickCount64()<deadline){
            MSG message{};while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessageW(&message);}
            poll();
            if(cancel&&!clicked&&report_.completed>=1){SendMessageW(buttons_[7],BM_CLICK,0,0);clicked=true;}
            Sleep(5);
        }
        poll();
        if(worker_.valid())return 11;
        if(cancel){if(!clicked||report_.status!="cancelled"||!report_.completed||report_.completed>=report_.moves.size())return 12;}
        else if(report_.status!="complete"||report_.completed!=report_.moves.size())return 2;
        if(report_.moves.empty())return 9;
        const auto original=report_.replay;
        for(unsigned i=0;i<report_.moves.size();++i){
            select(i);command(303);command(304);command(305);command(306);
            const auto& e=report_.moves[i];auto b=Board::from_game_string(e.before_game);if(!b)return 4;
            if(!validate_evidence(e,*b,std::chrono::steady_clock::now()+std::chrono::seconds(2)))return 13;
        }
        if(report_.replay!=original)return 3;
        std::error_code error;std::filesystem::create_directories(directory,error);if(error)return 6;
        for(unsigned dpi:{96u,120u,144u,192u}){
            RECT scale_rect{0,0,MulDiv(900,dpi,96),MulDiv(640,dpi,96)};
            SendMessageW(hwnd_,WM_DPICHANGED,MAKEWPARAM(dpi,dpi),reinterpret_cast<LPARAM>(&scale_rect));layout();
            select(unsigned(report_.moves.size()-1));details_=true;update_text();
            RECT client{};GetClientRect(hwnd_,&client);
            for(auto h:buttons_){RECT rect{};GetWindowRect(h,&rect);MapWindowPoints(nullptr,hwnd_,reinterpret_cast<POINT*>(&rect),2);
                if(rect.left<0||rect.top<0||rect.right>client.right||rect.bottom>client.bottom)return 14;}
            for(const auto& stack:display_.stacks()){
                auto center=point(stack.cell);auto radius=LONG(size_*dpi_/96.*.85);
                if(center.x-radius<board_rect_.left||center.x+radius>board_rect_.right||center.y-radius<board_rect_.top||center.y+radius>board_rect_.bottom)return 15;
            }
            if(!snapshot(directory/("review-"+std::to_string(dpi)+".bmp")))return 7;
        }
        return save(report_,directory/"review.json")?0:8;
    }
    static int smoke(HINSTANCE instance,const std::filesystem::path& directory,std::string replay="Base;InProgress;White[3];wS1;bS1 wS1-;wQ -wS1;bQ bS1-"){
        ReviewWindow review;
        auto validated=prepare(replay);if(!validated||validated->moves.empty())return 9;
        if(!review.open(instance,nullptr,replay,{},true))return 1;
        return review.acceptance(directory);
    }
private:
    struct Shared {std::mutex mutex;Report report;unsigned version=0;};
    struct Line {std::wstring label;std::string start;std::vector<std::string> moves;bool operator==(const Line&)const=default;};
    static std::wstring wide(std::string_view text){
        if(text.empty())return {};
        int n=MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),nullptr,0);std::wstring result(n,L' ');
        MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),result.data(),n);return result;
    }
    static LRESULT CALLBACK procedure(HWND hwnd,UINT message,WPARAM w,LPARAM l){
        ReviewWindow* app=reinterpret_cast<ReviewWindow*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
        if(message==WM_NCCREATE){app=static_cast<ReviewWindow*>(reinterpret_cast<CREATESTRUCTW*>(l)->lpCreateParams);app->hwnd_=hwnd;SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(app));}
        return app?app->handle(message,w,l):DefWindowProcW(hwnd,message,w,l);
    }
    LRESULT handle(UINT message,WPARAM w,LPARAM l){
        switch(message){
            case WM_CREATE:create_controls();return 0;
            case WM_SIZE:layout();InvalidateRect(hwnd_,nullptr,FALSE);return 0;
            case WM_GETMINMAXINFO:reinterpret_cast<MINMAXINFO*>(l)->ptMinTrackSize={px(900),px(640)};return 0;
            case WM_DPICHANGED:dpi_=HIWORD(w);refresh_font();{auto rect=reinterpret_cast<RECT*>(l);SetWindowPos(hwnd_,nullptr,rect->left,rect->top,rect->right-rect->left,rect->bottom-rect->top,SWP_NOZORDER);}return 0;
            case WM_ERASEBKGND:return 1;
            case WM_TIMER:poll();return 0;
            case WM_COMMAND:
                if(LOWORD(w)==401&&HIWORD(w)==LBN_SELCHANGE){auto row=SendMessageW(list_,LB_GETCURSEL,0,0);if(row!=LB_ERR)select(unsigned(row));return 0;}
                if(LOWORD(w)==403&&HIWORD(w)==CBN_SELCHANGE){step_=0;show_position();return 0;}
                command(LOWORD(w));return 0;
            case WM_DRAWITEM:draw_button(*reinterpret_cast<DRAWITEMSTRUCT*>(l));return TRUE;
            case WM_CTLCOLORLISTBOX:case WM_CTLCOLOREDIT:case WM_CTLCOLORSTATIC:
                SetBkColor(reinterpret_cast<HDC>(w),RGB(43,30,25));SetTextColor(reinterpret_cast<HDC>(w),RGB(246,225,199));return reinterpret_cast<LRESULT>(background_);
            case WM_LBUTTONDOWN:if(GET_X_LPARAM(l)<board_rect_.right&&GET_Y_LPARAM(l)>board_rect_.top){dragging_=true;mouse_={GET_X_LPARAM(l),GET_Y_LPARAM(l)};SetCapture(hwnd_);}return 0;
            case WM_LBUTTONUP:dragging_=false;ReleaseCapture();return 0;
            case WM_MOUSEMOVE:if(dragging_&&(w&MK_LBUTTON)){offset_.x+=GET_X_LPARAM(l)-mouse_.x;offset_.y+=GET_Y_LPARAM(l)-mouse_.y;mouse_={GET_X_LPARAM(l),GET_Y_LPARAM(l)};InvalidateRect(hwnd_,nullptr,FALSE);}return 0;
            case WM_MOUSEWHEEL:size_=std::clamp(size_*(GET_WHEEL_DELTA_WPARAM(w)>0?1.12:.89),12.,80.);InvalidateRect(hwnd_,nullptr,FALSE);return 0;
            case WM_PAINT:{PAINTSTRUCT ps{};auto dc=BeginPaint(hwnd_,&ps);paint(dc);EndPaint(hwnd_,&ps);return 0;}
            case WM_PRINTCLIENT:paint(reinterpret_cast<HDC>(w));return 0;
            case WM_CLOSE:stop_.request_stop();closing_=true;if(!worker_.valid())DestroyWindow(hwnd_);return 0;
            case WM_DESTROY:KillTimer(hwnd_,1);hwnd_=nullptr;if(owner_){EnableWindow(owner_,TRUE);SetForegroundWindow(owner_);}return 0;
        }
        return DefWindowProcW(hwnd_,message,w,l);
    }
    int px(int value)const{return MulDiv(value,dpi_,96);}
    void create_controls(){
        background_=CreateSolidBrush(RGB(43,30,25));
        std::vector<std::pair<unsigned,const wchar_t*>> labels{{301,L"\u2190"},{302,L"\u2192"},{303,L"Before / After"},{304,L"Next in line"},{305,L"Reset line"},{306,L"Details"},{307,L"Export"},{308,L"Cancel"}};
        for(auto [id,label]:labels){auto h=CreateWindowExW(0,L"BUTTON",label,WS_CHILD|WS_VISIBLE|BS_OWNERDRAW,0,0,1,1,hwnd_,reinterpret_cast<HMENU>(UINT_PTR(id)),instance_,nullptr);buttons_.push_back(h);}
        list_=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"",WS_CHILD|WS_VISIBLE|WS_VSCROLL|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT,0,0,1,1,hwnd_,reinterpret_cast<HMENU>(401),instance_,nullptr);
        text_=CreateWindowExW(0,L"EDIT",L"Validating the replay against Hive's rules.",WS_CHILD|WS_VISIBLE|WS_VSCROLL|ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL,0,0,1,1,hwnd_,reinterpret_cast<HMENU>(402),instance_,nullptr);
        lines_=CreateWindowExW(0,L"COMBOBOX",L"",WS_CHILD|WS_VISIBLE|CBS_DROPDOWNLIST|WS_VSCROLL,0,0,1,1,hwnd_,reinterpret_cast<HMENU>(403),instance_,nullptr);
        tooltip_=CreateWindowExW(WS_EX_TOPMOST,TOOLTIPS_CLASSW,nullptr,WS_POPUP|TTS_ALWAYSTIP,0,0,0,0,hwnd_,nullptr,instance_,nullptr);
        for(unsigned i=0;i<2;++i){TOOLINFOW tool{};tool.cbSize=sizeof(tool);tool.uFlags=TTF_IDISHWND|TTF_SUBCLASS;tool.hwnd=hwnd_;tool.uId=reinterpret_cast<UINT_PTR>(buttons_[i]);tool.lpszText=const_cast<wchar_t*>(i?L"Next move":L"Previous move");SendMessageW(tooltip_,TTM_ADDTOOLW,0,reinterpret_cast<LPARAM>(&tool));}
    }
    void refresh_font(){
        if(font_)DeleteObject(font_);
        font_=CreateFontW(-px(16),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Nunito");
        for(auto h:{list_,text_,lines_})SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(font_),TRUE);
        for(auto h:buttons_)SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(font_),TRUE);
    }
    void layout(){
        if(!hwnd_||!list_)return;
        RECT rc{};GetClientRect(hwnd_,&rc);int x=px(8),y=px(10);
        for(unsigned i=0;i<buttons_.size();++i){int width=px(i<2?40:i<5?108:80);if(x+width>rc.right-px(8)){x=px(8);y+=px(38);}MoveWindow(buttons_[i],x,y,width,px(30),TRUE);x+=width+px(8);}
        int toolbar=y+px(42);int panel=std::clamp(px(380),300,std::max(300,int(rc.right)*48/100));
        board_rect_={0,toolbar,rc.right-panel,rc.bottom};panel_rect_={rc.right-panel,toolbar,rc.right,rc.bottom};
        int top=toolbar+px(72),height=std::clamp(int(rc.bottom-top)/3,px(90),px(180));
        MoveWindow(list_,panel_rect_.left+px(12),top,panel-px(24),height,TRUE);
        MoveWindow(lines_,panel_rect_.left+px(12),top+height+px(12),panel-px(24),px(180),TRUE);
        int text_top=top+height+px(52);
        MoveWindow(text_,panel_rect_.left+px(12),text_top,panel-px(24),std::max(px(50),int(rc.bottom)-text_top-px(12)),TRUE);
        fit_board();
    }
    void fit_board(){
        if(display_.stacks().empty())return;
        double left=1e9,right=-1e9,top=1e9,bottom=-1e9;
        auto include=[&](Hex cell){auto x=1.5*cell.q,y=.8660254038*cell.q+1.7320508076*cell.r;
            left=std::min(left,x-1.);right=std::max(right,x+1.);top=std::min(top,y-1.);bottom=std::max(bottom,y+1.);};
        for(const auto& stack:display_.stacks())include(stack.cell);
        for(auto cell:highlights_)include(cell);
        const double scale=double(dpi_)/96.;
        auto width=std::max(1L,board_rect_.right-board_rect_.left-px(24));
        auto height=std::max(1L,board_rect_.bottom-board_rect_.top-px(24));
        size_=std::max(1.,std::min({38.,width/(scale*(right-left)),height/(scale*(bottom-top))}));
        offset_.x=LONG(-(left+right)*.5*size_*scale);offset_.y=LONG(-(top+bottom)*.5*size_*scale);
    }
    void command(unsigned id){
        if(id==301&&index_)select(index_-1);
        if(id==302&&index_+1<report_.moves.size())select(index_+1);
        if(id==303){before_=!before_;step_=0;show_position();}
        if(id==304){++step_;show_position();}
        if(id==305){step_=0;show_position();}
        if(id==306){details_=!details_;update_text();}
        if(id==307)export_report();
        if(id==308)stop_.request_stop();
    }
    void poll(){
        if(!shared_)return;bool changed=false;
        {std::lock_guard lock(shared_->mutex);if(version_!=shared_->version){version_=shared_->version;report_=shared_->report;changed=true;}}
        if(worker_.valid()&&worker_.wait_for(std::chrono::seconds(0))==std::future_status::ready){try{report_=worker_.get();}catch(...){report_.status="error";report_.message="Review could not finish.";}changed=true;}
        if(closing_&&!worker_.valid()){DestroyWindow(hwnd_);return;}
        if(changed){
            auto count=SendMessageW(list_,LB_GETCOUNT,0,0);
            if(count!=LRESULT(report_.moves.size())){
                SendMessageW(list_,LB_RESETCONTENT,0,0);
                for(const auto& e:report_.moves){auto label=std::to_string(e.ply)+". "+(e.move.piece.color==Color::white?"White - ":"Black - ")+std::string(e.move.kind==MoveKind::pass?"Pass":name(e.move.piece.bug));auto w=wide(label);SendMessageW(list_,LB_ADDSTRING,0,reinterpret_cast<LPARAM>(w.c_str()));}
                if(!report_.moves.empty())select(0);
            }else{update_choices();show_position();}
            InvalidateRect(hwnd_,nullptr,FALSE);
        }
    }
    void select(unsigned index){
        if(index>=report_.moves.size())return;
        index_=index;step_=0;SendMessageW(list_,LB_SETCURSEL,index,0);choices_.clear();update_choices();show_position();
    }
    void update_choices(){
        if(index_>=report_.moves.size())return;const auto& e=report_.moves[index_];std::vector<Line> choices;
        if(!e.variation.empty())choices.push_back({L"Alpha's possible continuation",e.before_game,e.variation});
        if(e.winning_reply)choices.push_back({L"Verified opponent winning reply",e.after_game,{*e.winning_reply}});
        if(e.immediate_win)choices.push_back({L"Verified immediate winning move",e.before_game,{*e.immediate_win}});
        if(choices==choices_)return;
        auto selected=SendMessageW(lines_,CB_GETCURSEL,0,0);choices_=std::move(choices);SendMessageW(lines_,CB_RESETCONTENT,0,0);
        for(const auto& line:choices_)SendMessageW(lines_,CB_ADDSTRING,0,reinterpret_cast<LPARAM>(line.label.c_str()));
        if(!choices_.empty())SendMessageW(lines_,CB_SETCURSEL,std::clamp<LRESULT>(selected,0,choices_.size()-1),0);
        EnableWindow(lines_,!choices_.empty());
    }
    void show_position(){
        if(index_>=report_.moves.size())return;const auto& e=report_.moves[index_];
        auto game=before_?e.before_game:e.after_game;auto selected=SendMessageW(lines_,CB_GETCURSEL,0,0);highlights_.clear();
        if(step_&&selected>=0&&std::size_t(selected)<choices_.size()){
            const auto& line=choices_[selected];auto board=Board::from_game_string(line.start);if(!board)return;
            step_=std::min<unsigned>(step_,line.moves.size());
            for(unsigned i=0;i<step_;++i){auto move=board->parse_uhp_move(line.moves[i]);if(!move||!board->play(*move))return;if(i+1==step_){if(move->from)highlights_.push_back(*move->from);highlights_.push_back(move->to);}}
            display_=std::move(*board);
        }else{
            step_=0;auto board=Board::from_game_string(game);if(!board)return;display_=std::move(*board);
            if(e.move.kind!=MoveKind::pass){if(e.move.from)highlights_.push_back(*e.move.from);highlights_.push_back(e.move.to);}
            for(const auto& f:e.facts)for(auto cell:f.cells)highlights_.push_back(cell);
        }
        fit_board();update_text();InvalidateRect(hwnd_,nullptr,FALSE);
    }
    void update_text(){
        std::string text;
        if(index_<report_.moves.size()){
            const auto& e=report_.moves[index_];text=e.explanation;
            if(e.status=="unanalysed")text+="\r\n\r\nDeeper analysis has not completed for this move.";
            if(step_)text+="\r\n\r\nOne possible continuation. The original game is unchanged.";
            if(details_){text+="\r\n\r\nVerified board details\r\n";for(const auto& f:e.facts)text+="\r\n"+f.english+"\r\n";
                text+=e.tactical_complete?"\r\nImmediate tactical checks completed.":"\r\nTactical checks are incomplete. Absence of a warning is not proof of safety.";
                if(e.preferred){text+="\r\n\r\nOne possible alternative\r\n";for(const auto& f:e.alternative_facts)text+="\r\n"+f.english+"\r\n";text+="\r\nAlpha's preference is a bounded-search estimate, not a winning probability.";}}
        }
        if(!report_.message.empty())text+="\r\n\r\n"+report_.message;
        if(text!=text_cache_){text_cache_=text;auto w=wide(text);SetWindowTextW(text_,w.c_str());}
    }
    POINT point(Hex hex)const{
        const double size=size_*dpi_/96.;return {LONG(board_rect_.right/2+offset_.x+size*1.5*hex.q),LONG((board_rect_.top+board_rect_.bottom)/2+offset_.y+size*(.8660254038*hex.q+1.7320508076*hex.r))};
    }
    void draw_button(const DRAWITEMSTRUCT& item){
        auto fill=CreateSolidBrush(item.itemState&ODS_SELECTED?RGB(121,70,40):RGB(66,44,33));FillRect(item.hDC,&item.rcItem,fill);DeleteObject(fill);
        auto old=SelectObject(item.hDC,font_);SetBkMode(item.hDC,TRANSPARENT);SetTextColor(item.hDC,RGB(246,225,199));
        wchar_t label[64]{};GetWindowTextW(item.hwndItem,label,64);auto rect=item.rcItem;DrawTextW(item.hDC,label,-1,&rect,DT_CENTER|DT_VCENTER|DT_SINGLELINE);SelectObject(item.hDC,old);
        if(item.itemState&ODS_FOCUS)DrawFocusRect(item.hDC,&item.rcItem);
    }
    void paint(HDC dc){
        RECT rc{};GetClientRect(hwnd_,&rc);auto bg=CreateSolidBrush(RGB(25,19,17));FillRect(dc,&rc,bg);DeleteObject(bg);FillRect(dc,&panel_rect_,background_);
        auto old_font=SelectObject(dc,font_);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(246,225,199));
        auto title=wide(std::string(report_.partial_game?"Partial game review":"Game review")+" - "+std::to_string(report_.completed)+" / "+std::to_string(report_.moves.size())+" analysed");
        RECT heading{panel_rect_.left+px(12),panel_rect_.top+px(8),panel_rect_.right-px(12),panel_rect_.top+px(34)};DrawTextW(dc,title.c_str(),-1,&heading,DT_SINGLELINE|DT_END_ELLIPSIS);
        auto state=wide(report_.status+(step_?" - One possible continuation":before_?" - Before move":" - After move"));heading.top+=px(30);heading.bottom+=px(30);DrawTextW(dc,state.c_str(),-1,&heading,DT_SINGLELINE|DT_END_ELLIPSIS);
        auto clip=CreateRectRgn(board_rect_.left,board_rect_.top,board_rect_.right,board_rect_.bottom);SelectClipRgn(dc,clip);
        for(const auto& stack:display_.stacks()){
            auto center=point(stack.cell);const auto top=stack.pieces.back();double radius=size_*dpi_/96.*.82;
            soft_hex(dc,{center.x,center.y+px(3)},radius,RGB(17,12,10),RGB(17,12,10),1.f);
            soft_hex(dc,center,radius,top.color==Color::white?RGB(255,247,230):RGB(81,50,40),RGB(133,94,63),1.3f);
            RECT icon{center.x-LONG(radius*.6),center.y-LONG(radius*.6),center.x+LONG(radius*.6),center.y+LONG(radius*.6)};
            icons_.draw(dc,unsigned(top.bug),icon,top.color==Color::white?RGB(92,53,33):RGB(255,235,200));
            if(stack.pieces.size()>1){auto badge=wide("x"+std::to_string(stack.pieces.size()));RECT r{center.x+px(16),center.y+px(12),center.x+px(44),center.y+px(32)};SetTextColor(dc,RGB(250,224,185));DrawTextW(dc,badge.c_str(),-1,&r,DT_CENTER|DT_SINGLELINE);}
        }
        auto pen=CreatePen(PS_SOLID,px(2),RGB(232,173,83));auto old_pen=SelectObject(dc,pen);auto old_brush=SelectObject(dc,GetStockObject(NULL_BRUSH));
        for(auto cell:highlights_){auto center=point(cell);POINT polygon[7];for(int i=0;i<7;++i){auto angle=i*3.141592653589793/3;polygon[i]={LONG(center.x+std::cos(angle)*size_*dpi_/96.*.92),LONG(center.y+std::sin(angle)*size_*dpi_/96.*.92)};}Polyline(dc,polygon,7);}
        SelectObject(dc,old_pen);SelectObject(dc,old_brush);DeleteObject(pen);SelectClipRgn(dc,nullptr);DeleteObject(clip);SelectObject(dc,old_font);
    }
    void export_report(){
        wchar_t filename[MAX_PATH]=L"game-review.json";OPENFILENAMEW dialog{};dialog.lStructSize=sizeof(dialog);dialog.hwndOwner=hwnd_;dialog.lpstrFilter=L"Game review JSON\0*.json\0";dialog.lpstrFile=filename;dialog.nMaxFile=MAX_PATH;dialog.lpstrDefExt=L"json";dialog.Flags=OFN_OVERWRITEPROMPT|OFN_PATHMUSTEXIST;
        if(GetSaveFileNameW(&dialog)){auto written=save(report_,filename);if(!written)MessageBoxW(hwnd_,wide(written.error()).c_str(),L"Review export",MB_ICONERROR);}
    }
    bool snapshot(const std::filesystem::path& path){
        RECT rc{};GetClientRect(hwnd_,&rc);auto window_dc=GetDC(hwnd_);auto dc=CreateCompatibleDC(window_dc);
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=rc.right;info.bmiHeader.biHeight=-rc.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
        void* pixels=nullptr;auto bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixels,nullptr,0);auto old=SelectObject(dc,bitmap);
        SendMessageW(hwnd_,WM_PRINTCLIENT,reinterpret_cast<WPARAM>(dc),PRF_CLIENT);
        for(auto child=GetWindow(hwnd_,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT)){
            if(!(GetWindowLongPtrW(child,GWL_STYLE)&WS_VISIBLE))continue;
            RECT bounds{};GetWindowRect(child,&bounds);MapWindowPoints(nullptr,hwnd_,reinterpret_cast<POINT*>(&bounds),2);
            int saved=SaveDC(dc);IntersectClipRect(dc,bounds.left,bounds.top,bounds.right,bounds.bottom);
            SetViewportOrgEx(dc,bounds.left,bounds.top,nullptr);
            SendMessageW(child,WM_PRINT,reinterpret_cast<WPARAM>(dc),PRF_CLIENT|PRF_NONCLIENT);
            RestoreDC(dc,saved);
        }
        GdiFlush();
        unsigned nonblank=0;if(pixels){auto bytes=static_cast<DWORD*>(pixels);for(int i=0;i<rc.right*rc.bottom;++i)if((bytes[i]&0xffffff)!=0)++nonblank;}
        BITMAPFILEHEADER header{};header.bfType=0x4d42;header.bfOffBits=sizeof(header)+sizeof(info.bmiHeader);header.bfSize=header.bfOffBits+rc.right*rc.bottom*4;
        std::ofstream file(path,std::ios::binary);file.write(reinterpret_cast<char*>(&header),sizeof(header));file.write(reinterpret_cast<char*>(&info.bmiHeader),sizeof(info.bmiHeader));if(pixels)file.write(static_cast<char*>(pixels),rc.right*rc.bottom*4);
        SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);ReleaseDC(hwnd_,window_dc);return file.good()&&nonblank>unsigned(rc.right*rc.bottom/2);
    }
    HINSTANCE instance_=nullptr;HWND owner_=nullptr,hwnd_=nullptr,list_=nullptr,text_=nullptr,lines_=nullptr,tooltip_=nullptr;
    HFONT font_=nullptr;HBRUSH background_=nullptr;SvgIcons icons_;std::vector<HWND> buttons_;
    std::shared_ptr<Shared> shared_;std::future<Report> worker_;std::stop_source stop_;Report report_;
    Board display_;std::vector<Line> choices_;std::vector<Hex> highlights_;std::string text_cache_;
    unsigned index_=0,step_=0,version_=0,dpi_=96;bool before_=false,details_=false,closing_=false,testing_=false,dragging_=false;
    RECT board_rect_{},panel_rect_{};POINT offset_{},mouse_{};double size_=38.;
};
}
