// Answer key bridge for the frozen MetaBench fresh set. Calls the raw @smogon/calc package directly,
// independent of MetaMatch's engine/calc.py and calc_server.js.
// Usage: node bench/fresh_calc.js < requests.json > responses.json
// Input:  JSON array of {game: "sv" | "champions", attacker, defender, move, field}
//         Pokemon: {name, nature, evs, ivs, item, ability, teraType}. Champions "evs" are stat points.
// Output: JSON array of {ok, range: [min, max], rolls: [...16], maxHP, attacker_stats, defender_stats} or {ok: false, error}
const path = require('path');
const fs = require('fs');
const calc = require(path.join(__dirname, '..', 'src', 'metamatch', 'engine', 'node_modules', '@smogon', 'calc'));

const GENS = {sv: calc.Generations.get(9), champions: calc.Generations.get(0)};

function mon(gen, spec) {
  const {name, ...options} = spec;
  if (!gen.species.get(calc.toID(name))) throw new Error(`Unknown Pokemon: ${name}`);
  // 'auto' lets Protosynthesis and Quark Drive switch on exactly when sun or Electric Terrain is stated,
  // as they do in game; without it the calc never activates them
  return new calc.Pokemon(gen, name, {boostedStat: 'auto', ...options});
}

function run(req) {
  const gen = GENS[req.game || 'sv'];
  if (!gen.moves.get(calc.toID(req.move))) throw new Error(`Unknown move: ${req.move}`);
  const attacker = mon(gen, req.attacker);
  const defender = mon(gen, req.defender);
  const move = new calc.Move(gen, req.move);
  const field = new calc.Field(req.field || {});
  const result = calc.calculate(gen, attacker, defender, move, field);
  let rolls = result.damage;
  if (typeof rolls === 'number') rolls = Array(16).fill(rolls);
  // Fixed multi hit moves return one roll array per hit; sum them roll by roll
  if (Array.isArray(rolls[0])) rolls = rolls[0].map((_, i) => rolls.reduce((s, r) => s + r[i], 0));
  return {
    ok: true,
    range: [Math.min(...rolls), Math.max(...rolls)],
    rolls,
    maxHP: defender.maxHP(),
    attacker_stats: attacker.stats,
    defender_stats: defender.stats,
    move_type: move.type,
    hits: move.hits,
  };
}

const reqs = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = reqs.map(r => {
  try { return run(r); } catch (e) { return {ok: false, error: String(e.message || e)}; }
});
process.stdout.write(JSON.stringify(out));
