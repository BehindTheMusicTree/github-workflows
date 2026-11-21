import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('armer', Path(__file__).with_name('arm-release-pr-auto-merge.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEAD = 'c' * 40
REPO = 'owner/repo'


def pull(number=7, **changes):
    return {'number': number, 'state': 'open', 'node_id': f'PR_{number}', 'title': 'chore: release main',
            'head': {'sha': HEAD, 'ref': 'release-please--branches--main', 'repo': {'full_name': REPO}}, 'base': {'ref': 'main'}, 'labels': [{'name': module.PENDING}], **changes}


class FakeAPI:
    def __init__(self, issues=(7,), pulls=None):
        self.issues = list(issues)
        self.pulls = pulls if pulls is not None else {7: pull()}
        self.pages = []
        self.writes = []

    def request(self, method, path, data=None):
        if method == 'PUT':
            self.writes.append((method, path, data))
            return {'merged': True}
        assert method == 'GET', (method, path)
        if path.startswith('/issues?'):
            self.pages.append(path)
            page = int(path.rsplit('page=', 1)[1])
            start = (page - 1) * module.PAGE_SIZE
            return [{'number': n, 'pull_request': {}} for n in self.issues[start:start + module.PAGE_SIZE]]
        return self.pulls[int(path.rsplit('/', 1)[1])]


class Runner:
    def __init__(self, returncode=0, stderr=''):
        self.calls = []
        self.result = subprocess.CompletedProcess([], returncode, '', stderr)

    def __call__(self, query, variables, token):
        self.calls.append((query, variables, token))
        return self.result


class ArmTests(unittest.TestCase):
    def test_arms_squash_with_exact_title_and_pinned_head(self):
        api, run = FakeAPI(), Runner()
        self.assertEqual(module.arm(api, 'token', REPO, run), [7])
        self.assertEqual(run.calls, [(module.MUTATION, {'id': 'PR_7', 'headline': 'chore: release main', 'oid': HEAD}, 'token')])
        self.assertIn('mergeMethod: SQUASH', module.MUTATION)
        self.assertIn('state=open&labels=autorelease%3A%20pending', api.pages[0])

    def test_nothing_pending_is_a_noop(self):
        run = Runner()
        self.assertEqual(module.arm(FakeAPI(issues=()), 'token', REPO, run), [])
        self.assertEqual(run.calls, [])

    def test_closed_and_other_branch_prs_are_ignored(self):
        for changes in ({'state': 'closed'}, {'base': {'ref': 'develop'}}):
            with self.subTest(changes=changes):
                run = Runner()
                self.assertEqual(module.arm(FakeAPI(pulls={7: pull(**changes)}), 'token', REPO, run), [])
                self.assertEqual(run.calls, [])

    def test_clean_status_merges_directly_with_pinned_head(self):
        api = FakeAPI()
        run = Runner(1, 'Pull request is in clean status')
        self.assertEqual(module.arm(api, 'token', REPO, run), [7])
        self.assertEqual(api.writes, [('PUT', '/pulls/7/merge', {
            'merge_method': 'squash', 'commit_title': 'chore: release main', 'commit_message': '', 'sha': HEAD})])

    def test_labelled_prs_not_from_release_please_are_ignored(self):
        for head in ({'sha': HEAD, 'ref': 'feature/x', 'repo': {'full_name': REPO}},
                     {'sha': HEAD, 'ref': 'release-please--branches--main', 'repo': {'full_name': 'fork/repo'}},
                     {'sha': HEAD, 'ref': 'release-please--branches--main', 'repo': None}):
            with self.subTest(head=head):
                run = Runner()
                self.assertEqual(module.arm(FakeAPI(pulls={7: pull(head=head)}), 'token', REPO, run), [])
                self.assertEqual(run.calls, [])

    def test_other_failures_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Cannot arm auto-merge on PR #7: boom'):
            module.arm(FakeAPI(), 'token', REPO, Runner(1, 'boom'))

    def test_unusable_title_or_head_fails(self):
        for changes in ({'title': ' '}, {'head': {'sha': 'abc', 'ref': 'release-please--branches--main', 'repo': {'full_name': REPO}}}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    module.arm(FakeAPI(pulls={7: pull(**changes)}), 'token', REPO, Runner())

    def test_listing_beyond_the_page_limit_fails(self):
        api = FakeAPI(issues=range(module.PAGE_SIZE * module.MAX_PAGES))
        with self.assertRaisesRegex(ValueError, 'Too many'):
            module.arm(api, 'token', REPO, Runner())


class ReportedTests(unittest.TestCase):
    @staticmethod
    def reported(*numbers):
        return json.dumps([{'number': n, 'title': 't'} for n in numbers])

    def test_reported_pr_missing_from_the_listing_is_armed(self):
        api, run = FakeAPI(issues=(), pulls={61: pull(61)}), Runner()
        self.assertEqual(module.arm(api, 'token', REPO, run, self.reported(61)), [61])
        self.assertEqual(run.calls[0][1]['id'], 'PR_61')

    def test_reported_and_listed_pr_is_armed_once(self):
        run = Runner()
        self.assertEqual(module.arm(FakeAPI(), 'token', REPO, run, self.reported(7)), [7])
        self.assertEqual(len(run.calls), 1)

    def test_duplicate_reported_numbers_are_armed_once(self):
        run = Runner()
        self.assertEqual(module.arm(FakeAPI(issues=()), 'token', REPO, run, self.reported(7, 7)), [7])
        self.assertEqual(len(run.calls), 1)

    def test_invalid_reported_pr_fails(self):
        for changes in ({'state': 'closed'}, {'base': {'ref': 'develop'}}, {'labels': []},
                        {'head': {'sha': HEAD, 'ref': 'feature/x', 'repo': {'full_name': REPO}}}):
            with self.subTest(changes=changes):
                run = Runner()
                with self.assertRaisesRegex(ValueError, 'reported by release-please'):
                    module.arm(FakeAPI(issues=(), pulls={7: pull(**changes)}), 'token', REPO, run, self.reported(7))
                self.assertEqual(run.calls, [])

    def test_empty_reported_keeps_the_listing_behaviour(self):
        for reported in ('', '  ', '[]'):
            with self.subTest(reported=reported):
                self.assertEqual(module.arm(FakeAPI(), 'token', REPO, Runner(), reported), [7])

    def test_malformed_reported_fails(self):
        for reported in ('{', '{}', '[1]', '[{}]', '[{"number": "7"}]', '[{"number": true}]'):
            with self.subTest(reported=reported):
                with self.assertRaises(ValueError):
                    module.arm(FakeAPI(), 'token', REPO, Runner(), reported)


if __name__ == '__main__':
    unittest.main()
