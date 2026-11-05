#!/usr/bin/env python3
"""Publish the validated tag's changelog; fail closed on API errors."""

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
APIError = TAGGING['APIError']
GitHub = TAGGING['GitHub']


def release_notes(changelog, tag):
    if not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
        raise ValueError('Expected a stable vX.Y.Z tag')
    lines = changelog.splitlines()
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r'## \[' + re.escape(tag[1:]) + r'\](?: - \d{4}-\d{2}-\d{2})?', line)]
    if len(starts) != 1:
        raise ValueError('Expected one version changelog section')
    end = next((i for i in range(starts[0] + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    body = '\n'.join(lines[starts[0] + 1:end]).strip()
    if not re.sub(r'^#{1,6}\s.*$', '', body, flags=re.MULTILINE).strip():
        raise ValueError('Version changelog section is empty')
    return body


def verify_release(release, tag):
    if (release['tag_name'] != tag or release['draft'] is not False or
            release['prerelease'] is not False or not release['published_at']):
        raise ValueError('Existing release is not the expected published stable release')


def publish(api, tag, commit, notes):
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or commit == '0' * 40:
        raise ValueError('Expected the exact tag commit SHA')
    path = '/releases/tags/' + quote(tag, safe='')
    try:
        release = api.request('GET', path)
    except APIError as error:
        if error.status != 404:
            raise
    else:
        verify_release(release, tag)
        return 'existing'
    try:
        release = api.request('POST', '/releases', {
            'tag_name': tag, 'target_commitish': commit, 'name': tag, 'body': notes,
            'draft': False, 'prerelease': False, 'make_latest': 'legacy',
        })
    except APIError as error:
        if error.status != 422:
            raise
        # A concurrent successful publisher is the only acceptable collision.
        release = api.request('GET', path)
        verify_release(release, tag)
        return 'existing'
    verify_release(release, tag)
    return 'created'


def tag_context(tag):
    git = VALIDATION['git']
    commit = git('rev-parse', 'HEAD').strip()
    if git('rev-parse', f'refs/tags/{tag}^{{commit}}').strip() != commit:
        raise ValueError('Checkout does not match the dereferenced tag')
    git('merge-base', '--is-ancestor', commit, 'refs/remotes/origin/main')
    policy = VALIDATION['policy_at'](commit, '.github/release-policy.json')
    version = VALIDATION['check_current'](commit, policy)
    if tag != policy['tag_prefix'] + version or not policy['outputs']['github_release']:
        raise ValueError('Tag or GitHub Release output differs from the policy')
    changelog = VALIDATION['read_file'](commit, policy['changelog'])
    notes = release_notes(changelog, 'v' + version)
    return commit, policy, notes


def main():
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in ('publish', 'notes'):
        raise ValueError('Usage: github-release.py publish | notes OUTPUT_PATH')
    tag = os.environ['GITHUB_REF_NAME']
    commit, policy, notes = tag_context(tag)
    if sys.argv[1] == 'notes':
        if len(sys.argv) != 3:
            raise ValueError('Notes output path is required')
        Path(sys.argv[2]).write_text(notes + '\n', encoding='utf-8')
        return
    if len(sys.argv) != 2 or policy['outputs']['packages']:
        raise ValueError('Standalone publisher requires a GitHub-only release policy')
    api = GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'], os.environ['GITHUB_API_URL'])
    if TAGGING['existing_commit'](api, tag) != commit:
        raise ValueError('Remote tag does not match the validated commit')
    logging.info('%s release %s', publish(api, tag, commit, notes), tag)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        logging.error('Release publication failed: %s', error)
        sys.exit(1)
