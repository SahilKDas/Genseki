#[cfg(not(target_arch = "wasm32"))]
use nokamute_core::*;
#[cfg(not(target_arch = "wasm32"))]
use std::ffi::OsString;

#[cfg(not(target_arch = "wasm32"))]
fn help() {
    println!(
        r#"nokamute hive engine {}

commands:
 profile [game_state]: Measure evaluation, move generation and board copies
 profile-search [game_state] [depth] [threads] [serial_cutoff]: Fixed-depth search timings
 cli:   Interactive interface to a board
 uhp:   Run as a Universal Hive Protocol engine
 play [--game-type=] [--depth=] [--timeout=] [player1] [player2]:
        Play a game, with each player being "human", "ai|nokamute",
        or a path to a UHP engine
 perft [--parallel] [game_state]:
        Count the number of board states at each depth
 uhp-debug [--search=game_state] engine_command
        Run external UHP engine through correctness testsuite,
        then randomly search for discrepancies with nokamute's move generator.

engine flags:
 --verbose
 --strategy=iterative|mcts|mtdf|random
 --table-mb=[int]
 --num-threads=[int]|all
 --serial-cutoff-depth=[int]
 --aspiration-window=[int]
 --double-step
 --quiet-search
 --null-move-pruning"#,
        nokamute_version()
    );
}

#[cfg(not(target_arch = "wasm32"))]
fn main() {
    let (config, args) = configure_player().unwrap();
    if config.is_neural() && matches!(args.first().map(String::as_str),Some("profile"|"profile-search"|"cli"|"uhp-debug")) {
        eprintln!("this auxiliary mode supports Gen 1 only; use neural UHP diagnostics instead");
        std::process::exit(2);
    }
    match args.first().unwrap_or(&"uhp".to_owned()).as_ref() {
        "profile-search" => {
            let game = args.get(1).map(String::as_str).unwrap_or("Base");
            let depth = args.get(2).map(|s| s.parse().expect("depth")).unwrap_or(4);
            let threads = args.get(3).map(|s| s.parse().expect("threads")).unwrap_or(1);
            let cutoff = args.get(4).map(|s| s.parse().expect("cutoff")).unwrap_or(1);
            profile_search(game, depth, threads, cutoff);
        }
        "profile" => {
            let game = args.get(1).map(String::as_str).unwrap_or("Base");
            profile_position(game, 10000);
        }
        "cli" => {
            terminal_game_interface(config);
        }
        "uhp" => {
            uhp_serve(config);
        }
        "play" => {
            let mut args = pico_args::Arguments::from_vec(
                args.iter().map(|s| s.into()).collect::<Vec<OsString>>(),
            );
            let game_type = args
                .opt_value_from_str("--game-type")
                .unwrap()
                .unwrap_or_else(|| "Base+MLP".to_owned());
            let depth: Option<u8> = args.opt_value_from_str("--depth").unwrap();
            let timeout: Option<String> = args.opt_value_from_str("--timeout").unwrap();
            let args =
                args.finish().into_iter().map(|s| s.into_string().unwrap()).collect::<Vec<_>>();

            let player1 = args.get(1).map(|s| s.as_ref()).unwrap_or("human");
            let player2 = args.get(2).map(|s| s.as_ref()).unwrap_or("ai");
            play_game(config, &game_type, player1, player2, depth, timeout);
        }
        "perft" => {
            let parallel = args.contains(&"--parallel".to_string());
            let mut args = args.clone();
            args.retain(|a| a != "--parallel");
            let game_type = args.get(1).map(|s| s.as_ref()).unwrap_or("Base");
            // Single threaded mode for engine performance comparisons.
            // Multi-threaded mode for getting values faster for correctness checking.
            perft(game_type, parallel);
        }
        "uhp-debug" => {
            let mut parsed_args = pico_args::Arguments::from_vec(
                args.iter().map(|s| s.into()).collect::<Vec<OsString>>(),
            );
            let search_string: Option<String> = parsed_args.opt_value_from_str("--search").unwrap();
            let args = parsed_args
                .finish()
                .into_iter()
                .map(|s| s.into_string().unwrap())
                .collect::<Vec<_>>();
            if args.len() < 2 {
                println!("uhp-debug requires engine command");
                return;
            }
            let success = uhp_tests(&args[1..]);
            if let Some(string) = search_string {
                perft_debug(&args[1..], &string, 20);
            }
            // Exit with test suite status code.
            std::process::exit(if success { 0 } else { 1 });
        }
        _ => {
            help();
        }
    }
}
