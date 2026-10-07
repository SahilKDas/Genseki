//! Nu-compatible integer inference. Search and noisy-move policy remain Gen 1's.
use crate::{board::*, bug::Bug, hex_grid::*, BasicEvaluator, Turn};
use minimax::{Evaluation, Evaluator};
use sha2::{Digest, Sha256};
use std::{
    cell::RefCell,
    collections::{BTreeMap, VecDeque},
    sync::Arc,
};

const DIR: [(i32, i32); 6] = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)];
fn mix(mut x: u64) -> u64 {
    x ^= x >> 30;
    x = x.wrapping_mul(0xbf58476d1ce4e5b9);
    x ^= x >> 27;
    x = x.wrapping_mul(0x94d049bb133111eb);
    x ^ (x >> 31)
}
fn kind(b: Bug) -> usize {
    match b {
        Bug::Queen => 0,
        Bug::Spider => 1,
        Bug::Beetle => 2,
        Bug::Grasshopper => 3,
        Bug::Ant => 4,
        _ => panic!("neural evaluator requires Base Hive"),
    }
}
fn slot(n: Node) -> usize {
    n.color() as usize * 11
        + [0, 1, 3, 5, 8][kind(n.bug())]
        + if n.bug() == Bug::Queen {
            0
        } else {
            n.bug_num() as usize - 1
        }
}
// Repetition remains identity-independent; neural TT values cannot be.
pub(crate) fn identity_hash(board: &Board) -> u64 {
    let token=|hex:Hex,node:Node,height:u8|mix((hex as u64)<<8 | slot(node) as u64 | (height as u64)<<24);
    let mut hash=mix(0x4e4e554552554c45);
    for &hex in board.occupied_hexes.iter().flatten() {
        hash^=token(hex,board.node(hex),board.height(hex));
    }
    for stone in board.get_underworld() {hash^=token(stone.hex(),stone.node(),stone.height());}
    hash
}
type Features = [Vec<usize>; 2];
pub(crate) const CACHE_RESERVE: usize = 13 * 256 * 1024;
const FEATURE_CACHE_BYTES: usize = 128 * 1024;

fn feature_key(b: &Board, schema: u32) -> Vec<u8> {
    let mut key = schema.to_le_bytes().to_vec();
    key.extend(b.nodes.iter().map(|n| n.bits()));
    key.extend(b.turn_num.to_le_bytes());
    key.push(b.game_type_bits);
    for reserve in b.remaining { key.extend(reserve); }
    for queen in b.queens { key.extend(queen.to_le_bytes()); }
    for hexes in &b.occupied_hexes {
        key.extend((hexes.len() as u32).to_le_bytes());
        for h in hexes { key.extend(h.to_le_bytes()); }
    }
    key.push(b.get_underworld().len() as u8);
    for stone in b.get_underworld() {
        key.extend(stone.hex().to_le_bytes());
        key.extend([stone.node().bits(), stone.height()]);
    }
    // Full replay disambiguates opening anchors and move-dependent mobility.
    for turn in &b.turn_history {
        match *turn {
            Turn::Place(h, bug) => { key.push(0); key.extend(h.to_le_bytes()); key.push(bug as u8); }
            Turn::Move(a, z) => { key.push(1); key.extend(a.to_le_bytes()); key.extend(z.to_le_bytes()); }
            Turn::Pass => key.push(2),
        }
    }
    key
}

#[derive(Default)]
struct FeatureCache { entries: VecDeque<(Vec<u8>, Features, usize)>, bytes: usize, hits: u64, misses: u64 }
impl FeatureCache {
    fn get(&mut self, b: &Board, schema: u32) -> Features {
        let key = feature_key(b, schema);
        if let Some(i) = self.entries.iter().position(|e| e.0 == key) {
            self.hits += 1;
            let entry = self.entries.remove(i).unwrap();
            let result = entry.1.clone(); self.entries.push_front(entry); return result;
        }
        self.misses += 1;
        let f = neural_features(b, schema);
        let bytes = key.capacity() + f.iter().map(|v| v.capacity() * std::mem::size_of::<usize>()).sum::<usize>() + 128;
        if bytes <= FEATURE_CACHE_BYTES {
            while self.bytes + bytes > FEATURE_CACHE_BYTES || self.entries.len() >= 32 {
                self.bytes -= self.entries.pop_back().unwrap().2;
            }
            self.bytes += bytes; self.entries.push_front((key, f.clone(), bytes));
        }
        f
    }
}
thread_local! {static FEATURE_CACHE:RefCell<FeatureCache>=RefCell::new(FeatureCache::default());}
pub(crate) fn feature_cache_metrics() -> [u64;4] {
    FEATURE_CACHE.with(|c| {let c=c.borrow(); [c.hits,c.misses,c.bytes as u64,c.entries.len() as u64]})
}

#[cfg(test)]
#[test]
fn exact_feature_cache_reference_and_budget() {
    use minimax::Game;
    let mut b=Board::new_core_set(); let mut cache=FeatureCache::default();
    for ply in 0..160 {
        assert_eq!(feature_impl(&b,4,true),feature_impl(&b,4,false));
        assert_eq!(cache.get(&b,4),neural_features(&b,4));
        assert_eq!(cache.get(&b,4),neural_features(&b,4));
        assert!(cache.bytes<=FEATURE_CACHE_BYTES && cache.entries.len()<=32);
        let mut moves=Vec::new(); crate::Rules::generate_moves(&b,&mut moves);
        if moves.is_empty() || crate::Rules::get_winner(&b).is_some() { break; }
        let m=moves[(ply*37+11)%moves.len()]; b.apply(m);
        assert_eq!(feature_impl(&b,4,true),feature_impl(&b,4,false));
        assert_eq!(cache.get(&b,4),neural_features(&b,4));
        b.undo(m); assert_eq!(cache.get(&b,4),neural_features(&b,4)); b.apply(m);
    }
    let mut changed=b.clone(); changed.turn_history.push(Turn::Pass);
    assert_ne!(feature_key(&b,4),feature_key(&changed,4));
    assert_ne!(feature_key(&b,3),feature_key(&b,4));
}

// Lift the occupied connected hive from the toroidal representation into axial coordinates.
// Before both queens exist, preserve the opening origin through move history.
fn cells(board: &Board) -> Vec<((i32, i32), Vec<Node>)> {
    let mut coords = BTreeMap::new();
    let mut opening_coords = BTreeMap::new();
    let mut levels = BTreeMap::<Hex, usize>::new();
    let steps = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)];
    // An absent queen anchors at the original origin in Nu. Recover that origin
    // from the legal replay even when its first stone has since moved away.
    if board.remaining.iter().any(|r| r[Bug::Queen as usize] > 0) {
        for turn in &board.turn_history {
            let dest = match *turn {
                Turn::Place(h, _) => h,
                Turn::Move(_, h) => h,
                Turn::Pass => continue,
            };
            if !opening_coords.contains_key(&dest) {
                let xy = adjacent(dest)
                    .into_iter()
                    .enumerate()
                    .find_map(|(d, h)| {
                        opening_coords
                            .get(&h)
                            .map(|&(q, r)| (q + steps[(d + 3) % 6].0, r + steps[(d + 3) % 6].1))
                    })
                    .unwrap_or((0, 0));
                opening_coords.insert(dest, xy);
            }
            if let Turn::Move(source, _) = *turn {
                let n = levels.get_mut(&source).unwrap();
                *n -= 1;
                if *n == 0 {
                    levels.remove(&source);
                    opening_coords.remove(&source);
                }
            }
            *levels.entry(dest).or_default() += 1;
        }
    }
    coords.insert(START_HEX, (0, 0));
    let mut todo = VecDeque::from([START_HEX]);
    // During early placement the origin is occupied; afterward queen anchors remove translation.
    if !board.occupied(START_HEX) {
        if let Some(h) = board.occupied_hexes.iter().flatten().next() {
            coords.clear();
            coords.insert(*h, opening_coords.get(h).copied().unwrap_or((0, 0)));
            todo = VecDeque::from([*h]);
        }
    }
    while let Some(h) = todo.pop_front() {
        let (q, r) = coords[&h];
        for (d, a) in adjacent(h).into_iter().enumerate() {
            if board.occupied(a) && !coords.contains_key(&a) {
                coords.insert(a, (q + steps[d].0, r + steps[d].1));
                todo.push_back(a);
            }
        }
    }
    let mut out = Vec::new();
    for (&h, &xy) in &coords {
        if !board.occupied(h) {
            continue;
        }
        let mut stack: Vec<Node> = board
            .get_underworld()
            .iter()
            .filter(|u| u.hex() == h)
            .map(|u| u.node())
            .collect();
        stack.push(board.node(h));
        out.push((xy, stack));
    }
    out.sort_by_key(|c| c.0);
    out
}

pub(crate) fn neural_features(b: &Board, version: u32) -> Features {
    feature_impl(b,version,true)
}
fn feature_impl(b: &Board, version: u32, fast: bool) -> Features {
    let stacks = cells(b);
    let mut anchors = [(0, 0); 2];
    let mut present = [false; 2];
    for (xy, s) in &stacks {
        for n in s {
            if n.bug() == Bug::Queen {
                anchors[n.color() as usize] = *xy;
                present[n.color() as usize] = true;
            }
        }
    }
    let height = |xy: (i32, i32)| stacks.iter().find(|s| s.0 == xy).map_or(0, |s| s.1.len());
    let mut articulation = vec![false; stacks.len()];
    let mut access = vec![0; stacks.len()];
    let cuts=if fast && version>=3 && stacks.len()>2 {Some(b.find_cut_vertexes())} else {None};
    let mut top_hex=[0;22];
    if cuts.is_some() {for &hex in b.occupied_hexes.iter().flatten() {top_hex[slot(b.node(hex))]=hex;}}
    if version >= 3 {
        for (i, (xy, s)) in stacks.iter().enumerate() {
            if s.len() == 1 && stacks.len() > 2 {
                if let Some(cuts)=&cuts {
                    articulation[i]=cuts.get(top_hex[slot(s[0])]);
                } else {
                let start = if i == 0 { 1 } else { 0 };
                let mut seen = vec![false; stacks.len()];
                seen[i] = true;
                seen[start] = true;
                let mut todo = vec![start];
                while let Some(v) = todo.pop() {
                    for j in 0..stacks.len() {
                        let dq = stacks[v].0 .0 - stacks[j].0 .0;
                        let dr = stacks[v].0 .1 - stacks[j].0 .1;
                        if !seen[j] && dq.abs().max(dr.abs()).max((dq + dr).abs()) == 1 {
                            seen[j] = true;
                            todo.push(j);
                        }
                    }
                }
                articulation[i] = seen.iter().any(|x| !*x);
                }
            }
            for d in 0..6 {
                let to = (xy.0 + DIR[d].0, xy.1 + DIR[d].1);
                if height(to) > 0 {
                    continue;
                }
                let flank = |k: usize| height((xy.0 + DIR[k].0, xy.1 + DIR[k].1));
                if flank((d + 5) % 6) >= s.len() && flank((d + 1) % 6) >= s.len() {
                    continue;
                }
                if DIR.iter().any(|&(q, r)| {
                    let a = (to.0 + q, to.1 + r);
                    !(a == *xy && s.len() == 1) && height(a) > 0
                }) {
                    access[i] += 1;
                }
            }
        }
    }
    let mut mobility = [0usize; 22];
    if version == 4 {
        for color in 0..2 {
            let mut board = b.clone();
            if board.to_move() as usize != color {
                board.turn_num += 1;
            }
            // The Base rules service computes movement for either color without last-move stuns.
            board.turn_history.clear();
            if board.remaining[color][Bug::Queen as usize] == 0 {
                let mut moves = Vec::new();
                board.generate_movements(&mut moves);
                for m in moves {
                    if let Turn::Move(h, _) = m {
                        mobility[slot(board.node(h))] += 1;
                    }
                }
            }
        }
    }
    let mut out: Features = [Vec::new(), Vec::new()];
    for p in 0..2 {
        for (i, (xy, s)) in stacks.iter().enumerate() {
            for (h, &n) in s.iter().enumerate() {
                let id = (slot(n) + 11 * p) % 22;
                let role = n.color() as usize ^ p;
                let bug = kind(n.bug());
                let top = h + 1 == s.len();
                let q = (xy.0 - anchors[p].0) as u32;
                let r = (xy.1 - anchors[p].1) as u32;
                let coordinates = mix(((q as u64) << 32) | r as u64);
                let v = coordinates
                    ^ mix(0x91e10da5c79e7b1du64
                        .wrapping_add((id + 32 * h + 1024 * usize::from(top)) as u64));
                out[p].push(
                    (mix(v)
                        % if version == 1 {
                            8192
                        } else if version == 2 {
                            4096
                        } else {
                            2048
                        }) as usize,
                );
                if version >= 2 {
                    out[p].push(
                        if version == 2 { 4096 } else { 2048 }
                            + (mix(coordinates
                                ^ mix((bug + 8 * role + 32 * h + 1024 * usize::from(top)) as u64))
                                % 2048) as usize,
                    );
                    if top {
                        let mut local = None;
                        let mut index = 0;
                        for dq in -2i32..=2 {
                            for dr in -2i32..=2 {
                                if dq.abs().max(dr.abs()).max((dq + dr).abs()) > 2 {
                                    continue;
                                }
                                if xy.0 - anchors[p].0 == dq && xy.1 - anchors[p].1 == dr {
                                    local = Some(index)
                                }
                                index += 1;
                            }
                        }
                        out[p].push(
                            if version == 2 { 6144 } else { 4096 }
                                + local.map_or(
                                    64 + (mix(coordinates ^ mix((role + 77) as u64)) % 1984)
                                        as usize,
                                    |l| role * 19 + l,
                                ),
                        );
                    }
                    if version >= 3 {
                        let covered = !top;
                        let flags = usize::from(present[n.color() as usize])
                            + 2 * usize::from(covered)
                            + 4 * usize::from(s.len() == 1 && articulation[i])
                            + 8 * usize::from(access[i] == 0);
                        out[p].push(6144 + role * 128 + bug * 16 + flags);
                        out[p].push(
                            6400 + role * 128 + bug * 16 + if covered { 7 } else { access[i] },
                        );
                        if version == 4 {
                            out[p].push(7000 + role * 128 + bug * 16 + mobility[slot(n)].min(15));
                            if n.bug() == Bug::Queen {
                                out[p].push(
                                    7400 + role * 16
                                        + usize::from(covered)
                                        + 2 * usize::from(s.last().unwrap().color() != n.color()),
                                );
                            }
                        }
                    }
                }
            }
        }
        if version >= 3 {
            for color in 0..2 {
                let liberties = if present[color] {
                    DIR.iter()
                        .filter(|&&(q, r)| {
                            height((anchors[color].0 + q, anchors[color].1 + r)) == 0
                        })
                        .count()
                } else {
                    7
                };
                out[p].push(6800 + (color ^ p) * 16 + liberties);
            }
        }
        out[p].sort_unstable();
    }
    out
}

pub struct NeuralModel {
    pub width: usize,
    pub schema: u32,
    pub hash: String,
    pub scale: f64,
    pub bytes: usize,
    bias: Vec<i32>,
    embedding: Vec<i16>,
    output: Vec<i16>,
    head_weights: Vec<i16>,
    head_bias: Vec<i32>,
}
impl NeuralModel {
    pub fn load(path: &str) -> Result<Arc<Self>, String> {
        let size = std::fs::metadata(path).map_err(|e| e.to_string())?.len();
        if !(32..=8 * 1024 * 1024).contains(&size) {
            return Err("invalid model size".into());
        }
        if std::fs::metadata(format!("{path}.alpha.json"))
            .map_err(|_| "trained provenance sidecar required")?
            .len()
            > 65536
        {
            return Err("provenance too large".into());
        }
        let bytes = std::fs::read(path).map_err(|e| e.to_string())?;
        if bytes.len() < 32 || bytes.len() > 8 * 1024 * 1024 {
            return Err("invalid model size".into());
        }
        let hash = format!("{:x}", Sha256::digest(&bytes));
        let manifest: serde_json::Value = serde_json::from_slice(
            &std::fs::read(format!("{path}.alpha.json"))
                .map_err(|_| "trained provenance sidecar required")?,
        )
        .map_err(|e| e.to_string())?;
        if manifest["trained"] != true || manifest["sha256"] != hash {
            return Err("unverified trained model".into());
        }
        let scale = manifest["score_scale"]
            .as_f64()
            .ok_or("score scale required")?;
        if !scale.is_finite() || scale <= 0. || scale > 100. {
            return Err("invalid score scale".into());
        }
        let u32at = |at: usize| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
        let schema = u32at(8);
        let width = u32at(16) as usize;
        let nonlinear = &bytes[..8] == b"NUNNUE2\0";
        if (!nonlinear && &bytes[..8] != b"NUNNUE1\0")
            || schema != 4
            || ![64, 128].contains(&width)
            || u32at(12) != 8192
            || u32at(20) != 256
        {
            return Err("unsupported model schema".into());
        }
        let size = 32
            + width * 4
            + 8192 * width * 2
            + if nonlinear {
                32 * 2 * width * 2 + 32 * 4 + 32 * 2
            } else {
                width * 2
            };
        if bytes.len() != size {
            return Err("model dimensions mismatch".into());
        }
        let checksum = bytes[32..].iter().fold(14695981039346656037u64, |h, &b| {
            (h ^ b as u64).wrapping_mul(1099511628211)
        });
        if checksum != u64::from_le_bytes(bytes[24..32].try_into().unwrap()) {
            return Err("model checksum mismatch".into());
        }
        let mut at = 32;
        let mut read32 = |n: usize| {
            let out = (0..n)
                .map(|_| {
                    let v = i32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
                    at += 4;
                    v
                })
                .collect::<Vec<_>>();
            out
        };
        let bias = read32(width);
        drop(read32);
        let mut read16 = |n: usize| {
            (0..n)
                .map(|_| {
                    let v = i16::from_le_bytes(bytes[at..at + 2].try_into().unwrap());
                    at += 2;
                    v
                })
                .collect::<Vec<_>>()
        };
        let embedding = read16(8192 * width);
        let head_weights = if nonlinear {
            read16(32 * 2 * width)
        } else {
            Vec::new()
        };
        drop(read16);
        let mut head_bias = Vec::new();
        if nonlinear {
            for _ in 0..32 {
                head_bias.push(i32::from_le_bytes(bytes[at..at + 4].try_into().unwrap()));
                at += 4;
            }
        }
        if bias
            .iter()
            .chain(&head_bias)
            .any(|&v| (v as i64).abs() > 1000000)
        {
            return Err("invalid bias".into());
        }
        let output = bytes[at..]
            .chunks_exact(2)
            .map(|b| i16::from_le_bytes(b.try_into().unwrap()))
            .collect();
        Ok(Arc::new(Self {
            width,
            schema,
            hash,
            scale,
            bytes: size,
            bias,
            embedding,
            output,
            head_weights,
            head_bias,
        }))
    }
    fn refresh(&self, f: &Features) -> [Vec<i32>; 2] {
        let mut sums = [self.bias.clone(), self.bias.clone()];
        for p in 0..2 {
            for &id in &f[p] {
                for k in 0..self.width {
                    sums[p][k] += self.embedding[id * self.width + k] as i32;
                }
            }
        }
        sums
    }
    fn output(&self, s: &[Vec<i32>; 2], side: usize) -> i32 {
        let clip = |p: usize, k: usize| s[p][k].clamp(0, 256) as i64;
        let mut value = 0i64;
        if self.head_bias.is_empty() {
            for k in 0..self.width {
                value += (clip(side, k) - clip(1 - side, k)) * self.output[k] as i64;
            }
        } else {
            for j in 0..32 {
                let mut a = [self.head_bias[j] as i64 * 256; 2];
                for p in 0..2 {
                    for k in 0..self.width {
                        for o in 0..2 {
                            a[o] += clip(side ^ p ^ o, k)
                                * self.head_weights[j * 2 * self.width + p * self.width + k] as i64;
                        }
                    }
                }
                value += ((a[0] / 256).clamp(0, 256) - (a[1] / 256).clamp(0, 256))
                    * self.output[j] as i64;
            }
        }
        (value * 600 / (256 * 256 * if self.head_bias.is_empty() { 1 } else { 2 }))
            .clamp(-5000, 5000) as i32
    }
    pub(crate) fn reference(&self, b: &Board) -> i32 {
        self.output(
            &self.refresh(&feature_impl(b, self.schema, false)),
            b.to_move() as usize,
        )
    }
    pub(crate) fn verify_accumulator(&self, b: &Board) -> bool {
        self.reference(b) == self.incremental(b)
    }
    pub(crate) fn costs(&self, b: &Board) -> [u128; 4] {
        use std::{hint::black_box, time::Instant};
        let f = neural_features(b, self.schema);
        let sums = self.refresh(&f);
        let mut ns = [0; 4];
        for phase in 0..4 {
            let start = Instant::now();
            for _ in 0..100 {
                match phase {
                    0 => {
                        black_box(neural_features(black_box(b), self.schema));
                    }
                    1 => {
                        black_box(self.reference(black_box(b)));
                    }
                    2 => {
                        black_box(self.incremental(black_box(b)));
                    }
                    _ => {
                        black_box(self.output(black_box(&sums), b.to_move() as usize));
                    }
                }
            }
            ns[phase] = start.elapsed().as_nanos() / 100;
        }
        ns
    }
    fn incremental(&self, b: &Board) -> i32 {
        let f = FEATURE_CACHE.with(|cache| cache.borrow_mut().get(b, self.schema));
        CACHE.with(|cache| {
            let mut c = cache.borrow_mut();
            if c.hash != self.hash {
                c.sums = self.refresh(&f);
                c.hash = self.hash.clone();
            } else {
                for p in 0..2 {
                    let (mut i, mut j) = (0, 0);
                    while i < c.features[p].len() || j < f[p].len() {
                        let (id, sign) = if j == f[p].len()
                            || (i < c.features[p].len() && c.features[p][i] < f[p][j])
                        {
                            let id = c.features[p][i];
                            i += 1;
                            (id, -1)
                        } else if i == c.features[p].len() || f[p][j] < c.features[p][i] {
                            let id = f[p][j];
                            j += 1;
                            (id, 1)
                        } else {
                            i += 1;
                            j += 1;
                            continue;
                        };
                        for k in 0..self.width {
                            c.sums[p][k] += sign * self.embedding[id * self.width + k] as i32;
                        }
                    }
                }
            }
            c.features = f;
            self.output(&c.sums, b.to_move() as usize)
        })
    }
}
#[derive(Default)]
struct Cache {
    hash: String,
    features: Features,
    sums: [Vec<i32>; 2],
}
thread_local! {static CACHE:RefCell<Cache>=RefCell::new(Cache::default());}
#[derive(Clone)]
pub struct SelectedEvaluator {
    pub basic: BasicEvaluator,
    pub model: Option<Arc<NeuralModel>>,
}
impl SelectedEvaluator {
    pub fn prepare_board(&self,board:&mut Board) {board.neural_hashing=self.model.is_some();}
}
impl Evaluator for SelectedEvaluator {
    type G = Rules;
    fn evaluate(&self, b: &Board) -> Evaluation {
        match &self.model {
            None => self.basic.evaluate(b),
            Some(m) => (m.incremental(b) as f64 * m.scale)
                .round()
                .clamp(-10000., 10000.) as i16,
        }
    }
    fn generate_noisy_moves(&self, b: &Board, moves: &mut Vec<Turn>) {
        self.basic.generate_noisy_moves(b, moves)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use minimax::{Game, IterativeOptions, IterativeSearch, Strategy};
    fn fixture_model() -> Arc<NeuralModel> {
        Arc::new(NeuralModel {
            width: 64,
            schema: 4,
            hash: "fixture".into(),
            scale: 1.,
            bytes: 1048992,
            bias: vec![30; 64],
            embedding: (0..8192 * 64).map(|i| (i % 17) as i16 - 8).collect(),
            output: vec![7; 64],
            head_weights: Vec::new(),
            head_bias: Vec::new(),
        })
    }
    #[test]
    fn covered_queen_forced_pass_undo_and_orientation() {
        let model = fixture_model();
        let mut board = Board::new_core_set();
        board.apply(Turn::Place(START_HEX, Bug::Queen));
        board.apply(Turn::Place(START_HEX, Bug::Beetle));
        board.apply(Turn::Pass);
        board.apply(Turn::Place(adjacent(START_HEX)[0], Bug::Queen));
        let mut moves = Vec::new();
        Rules::generate_moves(&board, &mut moves);
        assert_eq!(moves, vec![Turn::Pass]);
        assert_eq!(Rules::get_winner(&board), None);
        let original = board.game_log();
        let score = model.reference(&board);
        assert!(model.verify_accumulator(&board));
        board.apply(Turn::Pass);
        assert_eq!(model.reference(&board), -score);
        assert!(model.verify_accumulator(&board));
        board.undo(Turn::Pass);
        assert_eq!(original, board.game_log());
        assert!(model.verify_accumulator(&board));
        let eval = SelectedEvaluator {
            basic: BasicEvaluator::default(),
            model: Some(model),
        };
        let mut search =
            IterativeSearch::new(eval, IterativeOptions::new().with_table_byte_size(1 << 20));
        search.set_max_depth(1);
        assert_eq!(search.choose_move(&board), Some(Turn::Pass));
    }
    #[test]
    fn terminal_rules_override_neural_scores() {
        let mut board = Board::new_core_set();
        let neighbors = adjacent(START_HEX);
        for turn in [
            Turn::Place(START_HEX, Bug::Queen),
            Turn::Place(neighbors[0], Bug::Queen),
            Turn::Place(neighbors[1], Bug::Spider),
            Turn::Place(neighbors[2], Bug::Ant),
            Turn::Place(neighbors[3], Bug::Spider),
            Turn::Place(neighbors[4], Bug::Ant),
            Turn::Place(neighbors[5], Bug::Ant),
        ] {
            board.apply(turn);
        }
        assert!(Rules::get_winner(&board).is_some());
        let eval = SelectedEvaluator {
            basic: BasicEvaluator::default(),
            model: Some(fixture_model()),
        };
        assert!(eval.evaluate(&board).abs() <= 10000);
        let mut search =
            IterativeSearch::new(eval, IterativeOptions::new().with_table_byte_size(1 << 20));
        search.set_max_depth(2);
        assert_eq!(search.choose_move(&board), None);
    }
    #[test]
    fn gen1_interface_preserves_scores_and_noisy_moves() {
        let basic = BasicEvaluator::default();
        let selected = SelectedEvaluator { basic, model: None };
        let mut board = Board::new_core_set();
        for ply in 0..80 {
            assert_eq!(basic.evaluate(&board), selected.evaluate(&board));
            let mut a = Vec::new();
            let mut b = Vec::new();
            basic.generate_noisy_moves(&board, &mut a);
            selected.generate_noisy_moves(&board, &mut b);
            assert_eq!(a, b);
            let mut moves = Vec::new();
            Rules::generate_moves(&board, &mut moves);
            if moves.is_empty() || Rules::get_winner(&board).is_some() {
                break;
            }
            board.apply(moves[(ply * 17 + 3) % moves.len()]);
        }
        let opts = IterativeOptions::new().with_table_byte_size(1 << 20);
        let mut a = IterativeSearch::new(basic, opts);
        let mut b = IterativeSearch::new(selected, opts);
        a.set_max_depth(2);
        b.set_max_depth(2);
        a.choose_move(&board);
        b.choose_move(&board);
        assert_eq!(a.root_value(), b.root_value());
    }
    #[test]
    fn neural_tt_distinguishes_identical_stone_ids_and_restores_hash() {
        let neighbors=adjacent(START_HEX);
        let make=|swap:bool| {
            let mut board=Board::new_core_set();
            for turn in [Turn::Place(START_HEX,Bug::Queen),Turn::Place(neighbors[0],Bug::Queen),
                Turn::Place(neighbors[if swap {3}else{1}],Bug::Ant),Turn::Place(neighbors[2],Bug::Beetle),
                Turn::Place(neighbors[if swap {1}else{3}],Bug::Ant),Turn::Place(neighbors[4],Bug::Spider)] {board.apply(turn);}
            board
        };
        let mut a=make(false);let mut b=make(true);
        assert_eq!(Rules::zobrist_hash(&a),Rules::zobrist_hash(&b));
        assert_ne!(neural_features(&a,4),neural_features(&b,4));
        let eval=SelectedEvaluator{basic:BasicEvaluator::default(),model:Some(fixture_model())};
        eval.prepare_board(&mut a);eval.prepare_board(&mut b);
        assert_ne!(Rules::zobrist_hash(&a),Rules::zobrist_hash(&b));
        let original=Rules::zobrist_hash(&a);let turn=Turn::Move(neighbors[1],neighbors[5]);
        a.apply(turn);a.undo(turn);assert_eq!(original,Rules::zobrist_hash(&a));
        SelectedEvaluator{basic:BasicEvaluator::default(),model:None}.prepare_board(&mut a);
        assert_eq!(Rules::zobrist_hash(&a),Rules::zobrist_hash(&make(false)));
    }
    #[test]
    fn incremental_refresh_undo_and_workers() {
        for schema in 1..=4 {
            let width = 64;
            let model = Arc::new(NeuralModel {
                width,
                schema,
                hash: format!("test-{schema}"),
                scale: 1.,
                bytes: 1048992,
                bias: vec![30; width],
                embedding: (0..8192 * width).map(|i| (i % 17) as i16 - 8).collect(),
                output: vec![7; width],
                head_weights: Vec::new(),
                head_bias: Vec::new(),
            });
            let mut board = Board::new_core_set();
            for ply in 0..100 {
                assert!(model.verify_accumulator(&board));
                let mut moves = Vec::new();
                Rules::generate_moves(&board, &mut moves);
                if moves.is_empty() || Rules::get_winner(&board).is_some() {
                    break;
                }
                let m = moves[(ply * 23 + 5) % moves.len()];
                board.apply(m);
                assert!(model.verify_accumulator(&board));
                board.undo(m);
                assert!(model.verify_accumulator(&board));
                board.apply(m);
            }
            let workers: Vec<_> = (0..4)
                .map(|_| {
                    let m = model.clone();
                    let b = board.clone();
                    std::thread::spawn(move || assert!(m.verify_accumulator(&b)))
                })
                .collect();
            for worker in workers {
                worker.join().unwrap();
            }
        }
    }
}
