// Damage calc sidecar: one JSON request per stdin line, one JSON response per stdout line.
// Request:  {"id": 1, "game": "sv" | "champions", "attacker": {...}, "defender": {...}, "move": "Earthquake", "field": {...}}
// Pokemon:  {"name", "level", "nature", "evs", "ivs", "item", "ability", "teraType", "boosts", "status", "curHP"}
//           In Champions "evs" holds stat points (0 to 32 per stat), which is what the calc expects for gen 0.
// Response: {"id", "ok": true, "range": [min, max], "percent": [min, max], "ko": "guaranteed 2HKO", "desc": "...",
//            "attacker_stats": {...}, "defender_stats": {...}, "defender_cur_hp"} or {"id", "ok": false, "error": "..."}
const readline = require('readline');
const calc = require('@smogon/calc');
const {getFinalSpeed, getQPBoostedStat} = require('@smogon/calc/dist/mechanics/util');

const GENS = {sv: calc.Generations.get(9), champions: calc.Generations.get(0)};

// Usage stats name some Pokemon by base species while the dex only has formes ("Aegislash" vs "Aegislash-Shield")
const formeCache = new Map();
function resolveSpecies(gen, name) {
  if (gen.species.get(calc.toID(name))) return name;
  const key = `${gen.num}:${name}`;
  if (!formeCache.has(key)) {
    // "-Both" is the calc's Stance Change forme (Blade when attacking, Shield when hit), so it wins when present
    let found = ["Both", "Shield"].map(f => `${name}-${f}`).find(n => gen.species.get(calc.toID(n))) || null;
    if (!found) {
      for (const s of gen.species) {
        if (s.name.startsWith(`${name}-`)) { found = s.name; break; }
      }
    }
    formeCache.set(key, found);
  }
  return formeCache.get(key);
}

// Spec extras on top of the calc's own options:
//   hpPercent: current HP as a percent of max ("at 50% HP")
//   qpActive:  Protosynthesis or Quark Drive active without sun, terrain or Booster Energy
// Without a boostedStat the calc never activates Protosynthesis or Quark Drive, even with Booster Energy,
// so 'auto' is the default: the boost then applies exactly when the item, weather or terrain triggers it.
function makePokemon(gen, spec) {
  const {name, hpPercent, qpActive, ...options} = spec;
  const resolved = resolveSpecies(gen, name);
  if (!resolved) throw new Error(`Unknown Pokemon: ${name}`);
  if (options.boostedStat === undefined) options.boostedStat = 'auto';
  const p = new calc.Pokemon(gen, resolved, options);
  if (qpActive && p.hasAbility('Protosynthesis', 'Quark Drive')) p.boostedStat = getQPBoostedStat(p, gen);
  if (hpPercent != null && hpPercent < 100) p.originalCurHP = Math.max(1, Math.floor(p.maxHP() * hpPercent / 100));
  return p;
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
    defender_cur_hp: defender.curHP(),
    attacker_speed: getFinalSpeed(gen, attacker, field, field.attackerSide),
    defender_speed: getFinalSpeed(gen, defender, field, field.defenderSide),
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
