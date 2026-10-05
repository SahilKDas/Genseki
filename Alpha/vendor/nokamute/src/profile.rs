use crate::{BasicEvaluator, Board, Rules};
use minimax::{Evaluator, Game, IterativeOptions, IterativeSearch, ParallelOptions, ParallelSearch, Strategy};
use std::hint::black_box;
use std::time::Instant;

/// Component timings preserve the production evaluator and move generator.
pub fn profile_position(game: &str, iterations: usize) {
    assert!(iterations > 0);
    let board = Board::from_game_string(game).expect("valid game string");
    let evaluator = BasicEvaluator::default();
    let start = Instant::now();
    for _ in 0..iterations { black_box(evaluator.evaluate(black_box(&board))); }
    println!("evaluation_ns {}", start.elapsed().as_nanos() / iterations as u128);
    let mut moves = Vec::new();
    let start = Instant::now();
    for _ in 0..iterations {
        moves.clear();
        Rules::generate_moves(black_box(&board), &mut moves);
        black_box(&moves);
    }
    println!("move_generation_ns {}", start.elapsed().as_nanos() / iterations as u128);
    println!("legal_moves {}", moves.len());
    let start = Instant::now();
    for _ in 0..iterations { black_box(board.clone()); }
    println!("board_clone_ns {}", start.elapsed().as_nanos() / iterations as u128);
    let start = Instant::now();
    for _ in 0..iterations { black_box(Rules::zobrist_hash(black_box(&board))); }
    println!("hash_ns {}", start.elapsed().as_nanos() / iterations as u128);
    let start = Instant::now();
    for _ in 0..iterations { black_box(board.find_cut_vertexes()); }
    println!("connectivity_ns {}", start.elapsed().as_nanos() / iterations as u128);
    if let Some(&m) = moves.first() {
        let mut mutable = board.clone();
        let original = Rules::zobrist_hash(&mutable);
        let start = Instant::now();
        for _ in 0..iterations { mutable.apply(m); mutable.undo(m); black_box(&mutable); }
        println!("make_unmake_ns {}", start.elapsed().as_nanos() / iterations as u128);
        assert_eq!(original, Rules::zobrist_hash(&mutable));
    }
    println!("evaluation {}", evaluator.evaluate(&board));
}

pub fn profile_search(game: &str, depth: u8, threads: usize, cutoff: u8) {
    assert!(depth > 0 && (1..=12).contains(&threads));
    let mut board = Board::from_game_string(game).expect("valid game string");
    let opts = IterativeOptions::new().with_countermoves().with_countermove_history()
        .with_table_byte_size(32 << 20);
    if threads == 1 {
        let mut search = IterativeSearch::new(BasicEvaluator::default(), opts);
        search.set_max_depth(depth);
        let start = Instant::now();
        let m = search.choose_move(&board);
        println!("search_us {}", start.elapsed().as_micros());
        println!("root_value {}", search.root_value());
        println!("bestmove {}", m.map(|m| board.to_move_string(m)).unwrap_or_default());
        println!("{}", search.stats(&mut board));
    } else {
        let parallel = ParallelOptions::new().with_num_threads(threads)
            .with_serial_cutoff_depth(cutoff);
        let mut search = ParallelSearch::new(BasicEvaluator::default(), opts.verbose(), parallel);
        search.set_max_depth(depth);
        let start = Instant::now();
        let m = search.choose_move(&board);
        println!("search_us {}", start.elapsed().as_micros());
        println!("bestmove {}", m.map(|m| board.to_move_string(m)).unwrap_or_default());
    }
}
