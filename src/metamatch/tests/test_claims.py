"""
Regression tests for the clause level verifiers (agents/claims.py and the coach check). Every "must reject" case
is a hole the old regex verifiers let through; every "must accept" case is a correct paraphrase that a stricter
check must not break.
"""
import unittest

from metamatch.agents.coach import recommends_loser
from metamatch.agents.grounded import verify
from metamatch.engine.solvers import Verdict

# Great Tusk (the player's) is faster than Dragapult
FASTER = Verdict("speed", "yes", "Great Tusk (450 Speed) outspeeds Dragapult running its most common spread (421 Speed).",
                 ["Great Tusk Speed: 450.", "Dragapult Speed with its most common spread: 421."],
                 subject="Great Tusk", other="Dragapult")
# "Does Dragapult outspeed my Great Tusk?": the subject is the opponent, and it is faster
OPP_FASTER = Verdict("speed", "yes", "Dragapult running its most common spread (421 Speed) outspeeds Great Tusk (300 Speed).",
                     ["Great Tusk Speed: 300.", "Dragapult Speed with its most common spread: 421."],
                     subject="Dragapult", other="Great Tusk", subject_is_player=False)
NO_OHKO = Verdict("ko", "no", "Great Tusk's Headlong Rush does 40.2-47.5% to Toxapex, so it does not OHKO.",
                  ["Calc: guaranteed 3HKO."], subject="Great Tusk", other="Toxapex")
IMMUNE = Verdict("type", "immune", "Corviknight (Flying/Steel, Pressure) is immune to Ground attacks.",
                 ["Ground vs Flying: 0x.", "Ground vs Steel: 2x."])


class TestSpeedClaims(unittest.TestCase):
    def test_negated_and_reversed_claims_rejected(self):
        for text in ["Great Tusk can't outspeed Dragapult.", "Great Tusk cannot outspeed Dragapult.",
                     "Great Tusk won't outspeed Dragapult.", "Great Tusk is not faster than Dragapult.",
                     "Dragapult moves first.", "Great Tusk is outsped by Dragapult."]:
            self.assertIsNotNone(verify(text, FASTER), text)

    def test_correct_paraphrases_accepted(self):
        for text in ["Great Tusk is not slower than Dragapult.", "Great Tusk can't be outsped by Dragapult.",
                     "Dragapult can't outspeed Great Tusk.", "Great Tusk outspeeds Dragapult, so it moves first."]:
            self.assertIsNone(verify(text, FASTER), text)

    def test_opponent_subject_perspective(self):
        self.assertIsNone(verify("Dragapult outspeeds your Great Tusk.", OPP_FASTER))
        self.assertIsNone(verify("You are slower than Dragapult.", OPP_FASTER))
        self.assertIsNotNone(verify("Your Great Tusk outspeeds Dragapult.", OPP_FASTER))

    def test_slower_question_reads_inverted(self):
        slower = Verdict("speed", "yes", FASTER.statement.replace("450", "300").replace("outspeeds", "is slower than"),
                         ["Great Tusk Speed: 300.", "Dragapult Speed with its most common spread: 421."],
                         subject="Great Tusk", other="Dragapult", ask_slower=True)
        self.assertIsNone(verify("Great Tusk is slower than Dragapult.", slower))
        self.assertIsNotNone(verify("Great Tusk outspeeds Dragapult.", slower))


class TestKoClaims(unittest.TestCase):
    def test_ko_wordings_rejected(self):
        for text in ["Headlong Rush OHKOs Toxapex.", "Great Tusk one-shots Toxapex.",
                     "It knocks Toxapex out in a single hit.", "It is a guaranteed 2HKO."]:
            self.assertIsNotNone(verify(text, NO_OHKO), text)

    def test_correct_paraphrases_accepted(self):
        for text in ["Headlong Rush doesn't quite OHKO Toxapex.", "It is not enough to knock Toxapex out.",
                     "Toxapex survives the hit."]:
            self.assertIsNone(verify(text, NO_OHKO), text)


class TestTypeClaims(unittest.TestCase):
    def test_denial_of_the_wrong_answer_is_fine(self):
        self.assertIsNone(verify("Corviknight is not weak to Ground; it takes no damage.", IMMUNE))

    def test_denial_of_the_right_answer_rejected(self):
        self.assertIsNotNone(verify("Corviknight is not immune to Ground.", IMMUNE))


class TestCoachRecommendations(unittest.TestCase):
    losers, members = {"Gholdengo", "Dragapult"}, {"Gholdengo", "Dragapult", "Corviknight"}

    def test_caution_words_no_longer_bypass(self):
        for s in ["Gholdengo is your best answer to Kingambit and does not fear Sucker Punch.",
                  "Gholdengo handles Kingambit, so don't hesitate to switch it in.",
                  "Your best answer is Dragapult, not Corviknight."]:
            self.assertIsNotNone(recommends_loser(s, self.losers, self.members), s)

    def test_real_recommendations_accepted(self):
        for s in ["Use Corviknight over Dragapult against Kingambit.",
                  "Use Corviknight instead of Dragapult.",
                  "Kingambit is a strong threat to Dragapult, so lead with Corviknight."]:
            self.assertIsNone(recommends_loser(s, self.losers, self.members), s)


class TestSofterRecommendations(unittest.TestCase):
    """Oak's real answers to "How do I beat Raging Bolt?" when the engine had Corviknight losing (OHKO'd by
    Thunderbolt) and only Great Tusk winning."""
    losers, ohko = {"Corviknight", "Dragapult", "Gholdengo"}, {"Corviknight", "Dragapult"}
    members = losers | {"Great Tusk", "Kingambit"}

    def test_recommendations_spread_over_clauses_are_caught(self):
        for s in ["Corviknight, with its high defense and ability to set up Body Press, could be a good option to take on Raging Bolt.",
                  "Additionally, Corviknight's powerful Body Press can deal significant damage to Raging Bolt, making it a viable option.",
                  "Corviknight's slower speed actually works to your advantage, as it allows you to set up a Body Press.",
                  "Additionally, you may want to consider using Corviknight, who can provide a defensive anchor.",
                  "Corviknight's slower speed might allow it to survive Raging Bolt's initial Thunderbolt."]:
            self.assertEqual(recommends_loser(s, self.losers, self.members, self.ohko), "Corviknight", s)

    def test_honest_advice_still_passes(self):
        for s in ["I would recommend using Great Tusk with its powerful Headlong Rush move to take down Raging Bolt.",
                  "Great Tusk outspeeds and hits Raging Bolt hard, making it the best answer.",
                  "Corviknight is OHKO'd by Thunderbolt, so it's not a good option.",
                  "Corviknight can't take a hit from Raging Bolt, so bring Great Tusk instead.",
                  "Gholdengo can survive a hit from Raging Bolt, but it still loses the matchup.",
                  "Avoid Corviknight; it is a liability here.",
                  "Use Great Tusk rather than Corviknight."]:
            self.assertIsNone(recommends_loser(s, self.losers, self.members, self.ohko), s)


if __name__ == "__main__":
    unittest.main()
