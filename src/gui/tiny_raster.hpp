#pragma once

class TinyRaster {
    struct Sprite {HBITMAP bitmap;int width,height;};
    std::map<std::uint64_t,Sprite> cache_;
    HMODULE library_=nullptr;
    using New=void*(*)(unsigned,unsigned);
    using Free=void(*)(void*);
    using EllipseFn=void(*)(void*,float,float,float,float,std::uint32_t,bool,float);
    using PathFn=void(*)(void*,const float*,unsigned,std::uint32_t,bool,bool,float);
    using Pixels=const unsigned char*(*)(void*);
    New create_=nullptr;Free free_=nullptr;EllipseFn ellipse_=nullptr;PathFn path_=nullptr;Pixels pixels_=nullptr;
public:
    TinyRaster() {
        wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);
        auto dll=std::filesystem::path(executable).parent_path()/L"genseki_raster.dll";
        library_=LoadLibraryW(dll.c_str());
        if(!library_)return;
        create_=reinterpret_cast<New>(GetProcAddress(library_,"gs_canvas_new"));
        free_=reinterpret_cast<Free>(GetProcAddress(library_,"gs_canvas_free"));
        ellipse_=reinterpret_cast<EllipseFn>(GetProcAddress(library_,"gs_canvas_ellipse"));
        path_=reinterpret_cast<PathFn>(GetProcAddress(library_,"gs_canvas_path"));
        pixels_=reinterpret_cast<Pixels>(GetProcAddress(library_,"gs_canvas_pixels"));
    }
    ~TinyRaster(){for(auto [key,sprite]:cache_)DeleteObject(sprite.bitmap);if(library_)FreeLibrary(library_);}
    bool ready()const{return create_&&free_&&ellipse_&&path_&&pixels_;}
    static std::uint32_t rgba(COLORREF color,unsigned alpha=255){return GetRValue(color)<<24|GetGValue(color)<<16|GetBValue(color)<<8|alpha;}
    void* create(unsigned w,unsigned h){return ready()?create_(w,h):nullptr;}
    void release(void* c){free_(c);}
    void ellipse(void* c,float x,float y,float rx,float ry,COLORREF color,bool filled,float width=2,unsigned alpha=255){ellipse_(c,x,y,rx,ry,rgba(color,alpha),filled,width);}
    void path(void* c,const std::vector<float>& points,COLORREF color,bool closed,bool filled,float width=2,unsigned alpha=255){path_(c,points.data(),unsigned(points.size()/2),rgba(color,alpha),closed,filled,width);}
    bool cached(HDC dc,std::uint64_t key,int x,int y) {
        auto it=cache_.find(key);if(it==cache_.end())return false;
        auto sprite=it->second;HDC source=CreateCompatibleDC(dc);auto old=SelectObject(source,sprite.bitmap);
        BLENDFUNCTION blend{AC_SRC_OVER,0,255,AC_SRC_ALPHA};AlphaBlend(dc,x,y,sprite.width,sprite.height,source,0,0,sprite.width,sprite.height,blend);
        SelectObject(source,old);DeleteDC(source);return true;
    }
    void present(HDC dc,void* canvas,int x,int y,int w,int h,std::uint64_t key=0) {
        if(!canvas)return;
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=w;
        info.bmiHeader.biHeight=-h;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
        void* data=nullptr;HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&data,nullptr,0);
        if(!bitmap||!data){if(bitmap)DeleteObject(bitmap);return;}
        std::memcpy(data,pixels_(canvas),std::size_t(w)*h*4);
        HDC source=CreateCompatibleDC(dc);auto old=SelectObject(source,bitmap);
        BLENDFUNCTION blend{AC_SRC_OVER,0,255,AC_SRC_ALPHA};AlphaBlend(dc,x,y,w,h,source,0,0,w,h,blend);
        SelectObject(source,old);DeleteDC(source);
        if(key) {
            if(cache_.size()>=256){for(auto [id,sprite]:cache_)DeleteObject(sprite.bitmap);cache_.clear();}
            auto found=cache_.find(key);if(found!=cache_.end())DeleteObject(found->second.bitmap);
            cache_[key]={bitmap,w,h};
        }else DeleteObject(bitmap);
    }
};
inline TinyRaster& tiny_raster(){static TinyRaster raster;return raster;}

inline void soft_hex(HDC dc,POINT center,double radius,COLORREF fill,COLORREF edge,float width) {
    radius=std::round(radius*4)/4;
    auto& raster=tiny_raster();int side=int(std::ceil(radius*2))+10;
    std::uint64_t key=std::uint64_t(fill)|(std::uint64_t(edge)<<24)|(std::uint64_t(side)<<48)
        |(std::uint64_t(std::lround(width))<<56)|(std::uint64_t(std::lround(radius*4)%4)<<60)|(1ULL<<62);
    if(raster.cached(dc,key,center.x-side/2,center.y-side/2))return;
    void* canvas=raster.create(side,side);if(!canvas)return;
    std::vector<float> points;
    for(int i=0;i<6;++i){double angle=i*3.141592653589793/3;points.push_back(float(side/2.+radius*std::cos(angle)));points.push_back(float(side/2.+radius*std::sin(angle)));}
    raster.path(canvas,points,fill,true,true);raster.path(canvas,points,edge,true,false,width);
    raster.present(dc,canvas,center.x-side/2,center.y-side/2,side,side,key);raster.release(canvas);
}
