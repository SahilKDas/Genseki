#pragma once
#include "encoding.hpp"
#include <fstream>
#include <functional>
#include <numeric>
#include <span>
#include <future>

namespace iota {
struct Prediction {float value=0;std::vector<float> policy;std::array<float,3> wdl{};};
struct Model {
    bool cnn=false;int version=1,width=0,blocks=0,threads=1;uint64_t checksum=0;std::vector<float> weights;
    template<class F> void rows(int n,F fn) const {
        int count=std::min(n,threads);if(count<=1){fn(0,n);return;}
        std::vector<std::future<void>> jobs;std::exception_ptr error;
        for(int t=1;t<count;++t)jobs.push_back(std::async(std::launch::async,[&,t]{fn(n*t/count,n*(t+1)/count);}));
        try{fn(0,n/count);}catch(...){error=std::current_exception();}
        for(auto& j:jobs)try{j.get();}catch(...){if(!error)error=std::current_exception();}
        if(error)std::rethrow_exception(error);
    }
    void load(const std::string& path){
        std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("model not found");
        std::array<uint32_t,6> hdr{};uint64_t sum=0;f.read(reinterpret_cast<char*>(hdr.data()),sizeof(hdr));f.read(reinterpret_cast<char*>(&sum),8);
        if(!f||hdr[0]!=0x41544f49||(hdr[1]<1||hdr[1]>3)||(hdr[1]==3&&hdr[2]!=0)||hdr[2]>1||!(hdr[3]==32||hdr[3]==64)||!(hdr[4]==4||hdr[4]==6))throw std::runtime_error("invalid model header");
        bool c=hdr[2]==0;int w=hdr[3],n=hdr[4],kernels=hdr[1]==1||hdr[1]==3?7:c?2:6;size_t expected=features*w+w+n*(kernels*w*w+w)+3*w+3+(3*w+action_features)+1;
        if(hdr[5]!=expected)throw std::runtime_error("model dimensions mismatch");
        std::vector<float> data(expected);f.read(reinterpret_cast<char*>(data.data()),data.size()*4);char trailing;if(!f||f.get(trailing))throw std::runtime_error("model size mismatch");
        uint64_t actual=1469598103934665603ull;for(auto b:std::span(reinterpret_cast<const unsigned char*>(data.data()),data.size()*4)){actual^=b;actual*=1099511628211ull;}
        for(float x:data)if(!std::isfinite(x))throw std::runtime_error("nonfinite model");if(actual!=sum)throw std::runtime_error("model checksum mismatch");
        cnn=c;version=hdr[1];width=w;blocks=n;weights=std::move(data);checksum=sum;
    }
    Prediction predict(const Board& b,const std::vector<Move>& moves,const std::function<void()>& check=[] {}) const {
        if(weights.empty())throw std::runtime_error("load a neural model first");
        auto e=encode(b,cnn,version>=2,version==3);int N=e.cells.size(),W=width;size_t at=0;
        auto matrix=[&](int size){auto p=weights.data()+at;at+=size;return p;};
        auto iw=matrix(W*features),ib=matrix(W);std::vector<float> h(N*W),next(N*W);
        rows(N,[&](int begin,int end){for(int i=begin;i<end;++i){if(i%16==0)check();for(int o=0;o<W;++o){float s=ib[o];for(int k=0;k<features;++k)s+=iw[o*features+k]*e.x[i*features+k];h[i*W+o]=std::max(0.f,s);}}});
        int relations=version==3?6:cnn?1:5,kernels=version==1?7:relations+1;
        std::vector<std::vector<std::pair<int,int>>> incoming(N);
        if(version>=2)for(auto link:e.links)incoming[link[0]].push_back({link[1],link[2]});
        for(int layer=0;layer<blocks;++layer){auto kw=matrix(kernels*W*W),bias=matrix(W);
            if(version==1)rows(N,[&](int begin,int end){for(int i=begin;i<end;++i){if(i%8==0)check();for(int o=0;o<W;++o){float s=bias[o];for(int d=0;d<7;++d){int j=d==0?i:e.edges[i][d-1];if(j<0)continue;for(int k=0;k<W;++k)s+=kw[(d*W+o)*W+k]*h[j*W+k];}next[i*W+o]=std::max(0.f,h[i*W+o]+s/7.f);}}});
            else rows(N,[&](int begin,int end){std::vector<float> aggregate(relations*W);std::vector<int> degree(relations);for(int i=begin;i<end;++i){if(i%8==0)check();std::fill(aggregate.begin(),aggregate.end(),0);std::fill(degree.begin(),degree.end(),0);for(auto [j,r]:incoming[i]){++degree[r];for(int k=0;k<W;++k)aggregate[r*W+k]+=h[j*W+k];}for(int o=0;o<W;++o){float s=bias[o];for(int k=0;k<W;++k)s+=kw[o*W+k]*h[i*W+k];for(int r=0;r<relations;++r)if(degree[r])for(int k=0;k<W;++k)s+=kw[((r+1)*W+o)*W+k]*aggregate[r*W+k]/(cnn?1:degree[r]);next[i*W+o]=std::max(0.f,h[i*W+o]+s/(cnn?7:relations+1));}}});
            h.swap(next);}
        std::vector<float> pooled(W);for(int i=0;i<N;++i)for(int k=0;k<W;++k)pooled[k]+=h[i*W+k]/N;
        Prediction p;auto vw=matrix(3*W),vb=matrix(3);float max=-1e30f;
        for(int o=0;o<3;++o){float s=vb[o];for(int k=0;k<W;++k)s+=vw[o*W+k]*pooled[k];p.wdl[o]=s;max=std::max(max,s);}float total=0;for(auto& v:p.wdl){v=std::exp(v-max);total+=v;}for(auto& v:p.wdl)v/=total;p.value=p.wdl[0]-p.wdl[2];
        auto pw=matrix(3*W+action_features),pb=matrix(1);for(auto& m:moves){float s=*pb;auto src=m.from?e.index.find(*m.from):e.index.end(),dst=(version>=2&&m.kind==MoveKind::pass)?e.index.end():e.index.find(m.to);int si=src==e.index.end()?-1:src->second;if(version>=2&&!cnn&&m.from)si=e.stones.at(m.piece);for(int k=0;k<W;++k){s+=pw[k]*pooled[k];if(si>=0)s+=pw[W+k]*h[si*W+k];if(dst!=e.index.end())s+=pw[2*W+k]*h[dst->second*W+k];}auto a=action(b,m,version>=2);for(int k=0;k<action_features;++k)s+=pw[3*W+k]*a[k];if(!std::isfinite(s))throw std::runtime_error("nonfinite inference");p.policy.push_back(s);}if(!std::isfinite(p.value))throw std::runtime_error("nonfinite inference");return p;
    }
};
}
