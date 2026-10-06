#![allow(dead_code)]
#[path = "../../../../.tmp/nu-nokamute/src/board.rs"] mod board;
#[path = "../../../../.tmp/nu-nokamute/src/bug.rs"] mod bug;
#[path = "../../../../.tmp/nu-nokamute/src/hex_grid.rs"] mod hex_grid;
#[path = "../../../../.tmp/nu-nokamute/src/eval.rs"] mod eval;
#[path = "../../../../.tmp/nu-nokamute/src/notation.rs"] mod notation;
pub use board::*;
pub use bug::*;
pub use hex_grid::*;
pub use notation::*;
use eval::BasicEvaluator;
use std::io::{self, BufRead, Write};
use minimax::{Evaluator, Strategy, IterativeSearch, IterativeOptions, Game};
use std::time::Duration;

fn main() {
    println!("id NuOfflineTeacher Nokamute-1.0.3\nok");
    io::stdout().flush().unwrap();
    for line in io::stdin().lock().lines() {
        let line = line.unwrap();
        if line == "exit" { break; }
        if let Some(arguments) = line.strip_prefix("search ") {
            if let Some((ms, game)) = arguments.split_once(' ') {
                let ms = ms.parse::<u64>().unwrap_or(0);
                if !(1..=250).contains(&ms) { println!("err milliseconds must be 1..250"); }
                else {
                    match Board::from_game_string(game) {
                        Ok(board) => {
                            let opts = IterativeOptions::new().with_countermoves().with_countermove_history().with_table_byte_size(16 << 20);
                            let mut search = IterativeSearch::new(BasicEvaluator::default(), opts);
                            search.set_depth_or_timeout(32, Duration::from_millis(ms));
                            if let Some(turn) = search.choose_move(&board) {
                                let sign = if board.to_move() == Color::White { 1 } else { -1 };
                                println!("score {}", search.root_value() as i32 * sign);
                                println!("move {}", board.to_move_string(turn));
                                println!("pv_length {}", search.principal_variation().len());
                            } else { println!("err terminal position"); }
                        }
                        Err(error) => println!("err {error:?}"),
                    }
                }
            } else { println!("err expected search milliseconds game"); }
        } else if let Some(game) = line.strip_prefix("inspect ") {
            match Board::from_game_string(game) {
                Ok(board) => {
                    println!("game {}", board.game_string());
                    let mut moves=Vec::new();Rules::generate_moves(&board,&mut moves);
                    println!("moves {}", moves.into_iter().map(|turn|board.to_move_string(turn)).collect::<Vec<_>>().join(";"));
                }
                Err(error) => println!("err {error:?}"),
            }
        } else if let Some(game) = line.strip_prefix("eval ") {
            match Board::from_game_string(game) {
                Ok(board) => {
                    let sign = if board.to_move() == Color::White { 1 } else { -1 };
                    println!("score {}", BasicEvaluator::default().evaluate(&board) as i32 * sign);
                }
                Err(error) => println!("err {error:?}"),
            }
        } else { println!("err expected eval"); }
        println!("ok");
        io::stdout().flush().unwrap();
    }
}
