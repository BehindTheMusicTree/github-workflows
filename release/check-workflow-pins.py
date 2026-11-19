#!/usr/bin/env python3
"""Fail unless every github-workflows reference in the caller's workflows uses one commit."""

import os
from pathlib import Path
import re
import sys

REFERENCE = re.compile(r'^\s*(?:-\s+)?uses:\s*[\'"]?BehindTheMusicTree/github-workflows/(\S+?)@([^\s\'"#]+)', re.MULTILINE)
SHA = re.compile(r'[0-9a-f]{40}')


def check(workflows, expected):
    mismatches = []
    for path in sorted(p for pattern in ('*.yml', '*.yaml') for p in workflows.glob(pattern)):
        for target, ref in REFERENCE.findall(path.read_text(encoding='utf-8')):
            if ref != expected:
                mismatches.append(f'{path.name}: {target}@{ref}')
    if mismatches:
        raise ValueError('github-workflows references must all use the commit of this workflow '
                         f'({expected}); align them in one PR: ' + '; '.join(mismatches))


def main():
    if len(sys.argv) != 2:
        raise ValueError('usage: check-workflow-pins.py WORKFLOWS_DIRECTORY')
    expected = os.environ['WORKFLOW_SHA']
    if not SHA.fullmatch(expected):
        raise ValueError('WORKFLOW_SHA must be a full commit SHA')
    check(Path(sys.argv[1]), expected)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        sys.stderr.write(f'Workflow pin check failed: {error}\n')
        sys.exit(1)
