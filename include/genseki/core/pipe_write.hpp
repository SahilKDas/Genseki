#pragma once
#ifdef _WIN32
#include <windows.h>
#include <algorithm>
#include <memory>
#include <stop_token>
#include <string>

namespace genseki {
// The writer owns its handle and payload even if cancellation is delayed.
inline bool bounded_pipe_write(HANDLE pipe, std::string payload, ULONGLONG deadline,
                               std::stop_token stop = {}) {
    struct Job {
        HANDLE pipe = nullptr;
        std::string payload;
        ~Job() { if (pipe) CloseHandle(pipe); }
    };
    if (stop.stop_requested() || GetTickCount64() >= deadline) return false;
    auto job = std::make_shared<Job>();
    job->payload = std::move(payload);
    if (!DuplicateHandle(GetCurrentProcess(), pipe, GetCurrentProcess(), &job->pipe,
                         0, FALSE, DUPLICATE_SAME_ACCESS)) return false;
    auto context = new std::shared_ptr<Job>(job);
    HANDLE thread = CreateThread(nullptr, 0, [](LPVOID context) -> DWORD {
        std::unique_ptr<std::shared_ptr<Job>> owned(static_cast<std::shared_ptr<Job>*>(context));
        const auto job = *owned;
        std::size_t offset = 0;
        while (offset < job->payload.size()) {
            DWORD written = 0;
            const auto chunk = static_cast<DWORD>(std::min<std::size_t>(job->payload.size()-offset, 65536));
            if (!WriteFile(job->pipe, job->payload.data()+offset, chunk, &written, nullptr) || !written) return 0;
            offset += written;
        }
        return 1;
    }, context, 0, nullptr);
    if (!thread) { delete context; return false; }
    bool completed = false;
    while (!stop.stop_requested() && GetTickCount64() < deadline) {
        if (WaitForSingleObject(thread, 1) == WAIT_OBJECT_0) { completed = true; break; }
    }
    DWORD result = 0;
    if (completed) GetExitCodeThread(thread, &result);
    else CancelSynchronousIo(thread);
    CloseHandle(thread);
    return completed && result == 1;
}
}
#endif
