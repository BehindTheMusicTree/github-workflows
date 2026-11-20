#!/usr/bin/env python3
"""Arm squash auto-merge on open release-please PRs, committing with the PR title unchanged.

reconcile-release-prs.py requires a squash merge whose title is the PR title, and the head is pinned so
that a push after arming disarms auto-merge instead of publishing unchecked content.
"""

import logging
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from urllib.parse import quote

DIRECTORY = Path(__file__).resolve().parent
TAGGING = runpy.run_path(str(DIRECTORY / 'create-tag.py'))
GitHub = TAGGING['GitHub']
BRANCH = 'main'
PENDING = 'autorelease: pending'
PAGE_SIZE = 100
MAX_PAGES = 5
# GitHub refuses to arm auto-merge when nothing is left to wait for.
CLEAN_STATUS = 'clean status'
MUTATION = (
    'mutation($id: ID!, $headline: String!, $oid: GitObjectID!) {'
    ' enablePullRequestAutoMerge(input: {pullRequestId: $id, mergeMethod: SQUASH,'
    ' commitHeadline: $headline, commitBody: "", expectedHeadOid: $oid}) { clientMutationId } }'
)


def open_release_pull_requests(api):
    query = '?state=open&labels=' + quote(PENDING, safe='') + f'&per_page={PAGE_SIZE}&page='
    numbers = []
    for page in range(1, MAX_PAGES + 1):
        items = api.request('GET', '/issues' + query + str(page))
        if not isinstance(items, list):
            raise ValueError('Unexpected issue listing')
        numbers += [item['number'] for item in items if 'pull_request' in item]
        if len(items) < PAGE_SIZE:
            return numbers
    raise ValueError('Too many open release PRs to arm safely')


def graphql(query, variables, token):
    command = ['gh', 'api', 'graphql', '-f', f'query={query}']
    for name, value in variables.items():
        command += ['-f', f'{name}={value}']
    return subprocess.run(command, env={**os.environ, 'GH_TOKEN': token}, capture_output=True, text=True, check=False)


def arm(api, token, run=graphql):
    armed = []
    for number in open_release_pull_requests(api):
        pull = api.request('GET', f'/pulls/{number}')
        if pull['state'] != 'open' or pull['base']['ref'] != BRANCH:
            continue
        title, head = pull['title'], pull['head']['sha']
        if not title.strip() or not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError(f'PR #{number} has no usable title or head')
        result = run(MUTATION, {'id': pull['node_id'], 'headline': title, 'oid': head}, token)
        if result.returncode != 0:
            if CLEAN_STATUS in (result.stderr + result.stdout).lower():
                logging.info('PR #%s is already clean: left for the next run to arm', number)
                continue
            raise ValueError(f'Cannot arm auto-merge on PR #{number}: {result.stderr.strip() or result.stdout.strip()}')
        armed.append(number)
    return armed


def main():
    token = os.environ['RELEASE_PR_APP_TOKEN']
    api = GitHub(os.environ['GITHUB_REPOSITORY'], token, os.environ['GITHUB_API_URL'])
    armed = arm(api, token)
    logging.info('Armed auto-merge on release PRs: %s', ', '.join(f'#{n}' for n in armed) or 'none')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        logging.error('Arming release PR auto-merge failed: %s', error)
        sys.exit(1)
