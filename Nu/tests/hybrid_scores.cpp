#include "search.hpp"
#include <fstream>
#include <iostream>

int main(int argc,char** argv)try {
    if(argc!=3)throw std::runtime_error("model and G1 positions required");
    nu::Model model;model.load(argv[1]);std::ifstream input(argv[2]);std::string line;
    if(!input)throw std::runtime_error("missing positions");
    while(std::getline(input,line)) {
        auto board=nu::Board::from_position_string(line);if(!board)throw std::runtime_error(board.error());
        nu::State state(model,*board);
        std::cout<<state.evaluate()*(board->side_to_move()==nu::Color::white?1:-1)<<' '<<state.strategic_prior(nu::Color::white);
        for(unsigned i=0;i<6;++i)std::cout<<' '<<nu::handcrafted_white(*board,1u<<i);
        std::cout<<'\n';
    }
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
