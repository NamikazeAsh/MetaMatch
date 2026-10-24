// Exports species, moves and items from the pinned @smogon/calc data to data/json/dex_<game>.json,
// so Python gets types, base stats, Mega formes and move data without hitting PokeAPI.
// Run: node src/metamatch/engine/export_dex.js
const fs = require('fs');
const path = require('path');
const calc = require('@smogon/calc');

const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'data', 'json');
const GAMES = {sv: 9, champions: 0};

for (const [game, num] of Object.entries(GAMES)) {
  const gen = calc.Generations.get(num);
  const dex = {species: {}, moves: {}, items: {}, abilities: [...gen.abilities].map(a => a.name)};
  for (const s of gen.species) {
    dex.species[s.name] = {
      types: s.types,
      baseStats: s.baseStats,
      abilities: Object.values(s.abilities || {}),
      ...(s.baseSpecies ? {baseSpecies: s.baseSpecies} : {}),
      ...(s.otherFormes ? {otherFormes: s.otherFormes} : {}),
    };
  }
  for (const m of gen.moves) {
    if (m.name === '(No Move)') continue;
    // Champions data leaves category off status moves
    dex.moves[m.name] = {type: m.type, category: m.category || 'Status', basePower: m.basePower || 0};
  }
  for (const i of gen.items) {
    dex.items[i.name] = i.megaStone ? {megaStone: i.megaStone} : {};
  }
  const file = path.join(OUT_DIR, `dex_${game}.json`);
  fs.writeFileSync(file, JSON.stringify(dex));
  console.log(`${file}: ${Object.keys(dex.species).length} species, ${Object.keys(dex.moves).length} moves, ${Object.keys(dex.items).length} items`);
}
