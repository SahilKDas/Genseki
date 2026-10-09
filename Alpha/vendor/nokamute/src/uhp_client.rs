extern crate minimax;

use crate::notation::{Result, UhpError};
use crate::{Board, Color, Player, Turn};

use minimax::Winner;
use std::io::{BufRead, BufReader, Read, Write};
use std::ops::Drop;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::time::{Duration, Instant};

pub(crate) struct UhpClient {
    proc: Child,
    input: SyncSender<String>,
    output: Receiver<std::io::Result<String>>,
    failed: bool,
    board: Board,
    pub name: String,
    pub capabilities: String,
}

impl UhpClient {
    pub(crate) fn new(cmd_args: &[String]) -> Result<UhpClient> {
        if cmd_args.is_empty() {return Err(UhpError::EngineError("missing engine command".into()));}
        let mut proc = Command::new(&cmd_args[0])
            .args(&cmd_args[1..])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        let mut input = proc.stdin.take().unwrap();
        let mut output = BufReader::new(proc.stdout.take().unwrap());
        let (input_tx,input_rx)=mpsc::sync_channel::<String>(1);
        let (output_tx,output_rx)=mpsc::sync_channel(1);
        std::thread::spawn(move || {
            while let Ok(line)=input_rx.recv() {
                if input.write_all(line.as_bytes()).and_then(|_|input.flush()).is_err() {break;}
            }
        });
        std::thread::spawn(move || loop {
            let mut line=String::new();
            let result=match output.by_ref().take(65537).read_line(&mut line) {
                Ok(0)=>Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof,"engine exited before ok")),
                Ok(_) if line.len()>65536=>Err(std::io::Error::new(std::io::ErrorKind::InvalidData,"engine output limit exceeded")),
                Ok(_)=>Ok(line),
                Err(error)=>Err(error),
            };
            let stop=result.is_err();
            if output_tx.send(result).is_err() || stop {break;}
        });
        let mut client = UhpClient {
            proc,
            input: input_tx,
            output: output_rx,
            failed: false,
            board: Board::new_core_set(),
            name: String::new(),
            capabilities: String::new(),
        };
        let id = client.consume_output(Instant::now()+Duration::from_secs(30))?;
        client.name = id
            .first()
            .cloned()
            .unwrap_or_default()
            .strip_prefix("id ")
            .unwrap_or("somebot")
            .to_string();
        client.capabilities = id.get(1).cloned().unwrap_or_default();
        Ok(client)
    }

    pub fn capable_of_game_string(&self, game_string: &str) -> bool {
        let game_type = game_string.split(';').next().unwrap();
        if !game_type.starts_with("Base+") {
            return true;
        }
        game_type[5..].chars().all(|expansion| self.capabilities.contains(expansion))
    }

    fn consume_output(&mut self, deadline: Instant) -> Result<Vec<String>> {
        let mut out = Vec::new();
        let mut err = None;
        loop {
            let line = match self.output.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
                Ok(Ok(line))=>line,
                _=> {
                    self.failed=true;
                    let _=self.proc.kill();
                    return Err(UhpError::EngineError("engine transport failed or timed out".into()));
                }
            };
            if line.len()>65536 || out.len()>=256 {return Err(UhpError::EngineError("engine output limit exceeded".into()));}
            if line.trim() == "ok" {
                break;
            }
            out.push(line.trim().to_string());
            if line.starts_with("err") || line.starts_with("invalidmove") {
                err = Some(UhpError::EngineError(out.join("\n")));
            }
        }
        match err {
            Some(error) => Err(error),
            None => Ok(out),
        }
    }

    fn command(&mut self, command: &str) -> Result<Vec<String>> {
        let deadline=Instant::now()+Duration::from_secs(30);
        if self.failed {return Err(UhpError::EngineError("engine session invalidated".into()));}
        if command.len()>1048576 || command.contains(['\r','\n']) {return Err(UhpError::EngineError("invalid engine command".into()));}
        let mut line = command.to_owned();
        line.push('\n');
        if self.input.try_send(line).is_err() {
            self.failed=true;
            let _=self.proc.kill();
            return Err(UhpError::EngineError("engine writer unavailable".into()));
        }
        self.consume_output(deadline)
    }

    pub(crate) fn new_game(&mut self, game_type: &str) -> Result<String> {
        let mut command = "newgame ".to_owned();
        command.push_str(game_type);
        let output = self.command(&command)?.join("\n");
        self.board = Board::from_game_string(game_type)?;
        Ok(output)
    }

    pub(crate) fn raw_play(&mut self, move_string: &str) -> Result<String> {
        let command = format!("play {move_string}");
        let out = self.command(&command)?.join("\n");
        self.board.apply_untrusted(self.board.from_move_string(move_string)?)?;
        Ok(out)
    }

    pub(crate) fn apply(&mut self, m: Turn) -> Result<Option<Winner>> {
        let command = format!("play {}", self.board.to_move_string(m));
        let out = self.command(&command)?.join("\n");
        self.board.apply_untrusted(m)?;
        Ok(match out.split(';').nth(1).unwrap_or_default() {
            "Draw" => Some(Winner::Draw),
            "WhiteWins" => Some(if self.board.to_move() == Color::White {
                Winner::PlayerToMove
            } else {
                Winner::PlayerJustMoved
            }),
            "BlackWins" => Some(if self.board.to_move() == Color::Black {
                Winner::PlayerToMove
            } else {
                Winner::PlayerJustMoved
            }),
            _ => None,
        })
    }

    pub(crate) fn undo(&mut self, num_undo: usize) -> Result<()> {
        self.command(&format!("undo {num_undo}"))?;
        self.board.undo_count(num_undo)?;
        Ok(())
    }

    pub(crate) fn raw_generate_moves(&mut self) -> Result<String> {
        self.command("validmoves")?.into_iter().next().ok_or_else(||UhpError::EngineError("missing validmoves reply".into()))
    }

    // Ask the engine for the next possible moves.
    pub(crate) fn generate_moves(&mut self) -> Result<Vec<Turn>> {
        let mut moves = Vec::new();
        for move_string in self.raw_generate_moves()?.split(';') {
            moves.push(self.board.from_move_string(move_string)?);
        }
        Ok(moves)
    }

    pub(crate) fn game_log(&mut self) -> String {
        self.board.game_log()
    }

    pub(crate) fn best_move(&mut self, timeout: Duration) -> Result<Turn> {
        let move_string =
            self.command(&format!("bestmove seconds {:.9}",timeout.as_secs_f64()))?.pop()
                .ok_or_else(||UhpError::EngineError("missing bestmove reply".into()))?;
        self.board.from_move_string(&move_string)
    }

    pub(crate) fn best_move_depth(&mut self, depth: u8) -> Result<Turn> {
        let move_string = self.command(&format!("bestmove depth {depth}"))?.pop()
            .ok_or_else(||UhpError::EngineError("missing bestmove reply".into()))?;
        self.board.from_move_string(&move_string)
    }
}

impl Drop for UhpClient {
    fn drop(&mut self) {
        let _=self.proc.kill();
        let _=self.proc.wait();
    }
}

#[cfg(all(test, windows))]
mod transport_tests {
    use super::*;

    #[test]
    fn eof_and_stalled_response_are_bounded() {
        assert!(UhpClient::new(&["cmd.exe".into(),"/c".into(),"exit".into()]).is_err());
        let proc=Command::new("powershell.exe")
            .args(["-NoProfile","-Command","Start-Sleep -Seconds 60"])
            .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap();
        let (input,_input_rx)=mpsc::sync_channel(1);
        let (_output_tx,output)=mpsc::sync_channel(1);
        let mut client=UhpClient {proc,input,output,failed:false,board:Board::new_core_set(),name:String::new(),capabilities:String::new()};
        let start=Instant::now();
        assert!(client.consume_output(start+Duration::from_millis(10)).is_err());
        assert!(start.elapsed()<Duration::from_millis(250));
        assert!(client.command("info").is_err());
    }
}

pub(crate) struct UhpPlayer {
    client: UhpClient,
    timeout: Option<Duration>,
    depth: Option<u8>,
}

impl UhpPlayer {
    pub(crate) fn new(cmd: &str) -> Result<Self> {
        Ok(UhpPlayer { client: UhpClient::new(&[cmd.to_owned()])?, timeout: None, depth: None })
    }
}

impl Player for UhpPlayer {
    fn name(&self) -> String {
        self.client.name.clone()
    }

    fn new_game(&mut self, game_type: &str) {
        self.client.new_game(game_type).unwrap();
    }

    fn play_move(&mut self, m: Turn) {
        self.client.apply(m).unwrap();
    }

    fn undo_move(&mut self, _: Turn) {
        self.client.undo(1).unwrap();
    }

    fn generate_move(&mut self) -> Turn {
        if let Some(depth) = self.depth {
            self.client.best_move_depth(depth).unwrap()
        } else {
            self.client.best_move(self.timeout.unwrap_or_else(|| Duration::from_secs(5))).unwrap()
        }
    }

    fn set_max_depth(&mut self, depth: u8) {
        self.depth = Some(depth);
    }

    fn set_timeout(&mut self, time: Duration) {
        self.timeout = Some(time);
    }
}
