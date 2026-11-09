"""Guided tour (tour.py): the step table matches the app, and Back, Next, Skip and the first visit offer behave."""
import unittest
from unittest.mock import patch

from metamatch import tour
from metamatch.ui import DASHBOARD_TABS


class TestSteps(unittest.TestCase):
    def test_every_step_names_a_real_page_and_tab(self):
        for step in tour.STEPS:
            self.assertIn(step.page, ("home", "team"))
            self.assertTrue(step.target and step.title and step.text)
            if step.tab:
                self.assertIn(step.tab, DASHBOARD_TABS)

    def test_home_steps_come_first_so_the_tour_moves_forward(self):
        pages = [s.page for s in tour.STEPS]
        self.assertEqual(pages, sorted(pages, key=("home", "team").index))


class TestState(unittest.TestCase):
    def test_next_walks_every_step_then_ends(self):
        state = {}
        tour.start(state)
        seen = [tour.current(state)[0]]
        while tour.current(state):
            tour.next_step(state)
            if tour.current(state):
                seen.append(tour.current(state)[0])
        self.assertEqual(seen, list(range(len(tour.STEPS))))
        self.assertIsNone(state[tour.STEP_KEY])
        self.assertNotIn(tour.TAB_KEY, state)

    def test_tab_steps_leave_their_tab_for_the_team_page_once(self):
        state = {}
        tour.start(state)
        while tour.current(state) and not tour.current(state)[1].tab:
            tour.next_step(state)
        step = tour.current(state)[1]
        self.assertEqual(tour.pending_tab(state), step.tab)
        self.assertIsNone(tour.pending_tab(state))

    def test_back_stops_at_the_first_step_and_skip_clears_everything(self):
        state = {}
        tour.start(state)
        tour.back(state)
        self.assertEqual(tour.current(state)[0], 0)
        tour.next_step(state)
        tour.back(state)
        self.assertEqual(tour.current(state)[0], 0)
        tour.stop(state)
        self.assertIsNone(tour.current(state))
        tour.next_step(state)
        self.assertIsNone(tour.current(state))

    def test_the_offer_is_remembered_once_taken_or_dismissed(self):
        with patch.object(tour.config, "LOCAL_MODE", False):
            state = {}
            self.assertFalse(tour.seen(state))
            tour.mark_seen(state)
            self.assertTrue(tour.seen(state))
            fresh = {}
            tour.begin(fresh)
            self.assertTrue(tour.seen(fresh))
            self.assertEqual(tour.current(fresh)[0], 0)


if __name__ == "__main__":
    unittest.main()
