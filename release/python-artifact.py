#!/usr/bin/env python3
"""Validate Python distributions and recover partial PyPI uploads without blind skips."""

import argparse
from email.parser import BytesParser
import hashlib
from http.client import HTTPException
import json
import logging
import os
from pathlib import Path
import re
import runpy
import shutil
import ssl
import sys
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile


# Closed table: the registry input selects a base URL, it never supplies one.
REGISTRY_URLS = {'pypi': 'https://pypi.org', 'testpypi': 'https://test.pypi.org'}


def registry_url(registry):
    if registry not in REGISTRY_URLS:
        raise ValueError(f'Unknown registry {registry!r}; expected one of {", ".join(sorted(REGISTRY_URLS))}')
    return REGISTRY_URLS[registry]


def package_directory(directory, validation):
    if directory != '.':
        validation['repository_path'](directory)
    root = Path.cwd().resolve()
    path = root / directory
    if not path.resolve().is_relative_to(root) or not path.is_dir():
        raise ValueError('Package directory must be an existing directory inside the repository')
    for part in path.relative_to(root).parts:
        root = root / part
        if root.is_symlink():
            raise ValueError('Package directory must not traverse symlinks')
    return path


def source_version(package, tag, validation=None, package_directory_path='.',
                   release_policy_path='.github/release-policy.json'):
    canonical_name(package)
    if not isinstance(tag, str) or not tag:
        raise ValueError('A release tag is required')
    if validation is None:
        validation = runpy.run_path(str(Path(__file__).with_name('validate-release.py')))
    package_directory(package_directory_path, validation)
    validation['repository_path'](release_policy_path)
    git = validation['git']
    commit = git('rev-parse', 'HEAD').strip()
    if git('rev-parse', f'refs/tags/{tag}^{{commit}}').strip() != commit:
        raise ValueError('Checkout differs from the tag commit')
    git('merge-base', '--is-ancestor', commit, 'refs/remotes/origin/main')
    policy = validation['policy_at'](commit, release_policy_path)
    version = validation['check_current'](commit, policy)
    if tag != policy['tag_prefix'] + version or package not in policy['outputs']['packages']:
        raise ValueError('Tag or package differs from the publication contract')
    return version


def canonical_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name):
        raise ValueError('Expected a Python project name')
    return re.sub(r'[-_.]+', '-', name).lower()


def distributions(package, version, directory):
    name = canonical_name(package)
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Expected a stable X.Y.Z version')
    files = [path for path in Path(directory).iterdir() if path.name != 'manifest.json']
    wheels = [path for path in files if path.name.endswith('.whl')]
    sdists = [path for path in files if path.name.endswith('.tar.gz')]
    if len(files) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise ValueError('Expected exactly one wheel and one .tar.gz sdist')
    hashes = {}
    for path in wheels + sdists:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Distributions must be regular files')
        if path in wheels:
            parts = path.name[:-4].split('-')
            if len(parts) not in (5, 6) or canonical_name(parts[0]) != name or parts[1] != version:
                raise ValueError('Wheel filename differs from the intended package/version')
            with zipfile.ZipFile(path) as archive:
                members = [item for item in archive.namelist()
                           if re.fullmatch(r'[^/]+\.dist-info/METADATA', item)]
                if len(members) != 1:
                    raise ValueError('Expected one wheel METADATA file')
                metadata = archive.read(members[0])
        else:
            stem = path.name[:-7]
            project, separator, file_version = stem.rpartition('-')
            if not separator or canonical_name(project) != name or file_version != version:
                raise ValueError('Sdist filename differs from the intended package/version')
            with tarfile.open(path, 'r:gz') as archive:
                members = [item for item in archive.getmembers() if item.name == stem + '/PKG-INFO']
                if len(members) != 1 or not members[0].isfile():
                    raise ValueError('Expected one regular sdist PKG-INFO file')
                metadata = archive.extractfile(members[0]).read()
        headers = BytesParser().parsebytes(metadata)
        if (len(headers.get_all('Name', [])) != 1 or len(headers.get_all('Version', [])) != 1
                or canonical_name(headers['Name']) != name or headers['Version'] != version):
            raise ValueError('Distribution metadata differs from the intended package/version')
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'package': name, 'version': version, 'files': hashes}


# PEP 691 JSON flavour of the Simple index: the page pip and uv resolve from.
SIMPLE_ACCEPT = 'application/vnd.pypi.simple.v1+json'
# The Simple index is served with `max-age=600`, so a reader can see a stale page for up to
# 600 s after an upload; the default wait adds a 60 s margin.
DEFAULT_WAIT_SECONDS = 660
MAX_POLL_DELAY = 30


def file_version(filename, package):
    """Return the version of a wheel or sdist of `package`, or None for anything else."""
    if filename.endswith('.whl'):
        parts = filename[:-4].split('-')
        if len(parts) in (5, 6) and canonical_name(parts[0]) == package:
            return parts[1]
    elif filename.endswith('.tar.gz'):
        project, separator, version = filename[:-7].rpartition('-')
        if separator and canonical_name(project) == package:
            return version
    return None


def registry_files(package, version, opener=urlopen, registry='pypi'):
    # Read the project's Simple page, as installers do: it is purged on upload. The per-version
    # JSON URL is not: `prepare` caches a 404 there that outlives the upload.
    url = f'{registry_url(registry)}/simple/{quote(package, safe="")}/'
    try:
        with opener(Request(url, headers={'Accept': SIMPLE_ACCEPT}), timeout=30) as response:
            page = json.load(response)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            return {}
        raise
    meta = page['meta']['api-version']
    if not isinstance(meta, str) or meta.split('.')[0] != '1':
        raise ValueError('Unsupported PyPI Simple API version')
    if canonical_name(page['name']) != package:
        raise ValueError('PyPI response differs from the intended package')
    files = page['files']
    if not isinstance(files, list):
        raise ValueError('Invalid PyPI file list')
    names = set()
    result = {}
    for item in files:
        filename = item['filename']
        if not isinstance(filename, str) or filename in names:
            raise ValueError('Invalid or duplicate PyPI file')
        names.add(filename)
        if file_version(filename, package) != version:
            continue
        digest = item['hashes']['sha256']
        if item.get('yanked', False) is not False or not isinstance(digest, str) \
                or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid or yanked PyPI file')
        result[filename] = digest
    return result


def missing_files(manifest, remote):
    expected = manifest['files']
    for filename, digest in remote.items():
        if filename not in expected or expected[filename] != digest:
            raise ValueError('Existing PyPI filename or SHA-256 differs; investigate without moving the tag')
    return sorted(set(expected) - set(remote))


def prepare(package, version, directory, pending, opener=urlopen, registry='pypi'):
    registry_url(registry)
    manifest = distributions(package, version, directory)
    if json.loads((Path(directory) / 'manifest.json').read_text()) != manifest:
        raise ValueError('Downloaded distributions differ from the build manifest')
    missing = missing_files(manifest, registry_files(manifest['package'], version, opener, registry))
    # Refuse stale staging files so only this verified missing set can be uploaded.
    pending = Path(pending)
    pending.mkdir(parents=True, exist_ok=False)
    for filename in missing:
        shutil.copyfile(Path(directory) / filename, pending / filename)
    return bool(missing)


def retryable(error):
    if isinstance(error, HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, (URLError, TimeoutError, ConnectionError, ssl.SSLError, HTTPException))


def verify(package, version, directory, opener=urlopen, registry='pypi',
           wait_seconds=DEFAULT_WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic):
    registry_url(registry)
    manifest = distributions(package, version, directory)
    start = clock()
    delay = 5
    while True:
        try:
            missing = missing_files(manifest, registry_files(manifest['package'], version, opener, registry))
            if not missing:
                return
            reason = f'missing {", ".join(missing)}'
        except (OSError, HTTPException) as error:
            # A digest mismatch or a malformed page (ValueError, KeyError, TypeError) fails at once.
            if not retryable(error):
                raise
            reason = f'registry error: {error}'
        remaining = wait_seconds - (clock() - start)
        if remaining <= 0:
            raise ValueError(f'The registry does not yet contain every intended distribution ({reason})')
        logging.info('%s; retrying in %ss (%ss left)', reason, min(delay, remaining), round(remaining))
        sleep(min(delay, remaining))
        delay = min(delay * 2, MAX_POLL_DELAY)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['manifest', 'prepare', 'verify'])
    parser.add_argument('package')
    parser.add_argument('version')
    parser.add_argument('directory', type=Path)
    parser.add_argument('pending', type=Path, nargs='?')
    parser.add_argument('--registry', default='pypi')
    parser.add_argument('--wait-seconds', type=int, default=DEFAULT_WAIT_SECONDS)
    args = parser.parse_args()
    if args.command == 'manifest':
        manifest = distributions(args.package, args.version, args.directory)
        (args.directory / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    elif args.command == 'prepare':
        if args.pending is None:
            raise ValueError('A new pending directory is required')
        output = os.environ['GITHUB_OUTPUT']
        needed = prepare(args.package, args.version, args.directory, args.pending, registry=args.registry)
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f'upload-needed={str(needed).lower()}\n')
    else:
        if args.wait_seconds < 0:
            raise ValueError('--wait-seconds must not be negative')
        verify(args.package, args.version, args.directory, registry=args.registry,
               wait_seconds=args.wait_seconds)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        logging.error('Python artifact verification failed: %s', error)
        sys.exit(1)
