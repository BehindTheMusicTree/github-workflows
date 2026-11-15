#!/usr/bin/env python3
"""Validate Python distributions and recover partial PyPI uploads without blind skips."""

import argparse
from email.parser import BytesParser
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import runpy
import shutil
import sys
import tarfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
import zipfile


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


def registry_files(package, version, opener=urlopen):
    url = f'https://pypi.org/pypi/{quote(package, safe="")}/{quote(version, safe="")}/json'
    try:
        with opener(url, timeout=30) as response:
            metadata = json.load(response)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            return {}
        raise
    if canonical_name(metadata['info']['name']) != package or metadata['info']['version'] != version:
        raise ValueError('PyPI response differs from the intended package/version')
    urls = metadata['urls']
    if not isinstance(urls, list):
        raise ValueError('Invalid PyPI file list')
    result = {}
    for item in urls:
        filename = item['filename']
        digest = item['digests']['sha256']
        if (not isinstance(filename, str) or filename in result or item['yanked'] is not False
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('Invalid, duplicate or yanked PyPI file')
        result[filename] = digest
    return result


def missing_files(manifest, remote):
    expected = manifest['files']
    for filename, digest in remote.items():
        if filename not in expected or expected[filename] != digest:
            raise ValueError('Existing PyPI filename or SHA-256 differs; investigate without moving the tag')
    return sorted(set(expected) - set(remote))


def prepare(package, version, directory, pending, opener=urlopen):
    manifest = distributions(package, version, directory)
    if json.loads((Path(directory) / 'manifest.json').read_text()) != manifest:
        raise ValueError('Downloaded distributions differ from the build manifest')
    missing = missing_files(manifest, registry_files(manifest['package'], version, opener))
    # Refuse stale staging files so only this verified missing set can be uploaded.
    pending = Path(pending)
    pending.mkdir(parents=True, exist_ok=False)
    for filename in missing:
        shutil.copyfile(Path(directory) / filename, pending / filename)
    return bool(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['manifest', 'prepare', 'verify'])
    parser.add_argument('package')
    parser.add_argument('version')
    parser.add_argument('directory', type=Path)
    parser.add_argument('pending', type=Path, nargs='?')
    args = parser.parse_args()
    if args.command == 'manifest':
        manifest = distributions(args.package, args.version, args.directory)
        (args.directory / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    elif args.command == 'prepare':
        if args.pending is None:
            raise ValueError('A new pending directory is required')
        output = os.environ['GITHUB_OUTPUT']
        needed = prepare(args.package, args.version, args.directory, args.pending)
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f'upload-needed={str(needed).lower()}\n')
    else:
        manifest = distributions(args.package, args.version, args.directory)
        if missing_files(manifest, registry_files(manifest['package'], args.version)):
            raise ValueError('PyPI does not yet contain every intended distribution')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        logging.error('Python artifact verification failed: %s', error)
        sys.exit(1)
