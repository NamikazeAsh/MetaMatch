"""Replay Auditor: link parsing and the mistake and note rules, on small synthetic logs."""
import pytest

from metamatch import replay

HEADER = """|player|p1|Alice|
|player|p2|Bob|
|teamsize|p1|6
|teamsize|p2|6
|gametype|singles
|gen|9
|tier|[Gen 9] OU
|start
"""


def battle(body):
    return replay.analyze({"log": HEADER + body, "players": ["Alice", "Bob"], "formatid": "gen9ou",
                           "format": "[Gen 9] OU"})


def titles(analysis, side="p1"):
    return [(f.kind, f.title) for f in analysis.flags[side]]


@pytest.mark.parametrize("link, expected", [
    ("https://replay.pokemonshowdown.com/gen9ou-2704032656", ("gen9ou-2704032656", None)),
    ("https://replay.pokemonshowdown.com/gen9ou-2704032656?p2", ("gen9ou-2704032656", "p2")),
    ("replay.pokemonshowdown.com/smogtours-gen9ou-984081.log", ("smogtours-gen9ou-984081", None)),
    ("gen9ou-2704032656-abc12pw", ("gen9ou-2704032656-abc12pw", None)),
    ("https://replay.pokemonshowdown.com/gen9ou-2704032656.json", ("gen9ou-2704032656", None)),
])
def test_parse_replay_link(link, expected):
    assert replay.parse_replay_link(link) == expected


@pytest.mark.parametrize("link", ["", "https://youtube.com/watch", "gen9ou"])
def test_bad_links_raise(link):
    with pytest.raises(replay.ReplayError):
        replay.parse_replay_link(link)


def test_immune_target_is_a_mistake():
    a = battle("""|switch|p1a: Chomp|Garchomp, M|100/100
|switch|p2a: Corv|Corviknight, M|100/100
|turn|1
|move|p1a: Chomp|Earthquake|p2a: Corv
|-immune|p2a: Corv
|turn|2
""")
    assert ("mistake", "Earthquake into an immune target") in titles(a)


def test_tera_that_turn_is_only_a_note():
    a = battle("""|switch|p1a: Pult|Dragapult, M|100/100
|switch|p2a: Chomp|Garchomp, M|100/100
|turn|1
|-terastallize|p2a: Chomp|Fairy
|move|p1a: Pult|Draco Meteor|p2a: Chomp
|-immune|p2a: Chomp
|turn|2
""")
    flags = a.flags["p1"]
    assert [(f.kind, f.title) for f in flags] == [("note", "Draco Meteor into an immune target")]
    assert "Terastallized into Fairy" in flags[0].detail


def test_target_that_switched_in_is_not_flagged():
    a = battle("""|switch|p1a: Chomp|Garchomp, M|100/100
|switch|p2a: Tusk|Great Tusk|100/100
|turn|1
|switch|p2a: Corv|Corviknight, M|100/100
|move|p1a: Chomp|Earthquake|p2a: Corv
|-immune|p2a: Corv
|turn|2
""")
    assert not any("immune" in t for _, t in titles(a))


def test_known_magic_bounce_is_a_mistake():
    a = battle("""|switch|p1a: Ting|Ting-Lu|100/100
|switch|p2a: Hatt|Hatterene, F|100/100
|turn|1
|move|p1a: Ting|Stealth Rock|p2a: Hatt
|move|p2a: Hatt|Stealth Rock|p1a: Ting|[from] ability: Magic Bounce
|-sidestart|p1: Alice|move: Stealth Rock
|turn|2
|move|p1a: Ting|Spikes|p2a: Hatt
|move|p2a: Hatt|Spikes|p1a: Ting|[from] ability: Magic Bounce
|-sidestart|p1: Alice|Spikes
|turn|3
""")
    assert titles(a) == [("mistake", "Spikes bounced back"), ("note", "Stealth Rock bounced back")]


def test_setup_sweep():
    a = battle("""|switch|p1a: A|Clefable, F|100/100
|switch|p2a: Gambit|Kingambit, M|100/100
|turn|1
|move|p2a: Gambit|Swords Dance|p2a: Gambit
|-boost|p2a: Gambit|atk|2
|move|p1a: A|Moonblast|p2a: Gambit
|-damage|p2a: Gambit|60/100
|turn|2
|move|p2a: Gambit|Iron Head|p1a: A
|-damage|p1a: A|0 fnt
|faint|p1a: A
|switch|p1a: B|Dragapult, M|100/100
|turn|3
|move|p2a: Gambit|Sucker Punch|p1a: B
|-damage|p1a: B|0 fnt
|faint|p1a: B
|switch|p1a: C|Great Tusk|100/100
|turn|4
""")
    flags = a.flags["p1"]
    assert ("mistake", "Let Kingambit set up") in [(f.kind, f.title) for f in flags]
    assert "Clefable, Dragapult" in next(f.detail for f in flags if f.title == "Let Kingambit set up")
    assert a.battle.remaining("p1") == 4


def test_tie():
    a = battle("""|switch|p1a: A|Clefable, F|100/100
|switch|p2a: B|Clefable, F|100/100
|turn|1
|tie
""")
    assert a.battle.winner == "tie"
