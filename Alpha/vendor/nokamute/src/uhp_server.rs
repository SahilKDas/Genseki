extern crate minimax;

use crate::notation::{Result, UhpError};
use crate::*;

use std::io::Write;
#[cfg(not(target_arch = "wasm32"))]
use std::io::{stdin, stdout};
use std::time::Duration;

pub struct UhpServer<W: Write> {
    board: Option<Board>,
    pv_dirty: bool,
    config: PlayerConfig,
    engine: Option<Box<dyn Player + Send>>,
    output: W,
}

impl<W: Write> UhpServer<W> {
    pub fn new(config: PlayerConfig, output: W) -> Self {
        UhpServer { board: None, pv_dirty: true, config, engine: None, output }
    }

    pub fn swap_output(&mut self, mut output: W) -> W {
        std::mem::swap(&mut output, &mut self.output);
        output
    }

    fn info(&mut self) -> Result<()> {
        writeln!(self.output, "id {} {}", env!("CARGO_PKG_NAME"), nokamute_version())?;
        // Capabilities
        writeln!(self.output, "{}",if self.config.neural_enabled {""}else{"Mosquito;Ladybug;Pillbug"})?;
        Ok(())
    }

    fn reset_engine(&mut self) {
        // Drop the old strategy first: this joins/cancels its pondering workers
        // before constructing tables or exposing a different evaluator.
        self.engine.take();
        self.pv_dirty = true;
        if let Some(board) = &self.board {
            let mut engine = self.config.new_player();
            engine.new_game(&board.game_type());
            for &turn in &board.turn_history {
                engine.play_move(turn);
            }
            self.engine = Some(engine);
        }
    }

    fn new_game(&mut self, args: &str) -> Result<()> {
        self.pv_dirty = true;
        let args = if args.is_empty() { "Base" } else { args };
        let board=Board::from_game_string(args)?;
        if self.config.neural_enabled && board.game_type()!="Base" {return Err(UhpError::EngineError("neural mode supports Base only".into()));}
        self.board = Some(board);
        self.reset_engine();
        writeln!(self.output, "{}", self.board.as_mut().unwrap().game_string())?;
        Ok(())
    }

    fn valid_moves(&mut self) -> Result<()> {
        writeln!(
            self.output,
            "{}",
            self.board.as_ref().ok_or(UhpError::GameNotStarted)?.valid_moves()
        )?;
        Ok(())
    }

    fn play(&mut self, args: &str) -> Result<()> {
        self.pv_dirty = true;
        let board = self.board.as_mut().ok_or(UhpError::GameNotStarted)?;
        let m = board.from_move_string(args)?;
        board.apply_untrusted(m)?;
        self.engine.as_mut().unwrap().play_move(m);
        writeln!(self.output, "{}", board.game_string())?;
        Ok(())
    }

    fn best_move(&mut self, args: &str) -> Result<()> {
        self.pv_dirty = false;
        let board = self.board.as_ref().ok_or(UhpError::GameNotStarted)?;
        let arg_error = || UhpError::UnrecognizedCommand(args.to_string());
        if let Some(arg) = args.strip_prefix("depth ") {
            let depth = arg.parse::<u8>().map_err(|_| arg_error())?;
            if depth == 0 {
                return Err(UhpError::EngineError("depth must be positive".to_string()));
            }
            self.engine.as_mut().unwrap().set_max_depth(depth);
        } else if let Some(arg) = args.strip_prefix("time ") {
            let dur = parse_hhmmss(arg).ok_or_else(arg_error)?;
            self.engine.as_mut().unwrap().set_timeout(dur);
        } else if let Some(arg) = args.strip_prefix("seconds ") {
            // Unofficial command offering sub-second precision.
            let dur = parse_seconds(arg).ok_or_else(arg_error)?;
            self.engine.as_mut().unwrap().set_timeout(dur);
        } else if let Some(arg) = args.strip_prefix("depthorseconds ") {
            // Unofficial command stopping whichever comes first.
            let mut toks = arg.split(" ");
            let depth =
                toks.next().ok_or_else(arg_error)?.parse::<u8>().map_err(|_| arg_error())?;
            if depth == 0 {
                return Err(UhpError::EngineError("depth must be positive".to_string()));
            }
            let dur = parse_seconds(toks.next().ok_or_else(arg_error)?).ok_or_else(arg_error)?;
            if toks.next().is_some() {
                return Err(arg_error());
            }
            self.engine.as_mut().unwrap().set_depth_or_timeout(depth, dur);
        } else {
            return Err(arg_error());
        }
        let m = self.engine.as_mut().unwrap().generate_move();
        writeln!(self.output, "{}", board.to_move_string(m))?;
        Ok(())
    }

    fn pv(&mut self) -> Result<()> {
        let pv = self.engine.as_ref().ok_or(UhpError::GameNotStarted)?.principal_variation();
        let mut board = self.board.as_ref().unwrap().clone();
        if self.pv_dirty {
            return Err(UhpError::EngineError("Board changed since last engine move".into()));
        }
        for &m in &pv {
            writeln!(self.output, "{}", board.to_move_string(m))?;
            board.apply(m);
        }
        Ok(())
    }

    fn undo(&mut self, args: &str) -> Result<()> {
        self.pv_dirty = true;
        let board = self.board.as_mut().ok_or(UhpError::GameNotStarted)?;
        let num_undo = if args.is_empty() {
            1
        } else {
            args.parse::<usize>().map_err(|_| UhpError::UnrecognizedCommand(args.to_string()))?
        };
        if num_undo > board.turn_history.len() {
            return Err(UhpError::TooManyUndos);
        }
        for _ in 0..num_undo {
            self.engine.as_mut().unwrap().undo_move(board.last_move().unwrap());
            board.undo_count(1)?;
        }
        writeln!(self.output, "{}", board.game_string())?;
        Ok(())
    }

    fn get_option_int<Option: UhpOptionInt>(&mut self) -> Result<()> {
        writeln!(
            self.output,
            "{};int;{};{};{};{}",
            Option::name(),
            Option::current(&self.config)?,
            Option::current(&PlayerConfig::default())?,
            Option::min(),
            Option::max()
        )?;
        Ok(())
    }

    fn get_option_bool<Option: UhpOptionBool>(&mut self) -> Result<()> {
        fn fmt_bool(b: bool) -> &'static str {
            if b {
                "True"
            } else {
                "False"
            }
        }
        writeln!(
            self.output,
            "{};bool;{};{}",
            Option::name(),
            fmt_bool(Option::current(&self.config)?),
            fmt_bool(Option::current(&PlayerConfig::default())?)
        )?;
        Ok(())
    }

    fn set_option_int<Option: UhpOptionInt>(&mut self, arg: &str) -> Result<()> {
        let value = arg.parse::<usize>().map_err(|_| UhpError::InvalidOption(arg.into()))?;
        if value < Option::min() || value > Option::max() {
            return Err(UhpError::InvalidOption(arg.into()));
        }
        Option::set(value, &mut self.config);
        self.get_option_int::<Option>()
    }

    fn set_option_bool<Option: UhpOptionBool>(&mut self, arg: &str) -> Result<()> {
        let value = match arg {
            "True" => true,
            "False" => false,
            _ => return Err(UhpError::InvalidOption(arg.into())),
        };
        Option::set(value, &mut self.config);
        self.get_option_bool::<Option>()
    }

    fn get_option(&mut self, option: &str) -> Result<()> {
        match option {
            "Aggression" => self.get_option_int::<AggressionOption>(),
            #[cfg(not(target_arch = "wasm32"))]
            "BackgroundPondering" => self.get_option_bool::<BackgroundPonderingOption>(),
            #[cfg(not(target_arch = "wasm32"))]
            "NumThreads" => self.get_option_int::<NumThreadsOption>(),
            "RandomOpening" => self.get_option_bool::<RandomOpeningOption>(),
            "TableSizeMiB" => self.get_option_int::<TableSizeOption>(),
            "Verbose" => self.get_option_bool::<VerboseOption>(),
            "Evaluator" => {writeln!(self.output,"Evaluator;string;{};gen1;gen1;neural",if self.config.neural_enabled {"neural"}else{"gen1"})?;Ok(())},
            "ModelPath" => {writeln!(self.output,"ModelPath;string;{};",self.config.model_path)?;Ok(())},
            _ => Err(UhpError::InvalidOption(option.into())),
        }
    }

    fn options(&mut self, args: &str) -> Result<()> {
        if let Some(path)=args.strip_prefix("set ModelPath ") {
            let model=NeuralModel::load(path).map_err(UhpError::EngineError)?;
            if model.bytes+1024*1024+256*1024>self.config.opts.table_byte_size {return Err(UhpError::EngineError("memory budget too small for model".into()));}
            self.config.neural=Some(model);self.config.model_path=path.into();self.reset_engine();return self.get_option("ModelPath");
        }
        let tokens = args.split(' ').collect::<Vec<_>>();
        if args.is_empty() {
            self.get_option_int::<AggressionOption>()?;
            #[cfg(not(target_arch = "wasm32"))]
            self.get_option_bool::<BackgroundPonderingOption>()?;
            #[cfg(not(target_arch = "wasm32"))]
            self.get_option_int::<NumThreadsOption>()?;
            self.get_option_bool::<RandomOpeningOption>()?;
            self.get_option_int::<TableSizeOption>()?;
            self.get_option_bool::<VerboseOption>()?;
            self.get_option("Evaluator")?;self.get_option("ModelPath")?;
        } else if tokens.len() == 2 && tokens[0] == "get" {
            self.get_option(tokens[1])?;
        } else if tokens.len() == 3 && tokens[0] == "set" {
            match tokens[1] {
                "Evaluator" => {match tokens[2] {
                    "gen1"=>self.config.neural_enabled=false,
                    "neural"=>{if self.config.neural.is_none() {return Err(UhpError::EngineError("load trained ModelPath first".into()));}
                        if !matches!(self.config.strategy,PlayerStrategy::Iterative(_)) {return Err(UhpError::EngineError("neural mode requires iterative search".into()));}
                        if self.board.as_ref().is_some_and(|b|b.game_type()!="Base") {return Err(UhpError::EngineError("neural mode supports Base only".into()));}
                        if self.config.neural.as_ref().unwrap().bytes+1024*1024+256*1024>self.config.opts.table_byte_size {return Err(UhpError::EngineError("memory budget too small".into()));}
                        self.config.neural_enabled=true;},_=>return Err(UhpError::InvalidOption(args.into()))}self.get_option("Evaluator")?;},
                "Aggression" => self.set_option_int::<AggressionOption>(tokens[2])?,
                #[cfg(not(target_arch = "wasm32"))]
                "BackgroundPondering" => {
                    self.set_option_bool::<BackgroundPonderingOption>(tokens[2])?
                }
                #[cfg(not(target_arch = "wasm32"))]
                "NumThreads" => self.set_option_int::<NumThreadsOption>(tokens[2])?,
                "RandomOpening" => self.set_option_bool::<RandomOpeningOption>(tokens[2])?,
                "TableSizeMiB" => {let v=tokens[2].parse::<usize>().map_err(|_|UhpError::InvalidOption(args.into()))?;
                    if self.config.neural.as_ref().is_some_and(|m|v.saturating_mul(1<<20)<m.bytes+1024*1024+256*1024) {return Err(UhpError::EngineError("memory budget too small".into()));}
                    self.set_option_int::<TableSizeOption>(tokens[2])?;},
                "Verbose" => self.set_option_bool::<VerboseOption>(tokens[2])?,
                _ => return Err(UhpError::InvalidOption(args.into())),
            }
            self.reset_engine();
        } else {
            return Err(UhpError::UnrecognizedCommand(args.into()));
        }
        Ok(())
    }

    // Bonus undocumented command.
    fn perft(&mut self, args: &str) -> Result<()> {
        let depth = args.parse::<u8>().unwrap_or(20);
        let mut b = self.board.as_ref().ok_or(UhpError::GameNotStarted)?.clone();
        minimax::perft::<Rules>(&mut b, depth, false);
        Ok(())
    }

    pub fn command(&mut self, line: &str) -> bool {
        let line = line.trim();
        let space = line.find(' ');
        let command = if let Some(i) = space { &line[..i] } else { line };
        let args = if let Some(i) = space { &line[i + 1..] } else { "" };
        let result = match command {
            "info" => self.info(),
            "newgame" => self.new_game(args),
            "validmoves" => self.valid_moves(),
            "play" => self.play(args),
            "pass" => self.play("pass"),
            "bestmove" => self.best_move(args),
            "pv" => self.pv(),
            "undo" => self.undo(args),
            "options" => self.options(args),
            "alpha-eval" => {if let Some(b)=&self.board {use minimax::Evaluator;writeln!(self.output,"score {}",self.config.selected().evaluate(b)).map_err(UhpError::from)}else{Err(UhpError::GameNotStarted)}},
            "alpha-neural" => self.neural_diagnostics(),
            "alpha-neural-bench" => self.neural_benchmark(),
            "alpha-search" => self.teacher_search(args),
            "alpha-moveid" => {if let Some(b)=&self.board {match b.from_move_string(args) {Ok(m)=>writeln!(self.output,"{m:?}").map_err(UhpError::from),Err(e)=>Err(e)}}else{Err(UhpError::GameNotStarted)}},
            "perft" => self.perft(args),
            "exit" => return true,
            _ => Err(UhpError::UnrecognizedCommand(command.to_string())),
        };
        if let Err(err) = result {
            if let UhpError::InvalidMove(invalid) = err {
                writeln!(self.output, "invalidmove {invalid}").unwrap();
            } else {
                writeln!(self.output, "err {err:?}").unwrap();
            }
        }
        false
    }
}

impl<W:Write> UhpServer<W> {
    fn neural_benchmark(&mut self)->Result<()> {
        let b=self.board.as_ref().ok_or(UhpError::GameNotStarted)?;
        if b.game_type()!="Base" {return Err(UhpError::EngineError("Base only".into()))}
        let model=self.config.neural.as_ref().ok_or_else(||UhpError::EngineError("no model".into()))?;
        let ns=model.costs(b);
        writeln!(self.output,"feature_ns {} reconstruction_ns {} incremental_ns {} inference_ns {}",ns[0],ns[1],ns[2],ns[3])?;Ok(())
    }
    fn neural_diagnostics(&mut self)->Result<()> {
        let b=self.board.as_ref().ok_or(UhpError::GameNotStarted)?;
        let model=self.config.neural.as_ref().ok_or_else(||UhpError::EngineError("no model".into()))?;
        if b.game_type()!="Base" {return Err(UhpError::EngineError("Base only".into()))}
        if !model.verify_accumulator(b) {return Err(UhpError::EngineError("incremental accumulator mismatch".into()))}
        for (p,f) in crate::neural::neural_features(b,model.schema).iter().enumerate() {write!(self.output,"{p}:")?;for id in f {write!(self.output," {id}")?;}writeln!(self.output)?;}
        writeln!(self.output,"raw {}",model.reference(b))?;
        writeln!(self.output,"sha256 {} schema {} scale {} model_bytes {} tt_request_bytes {}",model.hash,model.schema,model.scale,model.bytes,self.config.search_options().table_byte_size)?;Ok(())
    }
    fn teacher_search(&mut self,args:&str)->Result<()> {
        use minimax::{Strategy,IterativeSearch,Evaluator};
        let tokens:Vec<_>=args.split_whitespace().collect();
        if tokens.is_empty() || tokens.len()>2 {return Err(UhpError::InvalidOption(args.into()))}
        let depth=tokens[0].parse::<u8>().map_err(|_|UhpError::InvalidOption(args.into()))?;
        let ms=if tokens.len()==2 {tokens[1].parse::<u64>().map_err(|_|UhpError::InvalidOption(args.into()))?}else{2000};
        if !(1..=2000).contains(&ms) {return Err(UhpError::InvalidOption(args.into()))}
        if !(1..=8).contains(&depth) {return Err(UhpError::InvalidOption(args.into()))}
        let mut prepared=self.board.as_ref().ok_or(UhpError::GameNotStarted)?.clone();
        self.config.selected().prepare_board(&mut prepared);
        let board=&prepared;
        let mut search=IterativeSearch::new(self.config.selected(),self.config.search_options());
        search.set_depth_or_timeout(depth,Duration::from_millis(ms));
        let m=search.choose_move(board).ok_or_else(||UhpError::EngineError("no move".into()))?;
        writeln!(self.output,"score {} static {} move {}",search.root_value(),self.config.selected().evaluate(board),board.to_move_string(m))?;
        writeln!(self.output,"{}",search.stats(&mut board.clone()))?;Ok(())
    }
}

#[cfg(not(target_arch = "wasm32"))]
pub fn uhp_serve(config: PlayerConfig) {
    let mut server = UhpServer::new(config, stdout());
    server.info().unwrap();
    println!("ok");
    loop {
        let mut line = String::new();
        match stdin().read_line(&mut line) {
            Ok(size) => {
                if size == 0 {
                    return;
                }
            }
            Err(err) => {
                eprintln!("{err}");
                return;
            }
        };
        if server.command(&line) {
            return;
        }
        println!("ok");
    }
}

trait UhpOptionInt {
    fn name() -> &'static str;
    fn current(config: &PlayerConfig) -> Result<usize>;
    fn min() -> usize;
    fn max() -> usize;
    // Caller does bounds checking.
    fn set(value: usize, config: &mut PlayerConfig);
}

#[cfg(not(target_arch = "wasm32"))]
struct NumThreadsOption {}
#[cfg(not(target_arch = "wasm32"))]
impl UhpOptionInt for NumThreadsOption {
    fn name() -> &'static str {
        "NumThreads"
    }
    fn current(config: &PlayerConfig) -> Result<usize> {
        Ok(if let Some(num_threads) = config.num_threads { num_threads } else { Self::max() })
    }
    fn min() -> usize {
        1
    }
    fn max() -> usize {
        minimax::ParallelOptions::default().num_threads()
    }
    fn set(value: usize, config: &mut PlayerConfig) {
        config.num_threads = Some(value)
    }
}

struct AggressionOption {}
impl UhpOptionInt for AggressionOption {
    fn name() -> &'static str {
        "Aggression"
    }
    fn current(config: &PlayerConfig) -> Result<usize> {
        Ok(config.eval.aggression().into())
    }
    fn min() -> usize {
        1
    }
    fn max() -> usize {
        5
    }
    fn set(value: usize, config: &mut PlayerConfig) {
        config.eval = BasicEvaluator::new(value as u8);
    }
}

struct TableSizeOption {}
impl UhpOptionInt for TableSizeOption {
    fn name() -> &'static str {
        "TableSizeMiB"
    }
    fn current(config: &PlayerConfig) -> Result<usize> {
        Ok(config.opts.table_byte_size >> 20)
    }
    fn min() -> usize {
        1
    }
    fn max() -> usize {
        256
    }
    fn set(value: usize, config: &mut PlayerConfig) {
        config.opts.table_byte_size = value << 20
    }
}

trait UhpOptionBool {
    fn name() -> &'static str;
    fn current(config: &PlayerConfig) -> Result<bool>;
    fn set(value: bool, config: &mut PlayerConfig);
}

struct VerboseOption {}
impl UhpOptionBool for VerboseOption {
    fn name() -> &'static str {
        "Verbose"
    }
    fn current(config: &PlayerConfig) -> Result<bool> {
        Ok(config.opts.verbose)
    }
    fn set(value: bool, config: &mut PlayerConfig) {
        config.opts.verbose = value;
    }
}

struct RandomOpeningOption {}
impl UhpOptionBool for RandomOpeningOption {
    fn name() -> &'static str {
        "RandomOpening"
    }
    fn current(config: &PlayerConfig) -> Result<bool> {
        Ok(config.random_opening)
    }
    fn set(value: bool, config: &mut PlayerConfig) {
        config.random_opening = value;
    }
}

#[cfg(not(target_arch = "wasm32"))]
struct BackgroundPonderingOption {}
#[cfg(not(target_arch = "wasm32"))]
impl UhpOptionBool for BackgroundPonderingOption {
    fn name() -> &'static str {
        "BackgroundPondering"
    }
    fn current(config: &PlayerConfig) -> Result<bool> {
        let parallel_opts = if let PlayerStrategy::Iterative(parallel_opts) = config.strategy {
            parallel_opts
        } else {
            return Err(UhpError::EngineError("Unexpected config".into()));
        };
        Ok(parallel_opts.background_pondering)
    }
    fn set(value: bool, config: &mut PlayerConfig) {
        if let PlayerStrategy::Iterative(ref mut parallel_opts) = config.strategy {
            parallel_opts.background_pondering = value;
        }
    }
}

// Parse hh:mm:ss as a duration.
fn parse_hhmmss(time: &str) -> Option<Duration> {
    let mut toks = time.split(':');
    let hours = toks.next().unwrap_or("").parse::<u64>().ok()?;
    let minutes = toks.next().unwrap_or("").parse::<u64>().ok()?;
    let seconds = parse_seconds(toks.next().unwrap_or(""))?;
    if toks.next().is_some() || minutes >= 60 || seconds >= Duration::from_secs(60) {
        return None;
    }
    let whole = hours.checked_mul(3600)?.checked_add(minutes.checked_mul(60)?)?;
    Duration::from_secs(whole).checked_add(seconds)
}

#[test]
fn test_parse_hhmmss() {
    assert_eq!(Some(Duration::from_secs(7)), parse_hhmmss("00:00:07"));
    assert_eq!(Some(Duration::from_secs(3661)), parse_hhmmss("01:01:01"));
    assert_eq!(Some(Duration::from_millis(230)), parse_hhmmss("00:00:00.230"));
    assert_eq!(None, parse_hhmmss("00:60:00"));
    assert_eq!(None, parse_hhmmss("00:00:60"));
    assert_eq!(None, parse_hhmmss("18446744073709551615:00:00"));
    assert_eq!(None, parse_hhmmss("45"));
    assert_eq!(None, parse_hhmmss("1:23"));
    assert_eq!(None, parse_hhmmss("01:02:03:04"));
    assert_eq!(None, parse_hhmmss("five"));
}

// Parse nnn[.nnn] as number of seconds.
fn parse_seconds(time: &str) -> Option<Duration> {
    let dot = time.find('.');
    let secs = time[..dot.unwrap_or(time.len())].parse::<u64>().ok()?;
    let mut dur = Duration::from_secs(secs);
    if let Some(i) = dot {
        let trailing = &time[i + 1..];
        let mut len = trailing.len();
        if len > 9 {
            return None;
        }
        let mut subsecs = trailing.parse::<u64>().ok()?;
        while len < 9 {
            len += 1;
            subsecs *= 10;
        }
        dur += Duration::from_nanos(subsecs);
    }
    Some(dur)
}

#[test]
fn test_parse_seconds() {
    assert_eq!(Some(Duration::from_millis(5)), parse_seconds("0.005"));
    assert_eq!(Some(Duration::from_mins(1)), parse_seconds("60"));
    assert_eq!(None, parse_seconds("01:23:45"));
    assert_eq!(None, parse_seconds("2e1"));
}

#[test]
fn test_pv_output_failure_preserves_board() {
    struct Output { fail: bool }
    impl std::io::Write for Output {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            if self.fail {
                Err(std::io::Error::new(std::io::ErrorKind::BrokenPipe, "test failure"))
            } else { Ok(bytes.len()) }
        }
        fn flush(&mut self) -> std::io::Result<()> { Ok(()) }
    }
    let mut server = UhpServer::new(PlayerConfig::default(), Output { fail: false });
    server.new_game("Base").unwrap();
    server.best_move("depth 1").unwrap();
    assert!(!server.engine.as_ref().unwrap().principal_variation().is_empty());
    let before = server.board.as_ref().unwrap().game_string();
    server.output.fail = true;
    assert!(server.pv().is_err());
    assert_eq!(before, server.board.as_ref().unwrap().game_string());
}
