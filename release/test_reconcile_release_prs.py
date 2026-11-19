import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reconciler', Path(__file__).with_name('reconcile-release-prs.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
COMMIT = 'a' * 40
PARENT = 'b' * 40
POLICIES = ['.github/release-policy.json', '.github/graph-policy.json']
PENDING_PATH = '/issues/7/labels/autorelease%3A%20pending'


def pull(number=7, **changes):
    return {'number': number, 'merged_at': '2026-11-19T10:00:00Z', 'merge_commit_sha': COMMIT,
            'base': {'ref': 'main'}, **changes}


class FakeAPI:
    def __init__(self, issues=(7,), pulls=None, tags=None, delete_error=None):
        self.issues = list(issues)
        self.pulls = pulls if pulls is not None else {7: pull()}
        self.tags = tags if tags is not None else {'v1.0.0': COMMIT, 'graph-v0.2.0': COMMIT}
        self.delete_error = delete_error
        self.writes = []
        self.pages = []

    def request(self, method, path, data=None):
        if method == 'GET' and path.startswith('/issues?'):
            self.pages.append(path)
            page = int(path.rsplit('page=', 1)[1])
            start = (page - 1) * module.PAGE_SIZE
            return [{'number': n, 'pull_request': {}} for n in self.issues[start:start + module.PAGE_SIZE]]
        if method == 'GET' and path.startswith('/pulls/'):
            return self.pulls[int(path.rsplit('/', 1)[1])]
        if method == 'GET' and path.startswith('/git/ref/tags/'):
            tag = path.removeprefix('/git/ref/tags/')
            if tag not in self.tags:
                raise module.APIError(404)
            return {'object': {'type': 'commit', 'sha': self.tags[tag]}}
        self.writes.append((method, path, data))
        if method == 'DELETE' and self.delete_error:
            raise self.delete_error
        return []


def validation(releases, parents=None):
    parents = parents or f'{COMMIT} {PARENT}\n'
    calls = []

    def validate(before, after, path):
        calls.append((before, after, path))
        return releases.get(path, {'release': False})

    def git(*args):
        assert args == ('rev-list', '--parents', '-n', '1', COMMIT), args
        return parents
    return {'git': git, 'validate': validate}, calls


ROOT = {'.github/release-policy.json': {'release': True, 'tag': 'v1.0.0'}}
BOTH = {**ROOT, '.github/graph-policy.json': {'release': True, 'tag': 'graph-v0.2.0'}}


class ReconcileTests(unittest.TestCase):
    def run_reconcile(self, api, releases=BOTH, parents=None):
        patches, calls = validation(releases, parents)
        with patch.dict(module.VALIDATION, patches):
            return module.reconcile(api, POLICIES), calls

    def test_swaps_labels_after_every_expected_tag_exists(self):
        api = FakeAPI()
        done, calls = self.run_reconcile(api)
        self.assertEqual(done, [7])
        self.assertEqual(calls, [(PARENT, COMMIT, path) for path in POLICIES])
        self.assertEqual(api.writes, [('POST', '/issues/7/labels', {'labels': ['autorelease: tagged']}),
                                      ('DELETE', PENDING_PATH, None)])
        self.assertIn('labels=autorelease%3A%20pending', api.pages[0])

    def test_single_component_release_is_enough(self):
        api = FakeAPI()
        self.assertEqual(self.run_reconcile(api, ROOT)[0], [7])

    def test_nothing_pending_is_a_noop(self):
        api = FakeAPI(issues=())
        self.assertEqual(self.run_reconcile(api)[0], [])
        self.assertEqual(api.writes, [])

    def test_unmerged_and_other_branch_prs_are_ignored(self):
        for changes in ({'merged_at': None}, {'base': {'ref': 'develop'}}):
            with self.subTest(changes=changes):
                api = FakeAPI(pulls={7: pull(**changes)})
                self.assertEqual(self.run_reconcile(api)[0], [])
                self.assertEqual(api.writes, [])

    def test_missing_or_foreign_tag_fails_without_label_change(self):
        for tags in ({'v1.0.0': COMMIT}, {'v1.0.0': COMMIT, 'graph-v0.2.0': PARENT}):
            with self.subTest(tags=tags):
                api = FakeAPI(tags=tags)
                with self.assertRaisesRegex(ValueError, 'graph-v0.2.0'):
                    self.run_reconcile(api)
                self.assertEqual(api.writes, [])

    def test_no_release_intent_fails(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, 'no release intent'):
            self.run_reconcile(api, {})
        self.assertEqual(api.writes, [])

    def test_merge_commit_must_have_one_parent(self):
        for parents in (f'{COMMIT} {PARENT} {"c" * 40}\n', f'{COMMIT}\n'):
            with self.subTest(parents=parents), self.assertRaisesRegex(ValueError, 'single parent'):
                self.run_reconcile(FakeAPI(), parents=parents)
        with self.assertRaisesRegex(ValueError, 'no merge commit'):
            self.run_reconcile(FakeAPI(pulls={7: pull(merge_commit_sha=None)}))

    def test_validation_errors_propagate(self):
        patches, _ = validation(BOTH)
        patches['validate'] = lambda *args: (_ for _ in ()).throw(ValueError('mirror mismatch'))
        with patch.dict(module.VALIDATION, patches), self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            module.reconcile(FakeAPI(), POLICIES)

    def test_already_removed_label_is_tolerated_but_other_errors_fail(self):
        self.assertEqual(self.run_reconcile(FakeAPI(delete_error=module.APIError(404)))[0], [7])
        with self.assertRaises(module.APIError):
            self.run_reconcile(FakeAPI(delete_error=module.APIError(403)))

    def test_listing_at_the_page_cap_fails(self):
        api = FakeAPI(issues=range(1, module.PAGE_SIZE * module.MAX_PAGES + 1), pulls={})
        with self.assertRaisesRegex(ValueError, 'Too many'):
            module.pending_pull_requests(api)
        self.assertEqual(len(api.pages), module.MAX_PAGES)

    def test_listing_collects_every_page_and_skips_plain_issues(self):
        api = FakeAPI(issues=range(1, module.PAGE_SIZE + 6))
        self.assertEqual(module.pending_pull_requests(api), list(range(1, module.PAGE_SIZE + 6)))
        self.assertEqual(len(api.pages), 2)

    def test_failed_label_removal_keeps_the_tagged_label_and_is_retryable(self):
        api = FakeAPI(delete_error=module.APIError(500))
        with self.assertRaises(module.APIError):
            self.run_reconcile(api)
        self.assertEqual(api.writes[0], ('POST', '/issues/7/labels', {'labels': ['autorelease: tagged']}))
        self.assertEqual(self.run_reconcile(FakeAPI())[0], [7])

    def test_requires_a_policy(self):
        with self.assertRaises(ValueError):
            module.reconcile(FakeAPI(), [])


if __name__ == '__main__':
    unittest.main()
