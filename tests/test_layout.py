from pathlib import Path
import unittest

from jack_display.layout import (
    DEFAULT_CONFIG,
    Rect,
    deep_merge,
    dual_panes,
    load_config,
    reading_pane,
)


class LayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_area = Rect(0, 0, 1920, 1152)
        self.config = DEFAULT_CONFIG

    def test_comfort_dual_maximizes_horizontal_space(self) -> None:
        left, right = dual_panes(self.work_area, self.config["presets"]["comfort_dual"])

        self.assertEqual(left.as_tuple(), (0, 230, 960, 692))
        self.assertEqual(right.as_tuple(), (960, 230, 960, 692))
        self.assertEqual(right.x - left.right, 0)

    def test_reading_pane_is_centered(self) -> None:
        rect = reading_pane(self.work_area, self.config["presets"]["single_reading"])

        self.assertEqual(rect.as_tuple(), (384, 103, 1152, 945))

    def test_deep_merge_preserves_default_config_values(self) -> None:
        config = deep_merge(DEFAULT_CONFIG, {"overlay": {"alpha": 0.2}})

        self.assertEqual(config["overlay"]["alpha"], 0.2)
        self.assertEqual(config["overlay"]["step"], DEFAULT_CONFIG["overlay"]["step"])
        self.assertIn("comfort_dual", config["presets"])

    def test_repo_config_loads(self) -> None:
        config = load_config(Path("comfort_layout.json"))

        self.assertIn("overlay", config)


if __name__ == "__main__":
    unittest.main()
