import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch
import xml.etree.ElementTree as ET


spec = importlib.util.spec_from_file_location(
    "generate_pins", Path(__file__).with_name("generate-pins.py")
)
pins = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pins
spec.loader.exec_module(pins)


def card(owner, repo, stem=None, theme="light"):
    stem = stem or repo
    return (
        f'<a href="https://github.com/{owner}/{repo}#gh-{theme}-mode-only">'
        f'<img src="https://raw.githubusercontent.com/profile/profile/output/pins/{stem}-{theme}.svg">'
        '</a>'
    )


class PinInputTests(unittest.TestCase):
    def test_deduplicates_themes_and_preserves_readme_order(self):
        readme = (card("alice", "project", theme="dark") + card("alice", "project") +
                  card("team", "tools"))
        selected = pins.read_pins(readme)
        self.assertEqual([(p.owner, p.repo) for p in selected], [
            ("alice", "project"), ("team", "tools")
        ])

    def test_other_owners_can_share_a_repository_name_with_distinct_filenames(self):
        selected = pins.read_pins(card("alice", "project", "alice-project") +
                                  card("team", "project", "team-project"))
        self.assertEqual([(p.owner, p.repo, p.stem) for p in selected], [
            ("alice", "project", "alice-project"), ("team", "project", "team-project")
        ])

    def test_conflicting_filenames_and_theme_links_are_rejected(self):
        invalid = [
            card("alice", "project") + card("team", "project"),
            card("alice", "project") + card("alice", "project", "other", "dark"),
            card("alice", "project").replace("#gh-light-mode-only", "#gh-dark-mode-only"),
        ]
        for readme in invalid:
            with self.subTest(readme=readme), self.assertRaises(ValueError):
                pins.read_pins(readme)

    def test_unlinked_images_and_normal_repo_links_are_not_inputs(self):
        readme = '<img src="pins/example-light.svg"><a href="https://github.com/alice/project">project</a>'
        self.assertEqual(pins.read_pins(readme), [])

    def test_generation_handles_arbitrary_counts_and_removes_stale_cards(self):
        data = {
            "description": "A repository description.", "language": None, "color": None,
            "stars": "0", "forks": "0", "icons": {"repo": {"d": "M0 0", "fill-rule": "evenodd"}},
        }
        for count in (0, 1, 3, 6):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "dist" / "pins"
                output.mkdir(parents=True)
                (output / "stale-light.svg").write_text("old")
                (root / "README.md").write_text("".join(card("team", f"repo-{i}") for i in range(count)))
                with patch.object(pins, "ROOT", root), patch.object(pins, "OUTPUT", output), \
                        patch.object(pins, "fetch", return_value=data) as fetch:
                    pins.main()
                self.assertEqual(fetch.call_args_list, [call("team", f"repo-{i}") for i in range(count)])
                self.assertEqual(len(list(output.glob("*.svg"))), count * 2)
                self.assertFalse((output / "stale-light.svg").exists())
                for svg in output.glob("*.svg"):
                    ET.parse(svg)


if __name__ == "__main__":
    unittest.main()
