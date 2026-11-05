import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish_release', ROOT / 'release/github-release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TAG = 'v2.3.0'
COMMIT = 'a' * 40
RELEASE = {'tag_name': TAG, 'draft': False, 'prerelease': False, 'published_at': '2026-11-05'}


class FakeAPI:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class PublishReleaseTests(unittest.TestCase):
    def test_changelog(self):
        text = '## [Unreleased]\n\n- Next\n\n## [2.3.0] - 2026-11-04\n\n### Added\n- Feature\n\n## [2.2.0]\n- Old\n'
        self.assertEqual(module.release_notes(text, TAG), '### Added\n- Feature')
        for text in ('', '## [2.3.0]\n### Added\n', '## [2.3.0]\nA\n## [2.3.0]\nB'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                module.release_notes(text, TAG)
        with self.assertRaises(ValueError):
            module.release_notes('## [2.3.0]\nA', 'v2.3.0-rc.1')

    def test_create_then_retry_without_duplicate(self):
        api = FakeAPI([module.APIError(404), RELEASE])
        self.assertEqual(module.publish(api, TAG, COMMIT, 'Notes'), 'created')
        self.assertEqual(api.calls[1], ('POST', '/releases', {
            'tag_name': TAG, 'target_commitish': COMMIT, 'name': TAG, 'body': 'Notes',
            'draft': False, 'prerelease': False, 'make_latest': 'legacy',
        }))
        api = FakeAPI([RELEASE])
        self.assertEqual(module.publish(api, TAG, COMMIT, 'Notes'), 'existing')
        self.assertEqual(len(api.calls), 1)

    def test_api_errors_never_mean_absence(self):
        for error in (module.APIError(401), module.APIError(403), module.APIError(429), module.APIError(500), OSError('network')):
            api = FakeAPI([error])
            with self.subTest(error=error), self.assertRaises((ValueError, OSError)):
                module.publish(api, TAG, COMMIT, 'Notes')
            self.assertEqual(len(api.calls), 1)

    def test_reject_unpublished_or_wrong_release(self):
        for change in ({'tag_name': 'v2.4.0'}, {'draft': True}, {'prerelease': True}, {'published_at': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.publish(FakeAPI([{**RELEASE, **change}]), TAG, COMMIT, 'Notes')

    def test_race_requires_a_published_release_and_creation_errors_fail(self):
        api = FakeAPI([module.APIError(404), module.APIError(422), RELEASE])
        self.assertEqual(module.publish(api, TAG, COMMIT, 'Notes'), 'existing')
        for status in (403, 500):
            with self.subTest(status=status), self.assertRaises(module.APIError):
                module.publish(FakeAPI([module.APIError(404), module.APIError(status)]), TAG, COMMIT, 'Notes')
        with self.assertRaises(module.APIError):
            module.publish(FakeAPI([module.APIError(404), module.APIError(422), module.APIError(404)]), TAG, COMMIT, 'Notes')


if __name__ == '__main__':
    unittest.main()
