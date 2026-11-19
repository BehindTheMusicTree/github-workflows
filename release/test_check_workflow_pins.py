import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_pins', ROOT / 'release/check-workflow-pins.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
A, B = 'a' * 40, 'b' * 40
BASE = 'BehindTheMusicTree/github-workflows/.github/workflows/'


class CheckWorkflowPinsTests(unittest.TestCase):
    def run_check(self, files, expected=A):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in files.items():
                (Path(directory) / name).write_text(text, encoding='utf-8')
            module.check(Path(directory), expected)

    def test_same_commit_everywhere_passes(self):
        self.run_check({
            'release.yml': f'jobs:\n  a:\n    uses: {BASE}release-tag.yml@{A}\n  b:\n    uses: {BASE}release-please.yml@{A}\n',
            'publish.yml': f'jobs:\n  p:\n    uses: {BASE}release-github.yml@{A} # pinned\n',
        })

    def test_divergent_publisher_pin_fails(self):
        with self.assertRaisesRegex(ValueError, 'publish.yml: .github/workflows/release-github.yml@' + B):
            self.run_check({
                'release.yml': f'jobs:\n  a:\n    uses: {BASE}release-tag.yml@{A}\n',
                'publish.yml': f'jobs:\n  p:\n    uses: {BASE}release-github.yml@{B}\n',
            })

    def test_branch_or_tag_refs_fail(self):
        for ref in ('main', 'v5.3.0'):
            with self.assertRaises(ValueError):
                self.run_check({'release.yml': f'jobs:\n  a:\n    uses: {BASE}release-tag.yml@{ref}\n'})

    def test_other_actions_and_comments_are_ignored(self):
        self.run_check({'ci.yml': f'# uses: {BASE}release-tag.yml@{B}\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v5\n'})

    def test_composite_actions_and_other_workflows_are_ignored(self):
        self.run_check({'ci.yml': (
            'jobs:\n  a:\n    steps:\n'
            f'      - uses: BehindTheMusicTree/github-workflows/.github/actions/setup@v4.2.0\n'
            f'      - uses: BehindTheMusicTree/github-workflows/.github/actions/publish-python@{B}\n'
            f'  b:\n    uses: {BASE}release-tag.yml@{A}\n'
            f'  c:\n    uses: {BASE}call-redeployment-webhook.yml@v1\n')})

    def test_every_release_workflow_is_checked(self):
        for name in ('release-github', 'release-please', 'publish-python'):
            with self.assertRaises(ValueError):
                self.run_check({'r.yml': f'jobs:\n  a:\n    uses: {BASE}{name}.yml@{B}\n'})

    def test_similarly_named_files_are_ignored(self):
        self.run_check({'r.yml': f'jobs:\n  a:\n    uses: {BASE}release-tag.yml.bak@{B}\n  b:\n    uses: {BASE}my-release-tag.yml@{B}\n'})

    def test_owner_case_is_insensitive(self):
        with self.assertRaises(ValueError):
            self.run_check({'r.yml': f'jobs:\n  a:\n    uses: behindthemusictree/github-workflows/.github/workflows/release-tag.yml@{B}\n'})


if __name__ == '__main__':
    unittest.main()
