#!/usr/bin/env python3
"""Arm squash auto-merge on open release-please PRs, committing with the PR title unchanged.

reconcile-release-prs.py requires a squash merge whose title is the PR title, and the head is pinned so
that a push after arming disarms auto-merge instead of publishing unchecked content.
"""

import json
import logging
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time
from urllib.parse import quote

DIRECTORY = Path(__file__).resolve().parent
TAGGING = runpy.run_path(str(DIRECTORY / 'create-tag.py'))
GitHub = TAGGING['GitHub']
BRANCH = 'main'
HEAD_PREFIX = 'release-please--'
PENDING = 'autorelease: pending'
PAGE_SIZE = 100
MAX_PAGES = 5
# GitHub refuses to arm auto-merge when nothing is left to wait for; the PR is then merged directly, decided
# from the REST merge state (computed in the background, so `unknown` is read again a bounded number of times).
STATE_READS = 5
STATE_WAIT = 2
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


def reported_numbers(reported):
    # release-please-action's `prs` output: a JSON array of PullRequest objects; unset when it touched no PR.
    if not reported.strip():
        return []
    try:
        items = json.loads(reported)
    except json.JSONDecodeError as error:
        raise ValueError(f'RELEASE_PRS is not valid JSON: {error}') from error
    numbers = [item.get('number') if isinstance(item, dict) else None for item in items] if isinstance(items, list) else None
    if numbers is None or any(type(number) is not int for number in numbers):
        raise ValueError('RELEASE_PRS must be a JSON list of objects with an integer number')
    return list(dict.fromkeys(numbers))


def graphql(query, variables, token):
    command = ['gh', 'api', 'graphql', '-f', f'query={query}']
    for name, value in variables.items():
        command += ['-f', f'{name}={value}']
    return subprocess.run(command, env={**os.environ, 'GH_TOKEN': token}, capture_output=True, text=True, check=False)


def release_branch(pull, repository):
    # The label alone is not proof of origin: only a release-please branch of this repository is armed.
    head_repo = (pull['head'].get('repo') or {}).get('full_name')
    return head_repo == repository and pull['head']['ref'].startswith(HEAD_PREFIX)


def merge_state(api, number, head, sleep):
    for read in range(STATE_READS):
        pull = api.request('GET', f'/pulls/{number}')
        if pull['head']['sha'] != head:
            raise ValueError(f'PR #{number} head moved from {head} to {pull["head"]["sha"]} while arming')
        state = pull.get('mergeable_state')
        if state != 'unknown' or read == STATE_READS - 1:
            return state
        sleep(STATE_WAIT)


def arm(api, token, repository, run=graphql, reported='', sleep=time.sleep):
    # The issue listing can lag behind a PR release-please has just opened and labelled, so the PRs the
    # action reports are armed too; they are checked strictly because the listing's label filter is absent.
    provided = reported_numbers(reported)
    candidates = provided + [number for number in open_release_pull_requests(api) if number not in provided]
    armed = []
    for number in candidates:
        pull = api.request('GET', f'/pulls/{number}')
        valid = pull['state'] == 'open' and pull['base']['ref'] == BRANCH and release_branch(pull, repository)
        if number in provided:
            if not valid or PENDING not in [label['name'] for label in pull['labels']]:
                raise ValueError(f'PR #{number} reported by release-please is not an open pending release PR')
        elif not valid:
            continue
        title, head = pull['title'], pull['head']['sha']
        if not title.strip() or not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError(f'PR #{number} has no usable title or head')
        result = run(MUTATION, {'id': pull['node_id'], 'headline': title, 'oid': head}, token)
        if result.returncode != 0:
            state = merge_state(api, number, head, sleep)
            if state == 'clean':
                # Nothing left to wait for; the sha pin and the branch rules still gate this merge, and
                # no later run would arm it.
                logging.info('PR #%s is already clean: merging it directly', number)
                api.request('PUT', f'/pulls/{number}/merge',
                            {'merge_method': 'squash', 'commit_title': title, 'commit_message': '', 'sha': head})
                armed.append(number)
                continue
            raise ValueError(f'Cannot arm auto-merge on PR #{number} (merge state {state}): '
                             f'{result.stderr.strip() or result.stdout.strip()}')
        armed.append(number)
    return armed


def main():
    token = os.environ['RELEASE_PR_APP_TOKEN']
    api = GitHub(os.environ['GITHUB_REPOSITORY'], token, os.environ['GITHUB_API_URL'])
    armed = arm(api, token, os.environ['GITHUB_REPOSITORY'], graphql,
                reported=os.environ.get('RELEASE_PRS', ''))
    logging.info('Armed auto-merge on release PRs: %s', ', '.join(f'#{n}' for n in armed) or 'none')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        logging.error('Arming release PR auto-merge failed: %s', error)
        sys.exit(1)
