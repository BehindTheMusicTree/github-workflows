import importlib.util
from pathlib import Path
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('armer', Path(__file__).with_name('arm-release-pr-auto-merge.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEAD = 'c' * 40


def pull(number=7, **changes):
    return {'number': number, 'state': 'open', 'node_id': f'PR_{number}', 'title': 'chore: release main',
            'head': {'sha': HEAD}, 'base': {'ref': 'main'}, **changes}


class FakeAPI:
    def __init__(self, issues=(7,), pulls=None):
        self.issues = list(issues)
        self.pulls = pulls if pulls is not None else {7: pull()}
        self.pages = []

    def request(self, method, path, data=None):
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
        self.assertEqual(module.arm(api, 'token', run), [7])
        self.assertEqual(run.calls, [(module.MUTATION, {'id': 'PR_7', 'headline': 'chore: release main', 'oid': HEAD}, 'token')])
        self.assertIn('mergeMethod: SQUASH', module.MUTATION)
        self.assertIn('state=open&labels=autorelease%3A%20pending', api.pages[0])

    def test_nothing_pending_is_a_noop(self):
        run = Runner()
        self.assertEqual(module.arm(FakeAPI(issues=()), 'token', run), [])
        self.assertEqual(run.calls, [])

    def test_closed_and_other_branch_prs_are_ignored(self):
        for changes in ({'state': 'closed'}, {'base': {'ref': 'develop'}}):
            with self.subTest(changes=changes):
                run = Runner()
                self.assertEqual(module.arm(FakeAPI(pulls={7: pull(**changes)}), 'token', run), [])
                self.assertEqual(run.calls, [])

    def test_clean_status_is_left_for_the_next_run(self):
        run = Runner(1, 'Pull request is in clean status')
        self.assertEqual(module.arm(FakeAPI(), 'token', run), [])

    def test_other_failures_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Cannot arm auto-merge on PR #7: boom'):
            module.arm(FakeAPI(), 'token', Runner(1, 'boom'))

    def test_unusable_title_or_head_fails(self):
        for changes in ({'title': ' '}, {'head': {'sha': 'abc'}}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    module.arm(FakeAPI(pulls={7: pull(**changes)}), 'token', Runner())

    def test_listing_beyond_the_page_limit_fails(self):
        api = FakeAPI(issues=range(module.PAGE_SIZE * module.MAX_PAGES))
        with self.assertRaisesRegex(ValueError, 'Too many'):
            module.arm(api, 'token', Runner())


if __name__ == '__main__':
    unittest.main()
