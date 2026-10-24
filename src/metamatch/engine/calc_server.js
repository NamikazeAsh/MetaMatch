// Damage calc sidecar: one JSON request per stdin line, one JSON response per stdout line.
// Request:  {"id": 1, "game": "sv" | "champions", "attacker": {...}, "defender": {...}, "move": "Earthquake", "field": {...}}
// Pokemon:  {"name", "level", "nature", "evs", "ivs", "item", "ability", "teraType", "boosts", "status", "curHP"}
//           In Champions "evs" holds stat points (0 to 32 per stat), which is what the calc expects for gen 0.
// Response: {"id", "ok": true, "range": [min, max], "percent": [min, max], "ko": "guaranteed 2HKO", "desc": "...",
//            "attacker_stats": {...}, "defender_stats": {...}} or {"id", "ok": false, "error": "..."}
const readline = require('readline');
const calc = require('@smogon/calc');

const GENS = {sv: calc.Generations.get(9), champions: calc.Generations.get(0)};

function makePokemon(gen, spec) {
  const {name, ...options} = spec;
  if (!gen.species.get(calc.toID(name))) throw new Error(`Unknown Pokemon: ${name}`);
  return new calc.Pokemon(gen, name, options);
}

function run(req) {
  const gen = GENS[req.game || 'sv'];
  if (!gen) throw new Error(`Unknown game: ${req.game}`);
  if (!gen.moves.get(calc.toID(req.move))) throw new Error(`Unknown move: ${req.move}`);
  const attacker = makePokemon(gen, req.attacker);
  const defender = makePokemon(gen, req.defender);
  const move = new calc.Move(gen, req.move, req.moveOptions || {});
  const field = new calc.Field(req.field || {});
  const result = calc.calculate(gen, attacker, defender, move, field);
  const [lo, hi] = result.range();
  const hp = defender.maxHP();
  let ko = '', desc = '';
  if (hi > 0) {
    ko = result.kochance().text;
    desc = result.desc();
  }
  return {
    range: [lo, hi],
    percent: [Math.floor(lo / hp * 1000) / 10, Math.floor(hi / hp * 1000) / 10],
    ko,
    desc,
    attacker_stats: attacker.stats,
    defender_stats: defender.stats,
  };
}

const rl = readline.createInterface({input: process.stdin});
rl.on('line', line => {
  let id = null;
  try {
    const req = JSON.parse(line);
    id = req.id;
    process.stdout.write(JSON.stringify({id, ok: true, ...run(req)}) + '\n');
  } catch (e) {
    process.stdout.write(JSON.stringify({id, ok: false, error: String(e.message || e)}) + '\n');
  }
});
