import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('validator', Path(__file__).with_name('validate-release.py'))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ReleaseValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.policy = {'release_branch': 'main', 'version': {'path': 'VERSION', 'format': 'text'},
                       'mirrors': [{'path': 'package.json', 'format': 'json', 'key': 'version'}],
                       'tag_prefix': 'v', 'changelog': 'CHANGELOG.md',
                       'outputs': {'github_release': True, 'packages': []}}
        self.write('policy.json', json.dumps(self.policy))
        self.write('VERSION', '1.0.0\n')
        self.write('package.json', '{"version":"1.0.0"}')
        self.write('CHANGELOG.md', '## [1.0.0] - 2026-01-01\n')
        self.before = self.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()

    def write(self, name, text):
        (self.root / name).write_text(text)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'test', '--allow-empty')
        sha = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', sha)
        return sha

    def check(self, after):
        import os
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            return validator.validate(self.before, after, 'policy.json')
        finally:
            os.chdir(previous)

    def test_no_bump_is_noop_even_without_tag(self):
        self.assertEqual(self.check(self.commit()), {'release': False})

    def test_bump_and_mirror(self):
        self.write('VERSION', '1.1.0\n')
        self.write('package.json', '{"version":"1.1.0"}')
        self.write('CHANGELOG.md', '## [1.1.0] - 2026-01-02\n')
        after = self.commit()
        self.assertEqual(self.check(after)['commit'], after)
        self.assertEqual(self.check(after)['tag'], 'v1.1.0')

    def test_mismatch_and_downgrade_fail(self):
        self.write('VERSION', '1.1.0\n')
        with self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            self.check(self.commit())
        self.write('VERSION', '0.9.0\n')
        with self.assertRaisesRegex(ValueError, 'must increase'):
            self.check(self.commit())

    def test_missing_changelog_and_invalid_version_fail(self):
        self.write('VERSION', '1.1.0\n')
        self.write('package.json', '{"version":"1.1.0"}')
        with self.assertRaisesRegex(ValueError, 'changelog'):
            self.check(self.commit())
        self.write('VERSION', '01.1.0\n')
        with self.assertRaisesRegex(ValueError, 'SemVer'):
            self.check(self.commit())


if __name__ == '__main__':
    unittest.main()
