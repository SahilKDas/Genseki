#pragma once
#include "genseki/review/review.hpp"
#include <memory>
namespace genseki::review {
class AlphaProcess {
public:
    AlphaProcess();
    ~AlphaProcess();
    [[nodiscard]] std::expected<void,std::string> start(const std::filesystem::path&,std::stop_token);
    [[nodiscard]] std::expected<SearchAnswer,std::string> search(const Board&,unsigned,std::stop_token);
    [[nodiscard]] unsigned process_id()const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
