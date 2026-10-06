#pragma once
#include <mmreg.h>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <memory>

class AudioPlayer {
    struct Voice {
        HWAVEOUT device=nullptr;
        WAVEHDR header{};
        std::vector<char> samples;
        bool prepared=false;
        ~Voice() {
            if(device) {
                waveOutReset(device);
                if(prepared)waveOutUnprepareHeader(device,&header,sizeof(header));
                waveOutClose(device);
            }
        }
    };
    std::mutex mutex_;
    std::condition_variable wake_;
    std::vector<unsigned> pending_;
    bool stopping_=false;
    std::uint64_t generation_=0;
    std::thread worker_;

    static std::unique_ptr<Voice> start_voice(unsigned resource_id) {
        auto instance=GetModuleHandleW(nullptr);
        auto resource=FindResourceW(instance,MAKEINTRESOURCEW(resource_id),L"WAVE");
        if(!resource)return {};
        auto size=std::size_t(SizeofResource(instance,resource));
        auto bytes=static_cast<const unsigned char*>(LockResource(LoadResource(instance,resource)));
        if(!bytes||size<12||std::memcmp(bytes,"RIFF",4)||std::memcmp(bytes+8,"WAVE",4))return {};
        auto u16=[&](std::size_t at){return WORD(bytes[at]|unsigned(bytes[at+1])<<8);};
        auto u32=[&](std::size_t at){return DWORD(bytes[at]|unsigned(bytes[at+1])<<8|unsigned(bytes[at+2])<<16|unsigned(bytes[at+3])<<24);};
        WAVEFORMATEX format{};const unsigned char* samples=nullptr;std::size_t length=0;
        for(std::size_t at=12;at+8<=size;) {
            std::size_t chunk=u32(at+4),data=at+8;
            if(chunk>size-data)return {};
            if(!std::memcmp(bytes+at,"fmt ",4)&&chunk>=16) {
                format.wFormatTag=u16(data);format.nChannels=u16(data+2);
                format.nSamplesPerSec=u32(data+4);format.nAvgBytesPerSec=u32(data+8);
                format.nBlockAlign=u16(data+12);format.wBitsPerSample=u16(data+14);
                if(format.wFormatTag==WAVE_FORMAT_EXTENSIBLE&&chunk>=40) {
                    const unsigned char pcm_guid[16]={1,0,0,0,0,0,16,0,128,0,0,170,0,56,155,113};
                    if(!std::memcmp(bytes+data+24,pcm_guid,16)&&u16(data+18)==format.wBitsPerSample)
                        format.wFormatTag=WAVE_FORMAT_PCM;
                }
            }else if(!std::memcmp(bytes+at,"data",4)){samples=bytes+data;length=chunk;}
            at=data+chunk+(chunk&1);
        }
        if(format.wFormatTag!=WAVE_FORMAT_PCM||!format.nChannels||!format.nBlockAlign||!samples||!length||length%format.nBlockAlign)return {};
        auto voice=std::make_unique<Voice>();
        voice->samples.assign(reinterpret_cast<const char*>(samples),reinterpret_cast<const char*>(samples+length));
        if(waveOutOpen(&voice->device,WAVE_MAPPER,&format,0,0,CALLBACK_NULL)!=MMSYSERR_NOERROR)return {};
        voice->header.lpData=voice->samples.data();voice->header.dwBufferLength=DWORD(length);
        if(waveOutPrepareHeader(voice->device,&voice->header,sizeof(voice->header))!=MMSYSERR_NOERROR)return {};
        voice->prepared=true;
        if(waveOutWrite(voice->device,&voice->header,sizeof(voice->header))!=MMSYSERR_NOERROR)return {};
        return voice;
    }
    void run() {
        std::vector<std::unique_ptr<Voice>> voices;
        std::uint64_t generation=0;
        for(;;) {
            std::unique_lock lock(mutex_);
            wake_.wait_for(lock,std::chrono::milliseconds(10),[&]{return stopping_||!pending_.empty()||generation!=generation_;});
            if(stopping_)break;
            if(generation!=generation_){voices.clear();generation=generation_;}
            std::erase_if(voices,[](const auto& voice){return (voice->header.dwFlags&WHDR_DONE)!=0;});
            // Keep the lock through submission so a mute cannot race a new voice.
            for(auto resource:pending_) {
                if(voices.size()>=8)break;
                if(auto voice=start_voice(resource))voices.push_back(std::move(voice));
            }
            pending_.clear();
        }
    }
public:
    AudioPlayer():worker_([this]{run();}){}
    ~AudioPlayer(){stop();}
    AudioPlayer(const AudioPlayer&)=delete;
    AudioPlayer& operator=(const AudioPlayer&)=delete;
    void play(unsigned resource) {
        std::lock_guard lock(mutex_);
        if(!stopping_&&pending_.size()<16)pending_.push_back(resource);
        wake_.notify_one();
    }
    void silence() {
        std::lock_guard lock(mutex_);pending_.clear();++generation_;wake_.notify_one();
    }
    void stop() {
        {std::lock_guard lock(mutex_);stopping_=true;pending_.clear();wake_.notify_one();}
        if(worker_.joinable())worker_.join();
    }
};
