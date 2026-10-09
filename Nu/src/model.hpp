#pragma once
#include "features8.hpp"
#include <fstream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#if defined(__GNUC__) && defined(__x86_64__)
#include <immintrin.h>
#endif

namespace nu {
constexpr unsigned quant_scale=256;
inline std::uint64_t checksum(const std::vector<unsigned char>& bytes) {
    std::uint64_t h=14695981039346656037ULL;
    for(auto b:bytes) {h^=b;h*=1099511628211ULL;}
    return h;
}
struct Model {
    unsigned hidden=64;
    unsigned feature_schema=schema;
    std::vector<std::int16_t> embedding, output;
    std::vector<std::int32_t> bias;
    unsigned head=0;
    std::vector<std::int16_t> head_weights;
    std::vector<std::int32_t> head_bias;
    std::string identity="untrained-seed-1701";
    std::size_t allocated_bytes()const {
        return sizeof(*this)+embedding.capacity()*sizeof(std::int16_t)+output.capacity()*sizeof(std::int16_t)
            +bias.capacity()*sizeof(std::int32_t)+head_weights.capacity()*sizeof(std::int16_t)
            +head_bias.capacity()*sizeof(std::int32_t)+identity.capacity();
    }
    explicit Model(unsigned width=64):hidden(width),embedding(feature_count*width),output(width),bias(width) {
        if(width!=64&&width!=128) throw std::runtime_error("unsupported architecture");
        std::mt19937 rng(1701);
        for(auto& x:embedding) x=std::int16_t(int(rng()%17)-8);
        for(auto& x:output) x=std::int16_t(int(rng()%65)-32);
    }
    void load(const std::string& path) {
        std::ifstream f(path,std::ios::binary|std::ios::ate);
        if(!f||f.tellg()>8*1024*1024||f.tellg()<32) throw std::runtime_error("invalid model size");
        std::vector<unsigned char> bytes(std::size_t(f.tellg())); f.seekg(0);
        f.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size()));
        if(!f) throw std::runtime_error("truncated model");
        auto u32=[&](unsigned offset) {std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(bytes.at(offset+i))<<(8*i);return v;};
        auto magic=std::string(reinterpret_cast<char*>(bytes.data()),8);
        bool nonlinear=magic==std::string("NUNNUE2\0",8);
        if((magic!=std::string("NUNNUE1\0",8)&&!nonlinear)
            ||u32(8)<1||u32(8)>latest_schema||u32(12)!=feature_count||u32(20)!=quant_scale) throw std::runtime_error("model schema mismatch");
        unsigned width=u32(16);
        if(width!=64&&width!=128)throw std::runtime_error("unsupported model width");
        auto size=32+width*4+feature_count*width*2+(nonlinear?32*2*width*2+32*4+32*2:width*2);
        if(bytes.size()!=size)throw std::runtime_error("model dimensions mismatch");
        std::uint64_t expected=0;for(unsigned i=0;i<8;++i)expected|=std::uint64_t(bytes[24+i])<<(8*i);
        std::vector<unsigned char> payload(bytes.begin()+32,bytes.end());
        if(checksum(payload)!=expected)throw std::runtime_error("model checksum mismatch");
        Model loaded(width);loaded.feature_schema=u32(8);unsigned at=32;
        for(auto& v:loaded.bias) {v=std::bit_cast<std::int32_t>(u32(at));at+=4;if(std::abs(std::int64_t(v))>1000000)throw std::runtime_error("invalid bias");}
        auto read16=[&]() {auto v=std::uint16_t(bytes[at])|std::uint16_t(bytes[at+1])<<8;at+=2;return std::bit_cast<std::int16_t>(std::uint16_t(v));};
        for(auto& v:loaded.embedding)v=read16();
        if(nonlinear) {
            loaded.head=32;loaded.head_weights.resize(32*2*width);loaded.head_bias.resize(32);loaded.output.resize(32);
            for(auto& v:loaded.head_weights)v=read16();
            for(auto& v:loaded.head_bias){v=std::bit_cast<std::int32_t>(u32(at));at+=4;if(std::abs(std::int64_t(v))>1000000)throw std::runtime_error("invalid head bias");}
        }
        for(auto& v:loaded.output)v=read16();
        loaded.identity=path; *this=std::move(loaded);
    }
};
struct Accumulator {
    std::array<std::vector<std::int32_t>,2> sums;
    explicit Accumulator(const Model& m):sums{m.bias,m.bias} {}
    static const char* backend(const Model& m) {
#if defined(__GNUC__) && defined(__x86_64__)
        if(m.feature_schema==8&&__builtin_cpu_supports("avx2"))return "avx2";
        if(m.feature_schema==8&&__builtin_cpu_supports("sse4.1"))return "sse4.1";
#endif
        return "scalar";
    }
    void add(const Model& m,unsigned perspective,unsigned feature,int sign) {
#if defined(__GNUC__) && defined(__x86_64__)
        if(m.feature_schema==8&&__builtin_cpu_supports("avx2")){add_avx2(m,perspective,feature,sign);return;}
        if(m.feature_schema==8&&__builtin_cpu_supports("sse4.1")){add_vectorized(m,perspective,feature,sign);return;}
#endif
        for(unsigned j=0;j<m.hidden;++j)sums[perspective][j]+=sign*m.embedding[feature*m.hidden+j];
    }
#if defined(__GNUC__) && defined(__x86_64__)
    __attribute__((target("avx2"))) void add_avx2(const Model& m,unsigned perspective,unsigned feature,int sign) {
        for(unsigned j=0;j<m.hidden;j+=8) {
            auto weights=_mm256_cvtepi16_epi32(_mm_loadu_si128(reinterpret_cast<const __m128i*>(m.embedding.data()+feature*m.hidden+j)));
            auto current=_mm256_loadu_si256(reinterpret_cast<const __m256i*>(sums[perspective].data()+j));
            auto next=sign==1?_mm256_add_epi32(current,weights):_mm256_sub_epi32(current,weights);
            _mm256_storeu_si256(reinterpret_cast<__m256i*>(sums[perspective].data()+j),next);
        }
    }
    __attribute__((target("sse4.1"))) void add_vectorized(const Model& m,unsigned perspective,unsigned feature,int sign) {
        for(unsigned j=0;j<m.hidden;j+=4) {
            auto weights=_mm_cvtepi16_epi32(_mm_loadl_epi64(reinterpret_cast<const __m128i*>(m.embedding.data()+feature*m.hidden+j)));
            auto current=_mm_loadu_si128(reinterpret_cast<const __m128i*>(sums[perspective].data()+j));
            auto next=sign==1?_mm_add_epi32(current,weights):_mm_sub_epi32(current,weights);
            _mm_storeu_si128(reinterpret_cast<__m128i*>(sums[perspective].data()+j),next);
        }
    }
#endif
    void update_blocks(const Model& m,const FastFeatures8& old,const FastFeatures8& next) {
        for(unsigned id=0;id<22;++id)if(old.pieces[id]!=next.pieces[id])for(unsigned p=0;p<2;++p) {
            for(auto feature:old.encoded[id][p])add(m,p,feature,-1);
            for(auto feature:next.encoded[id][p])add(m,p,feature,1);
        }
        for(unsigned p=0;p<2;++p)for(unsigned color=0;color<2;++color)if(old.queen_features[p][color]!=next.queen_features[p][color]) {
            add(m,p,old.queen_features[p][color],-1);add(m,p,next.queen_features[p][color],1);
        }
    }
    void refresh(const Model& m,const Features& f) {
        sums={m.bias,m.bias};
        for(unsigned p=0;p<2;++p)for(auto id:f[p])add(m,p,id,1);
    }
    void update(const Model& m,const Features& old,const Features& next) {
        for(unsigned p=0;p<2;++p) {
            unsigned i=0,j=0;
            while(i<old[p].size()||j<next[p].size()) {
                if(j==next[p].size()||(i<old[p].size()&&old[p][i]<next[p][j]))add(m,p,old[p][i++],-1);
                else if(i==old[p].size()||next[p][j]<old[p][i])add(m,p,next[p][j++],1);
                else {++i;++j;}
            }
        }
    }
    std::int64_t scalar(const Model& m,Color side) const {
        std::int64_t value=0;
        if(m.head) {
            for(unsigned j=0;j<m.head;++j) {
                std::array<std::int64_t,2> activation{std::int64_t(m.head_bias[j])*quant_scale,std::int64_t(m.head_bias[j])*quant_scale};
                for(unsigned p=0;p<2;++p)for(unsigned k=0;k<m.hidden;++k) {
                    auto weight=m.head_weights[j*2*m.hidden+p*m.hidden+k];
                    for(unsigned orientation=0;orientation<2;++orientation)
                        activation[orientation]+=std::int64_t(std::clamp(sums[unsigned(side)^p^orientation][k],0,int(quant_scale)))*weight;
                }
                auto own=std::clamp<std::int64_t>(activation[0]/quant_scale,0,quant_scale);
                auto enemy=std::clamp<std::int64_t>(activation[1]/quant_scale,0,quant_scale);
                value+=(own-enemy)*m.output[j];
            }
            return value;
        }
        for(unsigned j=0;j<m.hidden;++j)value+=(std::clamp(sums[unsigned(side)][j],0,int(quant_scale))
            -std::clamp(sums[1-unsigned(side)][j],0,int(quant_scale)))*std::int64_t(m.output[j]);
        return value;
    }
#if defined(__GNUC__) && defined(__x86_64__)
    __attribute__((target("sse4.1"))) std::int64_t vectorized(const Model& m,Color side) const {
        if(m.head) {
            alignas(16) std::array<std::array<std::int16_t,256>,2> input{};
            for(unsigned orientation=0;orientation<2;++orientation)for(unsigned p=0;p<2;++p)for(unsigned k=0;k<m.hidden;++k)
                input[orientation][p*m.hidden+k]=std::int16_t(std::clamp(sums[unsigned(side)^p^orientation][k],0,int(quant_scale)));
            std::int64_t value=0;
            for(unsigned j=0;j<m.head;++j) {
                __m128i total[2]{_mm_setzero_si128(),_mm_setzero_si128()};
                for(unsigned k=0;k<2*m.hidden;k+=8) {
                    auto weight=_mm_loadu_si128(reinterpret_cast<const __m128i*>(m.head_weights.data()+j*2*m.hidden+k));
                    for(unsigned o=0;o<2;++o) {
                        auto clipped=_mm_load_si128(reinterpret_cast<const __m128i*>(input[o].data()+k));
                        total[o]=_mm_add_epi32(total[o],_mm_madd_epi16(clipped,weight));
                    }
                }
                std::array<std::int64_t,2> activation{};
                for(unsigned o=0;o<2;++o) {
                    alignas(16) std::int32_t lanes[4];_mm_store_si128(reinterpret_cast<__m128i*>(lanes),total[o]);
                    std::int64_t sum=std::int64_t(m.head_bias[j])*quant_scale;
                    for(auto lane:lanes)sum+=lane;
                    activation[o]=std::clamp<std::int64_t>(sum/quant_scale,0,quant_scale);
                }
                value+=(activation[0]-activation[1])*m.output[j];
            }
            return value;
        }
        std::int64_t value=0;
        auto zero=_mm_setzero_si128(),ceiling=_mm_set1_epi32(quant_scale);
        for(unsigned j=0;j<m.hidden;j+=4) {
            auto own=_mm_loadu_si128(reinterpret_cast<const __m128i*>(sums[unsigned(side)].data()+j));
            auto enemy=_mm_loadu_si128(reinterpret_cast<const __m128i*>(sums[1-unsigned(side)].data()+j));
            own=_mm_min_epi32(_mm_max_epi32(own,zero),ceiling);
            enemy=_mm_min_epi32(_mm_max_epi32(enemy,zero),ceiling);
            auto weights=_mm_cvtepi16_epi32(_mm_loadl_epi64(reinterpret_cast<const __m128i*>(m.output.data()+j)));
            auto products=_mm_mullo_epi32(_mm_sub_epi32(own,enemy),weights);
            alignas(16) std::int32_t lanes[4];_mm_store_si128(reinterpret_cast<__m128i*>(lanes),products);
            for(auto lane:lanes)value+=lane;
        }
        return value;
    }
#endif
    int score(const Model& m,Color side) const {
        std::int64_t value;
#if defined(__GNUC__) && defined(__x86_64__)
        value=__builtin_cpu_supports("sse4.1")?vectorized(m,side):scalar(m,side);
#else
        value=scalar(m,side);
#endif
        return int(std::clamp<std::int64_t>(value*600/(quant_scale*quant_scale*(m.head?2:1)),-5000,5000));
    }
};
}
