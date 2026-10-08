//! Default-disabled, rules-proven Base Hive tactical advice.
use crate::{Board, Rules, Turn};
use minimax::{Game, Winner};
use std::time::{Duration, Instant};

const MAX_PROBES: usize = 4096;
const LOCAL_BUDGET: Duration = Duration::from_millis(2);

/// Reordering never removes a legal move. A unique defense requires a complete
/// legal reply enumeration for every child and no immediate winning alternative.
pub(crate) fn advise(
    board: &Board, moves: &mut [Turn], order: bool, stop: &dyn Fn() -> bool,
) -> bool {
    if board.game_type() != "Base" || Rules::get_winner(board).is_some() {
        return false;
    }
    let neighbors = board.queens_surrounded();
    if neighbors[board.to_move() as usize] < 4 && neighbors[board.to_move().other()] < 5 {
        return false;
    }
    classify(board, moves, order, stop, MAX_PROBES, LOCAL_BUDGET)
}

fn classify(
    board: &Board, moves: &mut [Turn], order: bool, stop: &dyn Fn() -> bool,
    max_probes: usize, budget: Duration,
) -> bool {
    let deadline = Instant::now() + budget;
    let mut probes = 0;
    let expired = |probes: usize| stop() || probes >= max_probes || Instant::now() >= deadline;
    let mut position = board.clone();
    let mut ranks = vec![1u8; moves.len()]; // Unknown remains distinct from a proven defense.
    let mut safe = 0;
    let mut losing = 0;
    let mut wins = 0;
    let mut complete = true;
    let mut replies = Vec::new();
    for (index, &m) in moves.iter().enumerate() {
        if expired(probes) { complete = false; break; }
        probes += 1;
        position.apply(m);
        match Rules::get_winner(&position) {
            Some(Winner::PlayerJustMoved) => { ranks[index] = 3; wins += 1; safe += 1; }
            Some(Winner::PlayerToMove) => { ranks[index] = 0; losing += 1; }
            Some(Winner::Draw) => { ranks[index] = 2; safe += 1; }
            None => {
                replies.clear();
                Rules::generate_moves(&position, &mut replies);
                let mut loss = false;
                let mut checked = true;
                for &reply in &replies {
                    if expired(probes) { checked = false; break; }
                    probes += 1;
                    position.apply(reply);
                    loss = Rules::get_winner(&position) == Some(Winner::PlayerJustMoved);
                    position.undo(reply);
                    if loss { break; }
                }
                if loss { ranks[index] = 0; losing += 1; }
                else if checked { ranks[index] = 2; safe += 1; }
                else { complete = false; }
            }
        }
        position.undo(m);
        if !complete { break; }
    }
    if order {
        let mut ranked: Vec<_> = moves.iter().copied().zip(ranks).collect();
        ranked.sort_by_key(|entry| std::cmp::Reverse(entry.1));
        for (m, (ordered, _)) in moves.iter_mut().zip(ranked) { *m = ordered; }
    }
    complete && wins == 0 && safe == 1 && losing + safe == moves.len() && losing > 0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn interruption_is_unknown_and_preserves_input() {
        let board = Board::new_core_set();
        let mut moves = Vec::new();
        Rules::generate_moves(&board, &mut moves);
        let original = moves.clone();
        let hash = Rules::zobrist_hash(&board);
        assert!(!classify(&board, &mut moves, true, &|| true, MAX_PROBES, LOCAL_BUDGET));
        assert_eq!(moves, original);
        assert_eq!(hash, Rules::zobrist_hash(&board));
        assert!(!classify(&board, &mut moves, true, &|| false, 0, LOCAL_BUDGET));
        assert_eq!(moves, original);
    }
    #[test]
    fn legal_game_advice_preserves_move_set_and_state() {
        let mut board = Board::new_core_set();
        for ply in 0..120 {
            if Rules::get_winner(&board).is_some() { break; }
            let mut moves = Vec::new();
            Rules::generate_moves(&board, &mut moves);
            let original = moves.clone();
            let hash = Rules::zobrist_hash(&board);
            let game = board.game_log();
            advise(&board, &mut moves, true, &|| false);
            assert_eq!(moves.len(), original.len());
            assert!(original.iter().all(|m| moves.contains(m)));
            assert_eq!(hash, Rules::zobrist_hash(&board));
            assert_eq!(game, board.game_log());
            board.apply(original[(ply * 37 + 11) % original.len()]);
        }
    }
}
