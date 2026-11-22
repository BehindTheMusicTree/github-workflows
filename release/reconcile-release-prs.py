#!/usr/bin/env python3
"""Mark merged release-please PRs as tagged once their declared GitHub outputs exist; fail closed otherwise.

release-please runs with skip-github-release, so nothing else moves a merged release PR from
`autorelease: pending` to `autorelease: tagged`, and it aborts every later run while one is pending.
"""

import logging
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import quote

DIRECTORY = Path(__file__).resolve().parent
TAGGING = runpy.run_path(str(DIRECTORY / 'create-tag.py'))
VALIDATION = runpy.run_path(str(DIRECTORY / 'validate-release.py'))
verify_release = runpy.run_path(str(DIRECTORY / 'github-release.py'))['verify_release']
APIError = TAGGING['APIError']
GitHub = TAGGING['GitHub']
BRANCH = 'main'
PENDING = 'autorelease: pending'
TAGGED = 'autorelease: tagged'
PAGE_SIZE = 100
# release-please scans the last 200 merged PRs; the label filter below is a superset of that window.
MAX_PAGES = 5


def pending_pull_requests(api):
    query = '?state=closed&labels=' + quote(PENDING, safe='') + f'&per_page={PAGE_SIZE}&page='
    numbers = []
    for page in range(1, MAX_PAGES + 1):
        items = api.request('GET', '/issues' + query + str(page))
        if not isinstance(items, list):
            raise ValueError('Unexpected issue listing')
        numbers += [item['number'] for item in items if 'pull_request' in item]
        if len(items) < PAGE_SIZE:
            return numbers
    raise ValueError('Too many pending release PRs to reconcile safely')


def release_commit(pull):
    sha = pull.get('merge_commit_sha')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError(f"PR #{pull['number']} has no merge commit")
    fields = VALIDATION['git']('rev-list', '--parents', '-n', '1', sha).split()
    if len(fields) != 2 or fields[0] != sha:
        raise ValueError(f"PR #{pull['number']} must be squash or rebase merged into a single parent commit")
    return fields[1], sha


def reconcile(api, policy_paths):
    if not policy_paths:
        raise ValueError('At least one release policy is required')
    done = []
    for number in pending_pull_requests(api):
        pull = api.request('GET', f'/pulls/{number}')
        if not pull.get('merged_at') or pull['base']['ref'] != BRANCH:
            continue  # release-please only scans merged PRs of the target branch
        parent, commit = release_commit(pull)
        outputs = []
        for path in policy_paths:
            result = VALIDATION['validate'](parent, commit, path)
            if result['release']:
                policy = VALIDATION['policy_at'](commit, path)
                outputs.append((result['tag'], policy['outputs']['github_release']))
        if not outputs:
            raise ValueError(f'PR #{number} carries no release intent for the given policies')
        for tag, github_release in outputs:
            if TAGGING['existing_commit'](api, tag) != commit:
                raise ValueError(f'Tag {tag} of PR #{number} is missing or targets another commit')
            if github_release:
                try:
                    release = api.request('GET', '/releases/tags/' + quote(tag, safe=''))
                except APIError as error:
                    if error.status != 404:
                        raise
                    raise ValueError(f'GitHub Release {tag} of PR #{number} is missing; retry publication first') from error
                verify_release(release, tag)
        # Add before removing: a failure in between leaves the PR pending, so a rerun retries.
        api.request('POST', f'/issues/{number}/labels', {'labels': [TAGGED]})
        try:
            api.request('DELETE', f'/issues/{number}/labels/' + quote(PENDING, safe=''))
        except APIError as error:
            if error.status != 404:
                raise
        done.append(number)
    return done


def main():
    api = GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['RELEASE_PR_APP_TOKEN'], os.environ['GITHUB_API_URL'])
    done = reconcile(api, sys.argv[1:])
    logging.info('Reconciled release PRs: %s', ', '.join(f'#{n}' for n in done) or 'none')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        logging.error('Release PR reconciliation failed: %s', error)
        sys.exit(1)
