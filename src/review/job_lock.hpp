#pragma once
#include <filesystem>
#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace genseki::review {
// Integration contract v1: nonblocking byte-0 lock, never truncate/unlink.
class FileJobLock {
#ifdef _WIN32
    HANDLE handle_=INVALID_HANDLE_VALUE;
#else
    int handle_=-1;
#endif
public:
    FileJobLock()=default;
    FileJobLock(const FileJobLock&)=delete;
    FileJobLock& operator=(const FileJobLock&)=delete;
    ~FileJobLock(){release();}
    bool acquire(const std::filesystem::path& path) {
        std::error_code error;
        std::filesystem::create_directories(path.parent_path(),error);
        if(error)return false;
#ifdef _WIN32
        if(handle_!=INVALID_HANDLE_VALUE)return false;
        HANDLE handle=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,
            FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(handle==INVALID_HANDLE_VALUE)return false;
        LARGE_INTEGER size{};DWORD written=0;
        if(!GetFileSizeEx(handle,&size)||
            (size.QuadPart==0&&(!WriteFile(handle,"0",1,&written,nullptr)||written!=1))){CloseHandle(handle);return false;}
        OVERLAPPED overlap{};
        if(!LockFileEx(handle,LOCKFILE_EXCLUSIVE_LOCK|LOCKFILE_FAIL_IMMEDIATELY,0,1,0,&overlap)){CloseHandle(handle);return false;}
        handle_=handle;
#else
        if(handle_!=-1)return false;
        int handle=open(path.c_str(),O_CREAT|O_RDWR,0600);
        if(handle<0)return false;
        if(flock(handle,LOCK_EX|LOCK_NB)!=0){close(handle);return false;}
        handle_=handle;
#endif
        return true;
    }
    void release() {
#ifdef _WIN32
        if(handle_!=INVALID_HANDLE_VALUE){OVERLAPPED overlap{};UnlockFileEx(handle_,0,1,0,&overlap);CloseHandle(handle_);handle_=INVALID_HANDLE_VALUE;}
#else
        if(handle_!=-1){flock(handle_,LOCK_UN);close(handle_);handle_=-1;}
#endif
    }
};
}
