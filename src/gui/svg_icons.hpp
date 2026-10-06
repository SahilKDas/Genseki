#pragma once
#include <msxml2.h>

// Small native renderer for our embedded SVG circles, ellipses and polylines.
struct SvgShape {
    std::wstring type;
    bool filled=true;
    double x=0,y=0,rx=0,ry=0;
    std::vector<POINT> points;
};
class SvgIcons {
    std::array<std::vector<SvgShape>,5> icons_;
    static std::wstring attribute(IXMLDOMElement* element,const wchar_t* name) {
        VARIANT value;VariantInit(&value);BSTR key=SysAllocString(name);
        element->getAttribute(key,&value);SysFreeString(key);
        std::wstring result=value.vt==VT_BSTR?value.bstrVal:L"";
        VariantClear(&value);return result;
    }
    static double number(IXMLDOMElement* element,const wchar_t* name) {
        return wcstod(attribute(element,name).c_str(),nullptr);
    }
public:
    bool load(HINSTANCE instance) {
        CLSID clsid;IID iid;
        CLSIDFromString(L"{88D96A05-F192-11D4-A65F-0040963251E5}",&clsid);
        IIDFromString(L"{2933BF81-7B36-11D2-B20E-00C04F983E60}",&iid);
        for(unsigned i=0;i<icons_.size();++i) {
            auto resource=FindResourceW(instance,MAKEINTRESOURCEW(501+i),RT_RCDATA);
            if(!resource)return false;
            auto bytes=static_cast<const char*>(LockResource(LoadResource(instance,resource)));
            int size=int(SizeofResource(instance,resource));
            int length=MultiByteToWideChar(CP_UTF8,0,bytes,size,nullptr,0);
            BSTR xml=SysAllocStringLen(nullptr,length);
            MultiByteToWideChar(CP_UTF8,0,bytes,size,xml,length);
            IXMLDOMDocument* document=nullptr;
            if(FAILED(CoCreateInstance(clsid,nullptr,CLSCTX_INPROC_SERVER,iid,reinterpret_cast<void**>(&document)))) {SysFreeString(xml);return false;}
            document->put_async(VARIANT_FALSE);document->put_resolveExternals(VARIANT_FALSE);
            VARIANT_BOOL loaded=VARIANT_FALSE;document->loadXML(xml,&loaded);SysFreeString(xml);
            if(!loaded){document->Release();return false;}
            IXMLDOMNodeList* nodes=nullptr;BSTR all=SysAllocString(L"*");
            document->getElementsByTagName(all,&nodes);SysFreeString(all);
            long count=0;nodes->get_length(&count);
            for(long n=0;n<count;++n) {
                IXMLDOMNode* node=nullptr;nodes->get_item(n,&node);
                IXMLDOMElement* element=nullptr;
                IID element_iid;IIDFromString(L"{2933BF86-7B36-11D2-B20E-00C04F983E60}",&element_iid);
                node->QueryInterface(element_iid,reinterpret_cast<void**>(&element));node->Release();
                if(!element)continue;
                BSTR tag=nullptr;element->get_tagName(&tag);
                SvgShape shape;shape.type=tag;SysFreeString(tag);
                shape.filled=attribute(element,L"fill")!=L"none";
                if(shape.type==L"circle"||shape.type==L"ellipse") {
                    shape.x=number(element,L"cx");shape.y=number(element,L"cy");
                    shape.rx=number(element,shape.type==L"circle"?L"r":L"rx");
                    shape.ry=shape.type==L"circle"?shape.rx:number(element,L"ry");
                } else if(shape.type==L"line") {
                    shape.points={{LONG(number(element,L"x1")),LONG(number(element,L"y1"))},
                                  {LONG(number(element,L"x2")),LONG(number(element,L"y2"))}};
                } else if(shape.type==L"polyline") {
                    auto points=attribute(element,L"points");std::replace(points.begin(),points.end(),L',',L' ');
                    std::wistringstream input(points);long x,y;while(input>>x>>y)shape.points.push_back({x,y});
                }
                element->Release();
                if(shape.type!=L"svg")icons_[i].push_back(std::move(shape));
            }
            nodes->Release();document->Release();
        }
        return true;
    }
    void draw(HDC dc,unsigned insect,RECT rect,COLORREF color) const {
        auto& raster=tiny_raster();
        int w=rect.right-rect.left,h=rect.bottom-rect.top;
        if(raster.ready()&&w>0&&h>0) {
            std::uint64_t key=(1ULL<<63)|std::uint64_t(color)|(std::uint64_t(w)<<24)|(std::uint64_t(h)<<35)|(std::uint64_t(insect)<<46);
            if(raster.cached(dc,key,rect.left,rect.top))return;
            void* canvas=raster.create(w,h);if(!canvas)return;
            const float scale=std::min(w,h)/64.f,ox=(w-64*scale)/2,oy=(h-64*scale)/2;
            for(const auto& shape:icons_[insect]) {
                if(shape.type==L"circle"||shape.type==L"ellipse")raster.ellipse(canvas,ox+float(shape.x)*scale,oy+float(shape.y)*scale,float(shape.rx)*scale,float(shape.ry)*scale,color,shape.filled,2.5f*scale);
                else {std::vector<float> points;for(auto p:shape.points){points.push_back(ox+p.x*scale);points.push_back(oy+p.y*scale);}raster.path(canvas,points,color,false,false,2.5f*scale);}
            }
            raster.present(dc,canvas,rect.left,rect.top,w,h,key);raster.release(canvas);return;
        }
        const double scale=std::min(rect.right-rect.left,rect.bottom-rect.top)/64.0;
        const double ox=(rect.left+rect.right-64*scale)/2,oy=(rect.top+rect.bottom-64*scale)/2;
        auto x=[&](double v){return LONG(std::lround(ox+v*scale));};
        auto y=[&](double v){return LONG(std::lround(oy+v*scale));};
        HPEN pen=CreatePen(PS_SOLID,std::max(1,int(std::lround(scale*2.5))),color);
        HBRUSH brush=CreateSolidBrush(color);auto previous_pen=SelectObject(dc,pen);auto previous_brush=SelectObject(dc,brush);
        for(const auto& shape:icons_[insect]) {
            SelectObject(dc,shape.filled?brush:GetStockObject(NULL_BRUSH));
            if(shape.type==L"circle"||shape.type==L"ellipse")Ellipse(dc,x(shape.x-shape.rx),y(shape.y-shape.ry),x(shape.x+shape.rx),y(shape.y+shape.ry));
            else {std::vector<POINT> points;for(auto p:shape.points)points.push_back({x(p.x),y(p.y)});if(points.size()>1)Polyline(dc,points.data(),int(points.size()));}
        }
        SelectObject(dc,previous_brush);SelectObject(dc,previous_pen);DeleteObject(brush);DeleteObject(pen);
    }
};
