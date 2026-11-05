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
        self.write('CHANGELOG.md', '## [1.0.0] - 2026-01-01\n\n- Initial.\n')
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

    def check(self, after, policy_path='policy.json'):
        import os
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            return validator.validate(self.before, after, policy_path)
        finally:
            os.chdir(previous)

    def test_no_bump_is_noop_even_without_tag(self):
        self.assertEqual(self.check(self.commit()), {'release': False})

    def test_bump_and_mirror(self):
        self.write('VERSION', '1.1.0\n')
        self.write('package.json', '{"version":"1.1.0"}')
        self.write('CHANGELOG.md', '## [1.1.0] - 2026-01-02\n\n- Feature.\n')
        after = self.commit()
        self.assertEqual(self.check(after)['commit'], after)
        self.assertEqual(self.check(after)['tag'], 'v1.1.0')

    def test_mismatch_and_downgrade_fail(self):
        self.write('VERSION', '1.1.0\n')
        with self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            self.check(self.commit())
        self.write('VERSION', '0.9.0\n')
        self.write('package.json', '{"version":"0.9.0"}')
        self.write('CHANGELOG.md', '## [0.9.0]\n- Downgrade.\n')
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

    def bump(self, version='1.1.0'):
        self.write('VERSION', version + '\n')
        self.write('package.json', json.dumps({'version': version}))
        self.write('CHANGELOG.md', f'## [{version}]\n\n- Change.\n')

    def test_activation_never_releases(self):
        self.git('rm', 'policy.json')
        self.before = self.commit()
        self.write('policy.json', json.dumps(self.policy))
        self.assertEqual(self.check(self.commit()), {'release': False})
        self.bump()
        self.assertEqual(self.check(self.commit()), {'release': False})

    def test_policy_change_requires_separate_push(self):
        self.policy['tag_prefix'] = 'release-'
        self.write('policy.json', json.dumps(self.policy))
        self.assertEqual(self.check(self.commit()), {'release': False})
        self.bump()
        with self.assertRaisesRegex(ValueError, 'separate pushes'):
            self.check(self.commit())

    def test_full_validation_without_bump(self):
        cases = [
            ('missing changelog', lambda: self.policy.update(changelog='missing.md')),
            ('unsafe path', lambda: self.policy.update(changelog='../CHANGELOG.md')),
            ('invalid mirror', lambda: self.policy.update(mirrors=[{'format': 'unknown', 'path': 'VERSION'}])),
            ('invalid key', lambda: self.policy['mirrors'][0].update(key='a..b')),
            ('duplicate source', lambda: self.policy.update(mirrors=[self.policy['version']])),
            ('invalid outputs', lambda: self.policy['outputs'].update(packages=['a', 'a'])),
            ('unknown field', lambda: self.policy.update(unknown=True)),
            ('invalid prefix', lambda: self.policy.update(tag_prefix='v/')),
        ]
        original = json.dumps(self.policy)
        for label, change in cases:
            with self.subTest(label=label):
                self.policy = json.loads(original)
                change()
                self.write('policy.json', json.dumps(self.policy))
                with self.assertRaises(ValueError):
                    self.check(self.commit())

    def test_no_bump_mirror_mismatch(self):
        self.write('package.json', '{"version":"1.0.1"}')
        with self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            self.check(self.commit())

    def test_empty_and_duplicate_changelog(self):
        for text in ('## [1.0.0]\n', '## [1.0.0]\n### Added\n<!-- nothing -->\n',
                     '## [1.0.0]\n- First.\n## [1.0.0]\n- Duplicate.\n'):
            with self.subTest(text=text):
                self.write('CHANGELOG.md', text)
                with self.assertRaisesRegex(ValueError, 'changelog'):
                    self.check(self.commit())

    def test_nonstable_versions(self):
        for version in ('1.1.0-rc.1', 'v1.1.0', '1.1.0+build', '1.01.0', '0.0', '  '):
            with self.subTest(version=version):
                self.write('VERSION', version)
                with self.assertRaisesRegex(ValueError, 'SemVer'):
                    self.check(self.commit())

    def test_invalid_shas_and_off_main(self):
        after = self.commit()
        for before in ('main', '0' * 40, after + '\n'):
            with self.subTest(before=before), self.assertRaises(ValueError):
                validator.validate(before, after, 'policy.json')
        self.git('update-ref', 'refs/remotes/origin/main', self.before)
        with self.assertRaises(ValueError):
            self.check(after)

    def test_event_sha_can_precede_main_tip(self):
        self.bump()
        event = self.commit()
        self.bump('1.2.0')
        later = self.commit()
        self.assertEqual(self.check(event)['commit'], event)
        self.before = event
        self.assertEqual(self.check(later)['commit'], later)

    def test_toml_source_and_dummy_root_manifest(self):
        self.write('project.toml', '[project]\nversion = "1.0.0"\n')
        self.policy['version'] = {'path': 'project.toml', 'format': 'toml', 'key': 'project.version'}
        self.policy['mirrors'] = []
        self.write('policy.json', json.dumps(self.policy))
        self.write('package.json', '{"version":"0.0.0"}')
        self.before = self.commit()
        self.write('project.toml', '[project]\nversion = "1.1.0"\n')
        self.write('CHANGELOG.md', '## [1.1.0]\n- Feature.\n')
        self.assertEqual(self.check(self.commit())['version'], '1.1.0')

    def test_two_coordinated_packages(self):
        self.policy['mirrors'].append({'path': 'second.json', 'format': 'json', 'key': 'version'})
        self.write('second.json', '{"version":"1.0.0"}')
        self.write('policy.json', json.dumps(self.policy))
        self.before = self.commit()
        self.bump()
        with self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            self.check(self.commit())
        self.write('second.json', '{"version":"1.1.0"}')
        self.assertTrue(self.check(self.commit())['release'])

    def test_missing_policy_fails(self):
        self.git('rm', 'policy.json')
        with self.assertRaises(ValueError):
            self.check(self.commit())

    def test_nested_policy_detected_on_previous_commit(self):
        (self.root / '.github').mkdir()
        self.git('mv', 'policy.json', '.github/release-policy.json')
        self.before = self.commit()
        self.bump()
        self.assertTrue(self.check(self.commit(), '.github/release-policy.json')['release'])

    def test_unrelated_before_fails(self):
        self.git('checkout', '-q', '--orphan', 'unrelated')
        self.write('unrelated.txt', 'different root')
        after = self.commit()
        with self.assertRaises(ValueError):
            self.check(after)


if __name__ == '__main__':
    unittest.main()
