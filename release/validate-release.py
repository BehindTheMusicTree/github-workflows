#!/usr/bin/env python3
"""Validate a push's release intent without credentials or side effects."""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import PurePosixPath

SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')


def git(*args):
    result = subprocess.run(['git', *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def read_file(commit, path):
    if not isinstance(path, str) or not path or path.startswith('-') or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path:
        raise ValueError('invalid repository path')
    return git('show', f'{commit}:{path}')


def version_at(commit, source):
    if not isinstance(source, dict) or set(source) not in ({'path', 'format'}, {'path', 'format', 'key'}):
        raise ValueError('invalid version source')
    data = read_file(commit, source['path'])
    fmt = source['format']
    if fmt == 'text' and 'key' not in source:
        version = data.strip()
    elif fmt in ('json', 'toml') and isinstance(source.get('key'), str) and source['key']:
        obj = json.loads(data) if fmt == 'json' else tomllib.loads(data)
        for part in source['key'].split('.'):
            if not part or not isinstance(obj, dict) or part not in obj:
                raise ValueError('version key missing')
            obj = obj[part]
        version = obj
    else:
        raise ValueError('invalid version format or key')
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError('version must be stable SemVer without leading zeroes')
    return version


def validate(before, after, policy_path):
    if not SHA.fullmatch(before) or not SHA.fullmatch(after) or before == '0' * 40:
        raise ValueError('push requires two exact nonzero commit SHAs')
    git('merge-base', '--is-ancestor', before, after)
    git('merge-base', '--is-ancestor', after, 'refs/remotes/origin/main')
    policy = json.loads(read_file(after, policy_path))
    if not isinstance(policy, dict) or set(policy) != {'release_branch', 'version', 'mirrors', 'tag_prefix', 'changelog', 'outputs'} or policy['release_branch'] != 'main':
        raise ValueError('invalid release policy')
    prefix = policy['tag_prefix']
    if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', prefix):
        raise ValueError('invalid tag prefix')
    mirrors = policy['mirrors']
    outputs = policy['outputs']
    if not isinstance(mirrors, list) or not isinstance(outputs, dict) or set(outputs) != {'github_release', 'packages'} or type(outputs['github_release']) is not bool or not isinstance(outputs['packages'], list) or any(not isinstance(p, str) or not p for p in outputs['packages']) or len(set(outputs['packages'])) != len(outputs['packages']):
        raise ValueError('invalid mirrors or outputs')
    old = version_at(before, policy['version'])
    new = version_at(after, policy['version'])
    if old == new:
        return {'release': False}
    if tuple(map(int, new.split('.'))) <= tuple(map(int, old.split('.'))):
        raise ValueError('version must increase')
    for mirror in mirrors:
        if version_at(after, mirror) != new:
            raise ValueError('version mirror mismatch')
    changelog = read_file(after, policy['changelog'])
    if not re.search(r'^## \[' + re.escape(new) + r'\](?:\s|$)', changelog, re.MULTILINE):
        raise ValueError('versioned changelog section missing')
    tag = prefix + new
    git('check-ref-format', f'refs/tags/{tag}')
    return {'release': True, 'version': new, 'tag': tag, 'commit': after}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4:
            raise ValueError('usage: validate-release.py BEFORE AFTER POLICY_PATH')
        sys.stdout.write(json.dumps(validate(*sys.argv[1:])) + '\n')
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        sys.stderr.write(f'release validation failed: {exc}\n')
        sys.exit(1)
