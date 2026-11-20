import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
import zipfile

spec = importlib.util.spec_from_file_location('python_artifact', Path(__file__).with_name('python-artifact.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PythonArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        self.wheel = self.dist / 'example_pkg-1.2.3-py3-none-any.whl'
        self.sdist = self.dist / 'example_pkg-1.2.3.tar.gz'
        self.write_archives()
        self.manifest = module.distributions('Example.Pkg', '1.2.3', self.dist)
        (self.dist / 'manifest.json').write_text(json.dumps(self.manifest))

    def write_archives(self, name='example-pkg', version='1.2.3'):
        metadata = f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'.encode()
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('example_pkg-1.2.3.dist-info/METADATA', metadata)
        with tarfile.open(self.sdist, 'w:gz') as archive:
            member = tarfile.TarInfo('example_pkg-1.2.3/PKG-INFO')
            member.size = len(metadata)
            archive.addfile(member, io.BytesIO(metadata))

    def response(self, files=None, **changes):
        data = {'info': {'name': 'example-pkg', 'version': '1.2.3'}, 'urls': [
            {'filename': filename, 'digests': {'sha256': digest}, 'yanked': False}
            for filename, digest in (self.manifest['files'] if files is None else files).items()]}
        data.update(changes)
        def opener(url, timeout):
            self.assertEqual(url, 'https://pypi.org/pypi/example-pkg/1.2.3/json')
            self.assertEqual(timeout, 30)
            return io.BytesIO(json.dumps(data).encode())
        return opener

    @staticmethod
    def failing(error):
        def opener(*args, **kwargs):
            raise error
        return opener

    def prepare(self, opener):
        return module.prepare('example-pkg', '1.2.3', self.dist, self.root / 'pending', opener)

    def test_testpypi_uses_its_own_api_url(self):
        urls = []
        def opener(url, timeout):
            urls.append(url)
            raise HTTPError(url, 404, 'missing', {}, None)
        self.assertEqual(module.registry_files('example-pkg', '1.2.3', opener, 'testpypi'), {})
        self.assertEqual(urls, ['https://test.pypi.org/pypi/example-pkg/1.2.3/json'])

    def test_unknown_registry_fails_before_any_lookup(self):
        for registry in ['', 'PyPI', 'https://evil.example', 'test']:
            with self.subTest(registry=registry), self.assertRaisesRegex(ValueError, 'Unknown registry'):
                module.prepare('example-pkg', '1.2.3', self.dist, self.root / 'pending',
                               self.failing(AssertionError('must not query')), registry)
            self.assertFalse((self.root / 'pending').exists())
        with self.assertRaisesRegex(ValueError, 'Unknown registry'):
            module.registry_files('example-pkg', '1.2.3', self.failing(AssertionError('must not query')), 'nope')

    def test_manifest_checks_both_formats_and_hashes(self):
        self.assertEqual(self.manifest['package'], 'example-pkg')
        self.assertEqual(self.manifest['files'], {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.wheel, self.sdist)})

    def test_only_404_means_absent_and_stages_both_files(self):
        self.assertTrue(self.prepare(self.failing(HTTPError('url', 404, 'missing', {}, None))))
        self.assertEqual({path.name for path in (self.root / 'pending').iterdir()}, set(self.manifest['files']))

    def test_identical_retry_needs_no_upload(self):
        self.assertFalse(self.prepare(self.response()))
        self.assertEqual(list((self.root / 'pending').iterdir()), [])

    def test_partial_retry_stages_only_missing_file(self):
        self.assertTrue(self.prepare(self.response({self.wheel.name: self.manifest['files'][self.wheel.name]})))
        staged = list((self.root / 'pending').iterdir())
        self.assertEqual([path.name for path in staged], [self.sdist.name])
        self.assertEqual(staged[0].read_bytes(), self.sdist.read_bytes())

    def test_mismatched_hash_or_filename_never_stages_anything(self):
        for files in ({self.wheel.name: '0' * 64}, {'unexpected.whl': '0' * 64}):
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.prepare(self.response(files))
            self.assertFalse((self.root / 'pending').exists())

    def test_registry_errors_are_not_absence(self):
        for error in [HTTPError('url', code, 'failure', {}, None) for code in (401, 403, 429, 500)] + [URLError('offline')]:
            with self.subTest(error=error), self.assertRaises(OSError):
                self.prepare(self.failing(error))
            self.assertFalse((self.root / 'pending').exists())

    def test_malformed_responses_fail_closed(self):
        valid_file = {'filename': self.wheel.name, 'digests': {'sha256': '0' * 64}, 'yanked': False}
        for changes in ({'info': {'name': 'other', 'version': '1.2.3'}},
                        {'info': {'name': 'example-pkg', 'version': '9.9.9'}},
                        {'urls': None}, {'urls': [{}]}, {'urls': [valid_file, valid_file]},
                        {'urls': [{**valid_file, 'yanked': True}]},
                        {'urls': [{**valid_file, 'digests': {'sha256': 'invalid'}}]}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError, KeyError)):
                self.prepare(self.response(**changes))
        with self.assertRaises(ValueError):
            self.prepare(lambda *args, **kwargs: io.BytesIO(b'not JSON'))

    def test_downloaded_artifact_mismatch_fails_before_registry_lookup(self):
        self.write_archives(name='example-pkg')
        with zipfile.ZipFile(self.wheel, 'a') as archive:
            archive.writestr('extra.txt', 'changed bytes')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.prepare(self.failing(AssertionError('must not query PyPI')))

    def test_stale_staging_directory_is_rejected(self):
        (self.root / 'pending').mkdir()
        (self.root / 'pending' / 'old.whl').write_text('stale')
        with self.assertRaises(FileExistsError):
            self.prepare(self.response())

    def test_missing_or_extra_distributions_fail(self):
        self.sdist.unlink()
        with self.assertRaises(ValueError):
            module.distributions('example-pkg', '1.2.3', self.dist)
        self.write_archives()
        (self.dist / 'unexpected.txt').write_text('unexpected')
        with self.assertRaises(ValueError):
            module.distributions('example-pkg', '1.2.3', self.dist)

    def test_metadata_and_filenames_must_match_expected_identity(self):
        for name, version in [('other', '1.2.3'), ('example-pkg', '2.0.0')]:
            self.write_archives(name, version)
            with self.subTest(name=name, version=version), self.assertRaises(ValueError):
                module.distributions('example-pkg', '1.2.3', self.dist)
        self.write_archives()
        for path in [self.wheel, self.sdist]:
            renamed = path.with_name(path.name.replace('1.2.3', '2.0.0'))
            path.rename(renamed)
            with self.assertRaises(ValueError):
                module.distributions('example-pkg', '1.2.3', self.dist)
            renamed.rename(path)

    def test_invalid_package_or_unstable_version_fails(self):
        for package, version in [('bad/name', '1.2.3'), ('example-pkg', '1.2.3rc1'), ('example-pkg', '01.2.3')]:
            with self.subTest(package=package, version=version), self.assertRaises(ValueError):
                module.distributions(package, version, self.dist)


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self.commit = 'a' * 40
        self.policy = {'tag_prefix': 'v', 'outputs': {'packages': ['example-pkg']}}
        self.validation = {
            'repository_path': module.runpy.run_path(str(Path(__file__).with_name('validate-release.py')))['repository_path'],
            'git': Mock(side_effect=[self.commit, self.commit, '']),
            'policy_at': Mock(return_value=self.policy),
            'check_current': Mock(return_value='1.2.3'),
        }

    def test_validates_exact_tag_main_ancestry_and_policy(self):
        self.assertEqual(module.source_version('example-pkg', 'v1.2.3', self.validation), '1.2.3')
        self.validation['git'].assert_any_call('rev-parse', 'refs/tags/v1.2.3^{commit}')
        self.validation['git'].assert_any_call('merge-base', '--is-ancestor', self.commit, 'refs/remotes/origin/main')
        self.validation['policy_at'].assert_called_once_with(self.commit, '.github/release-policy.json')
        self.validation['check_current'].assert_called_once_with(self.commit, self.policy)

    def test_empty_tag_fails_before_git(self):
        for tag in ['', None]:
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, 'tag is required'):
                module.source_version('example-pkg', tag, self.validation)
        self.validation['git'].assert_not_called()

    def test_wrong_tag_commit_fails(self):
        self.validation['git'].side_effect = [self.commit, 'b' * 40]
        with self.assertRaisesRegex(ValueError, 'tag commit'):
            module.source_version('example-pkg', 'v1.2.3', self.validation)

    def test_tag_version_or_package_contract_mismatch_fails(self):
        for package, tag in [('other', 'v1.2.3'), ('example-pkg', 'v2.0.0')]:
            self.validation['git'].side_effect = [self.commit, self.commit, '']
            with self.subTest(package=package, tag=tag), self.assertRaisesRegex(ValueError, 'contract'):
                module.source_version(package, tag, self.validation)

    def test_ancestry_or_version_validation_errors_propagate(self):
        self.validation['git'].side_effect = [self.commit, self.commit, ValueError('not on main')]
        with self.assertRaisesRegex(ValueError, 'not on main'):
            module.source_version('example-pkg', 'v1.2.3', self.validation)
        self.validation['git'].side_effect = [self.commit, self.commit, '']
        self.validation['check_current'].side_effect = ValueError('mirror mismatch')
        with self.assertRaisesRegex(ValueError, 'mirror mismatch'):
            module.source_version('example-pkg', 'v1.2.3', self.validation)


class RepositorySourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.add_package('.', 'root-pkg', '1.0.0', 'v', '.github/release-policy.json')
        self.add_package('packages/alpha', 'alpha-pkg', '2.3.4', 'alpha-v', '.github/alpha.json')
        self.add_package('packages/beta', 'beta-pkg', '7.0.1', 'beta-v', '.github/beta.json')
        self.commit()
        for tag in ('v1.0.0', 'alpha-v2.3.4', 'beta-v7.0.1'):
            self.git('tag', '-a', tag, '-m', tag)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def add_package(self, directory, name, version, prefix, policy_path):
        base = '' if directory == '.' else directory + '/'
        self.write(base + 'VERSION', version)
        self.write(base + 'pyproject.toml', (
            '[build-system]\nrequires = ["setuptools", "wheel"]\nbuild-backend = "setuptools.build_meta"\n'
            f'[project]\nname = "{name}"\nversion = "{version}"\n'
            'description = "Fixture"\nreadme = "README.md"\n'
            '[tool.setuptools]\npy-modules = ["sample"]\n'))
        self.write(base + 'sample.py', 'VALUE = 1\n')
        self.write(base + 'README.md', 'Fixture package.\n')
        self.write(base + 'CHANGELOG.md', f'## [{version}]\n\n- Release {name}.\n')
        policy = {
            'release_branch': 'main', 'version': {'path': base + 'VERSION', 'format': 'text'},
            'mirrors': [{'path': base + 'pyproject.toml', 'format': 'toml', 'key': 'project.version'}],
            'tag_prefix': prefix, 'changelog': base + 'CHANGELOG.md',
            'outputs': {'github_release': True, 'packages': [name]},
        }
        self.write(policy_path, json.dumps(policy))

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')

    def source(self, name='alpha-pkg', tag='alpha-v2.3.4', directory='packages/alpha', policy='.github/alpha.json'):
        return module.source_version(name, tag, package_directory_path=directory, release_policy_path=policy)

    def test_root_defaults_are_compatible(self):
        self.assertEqual(module.source_version('root-pkg', 'v1.0.0'), '1.0.0')

    def test_nested_packages_use_independent_versions_policies_and_notes(self):
        self.assertEqual(self.source(), '2.3.4')
        self.assertEqual(self.source('beta-pkg', 'beta-v7.0.1', 'packages/beta', '.github/beta.json'), '7.0.1')

    def test_builds_root_and_nested_distributions_with_independent_versions(self):
        for directory, package, tag, policy in (
                ('.', 'root-pkg', 'v1.0.0', '.github/release-policy.json'),
                ('packages/alpha', 'alpha-pkg', 'alpha-v2.3.4', '.github/alpha.json'),
                ('packages/beta', 'beta-pkg', 'beta-v7.0.1', '.github/beta.json')):
            with self.subTest(package=package):
                version = self.source(package, tag, directory, policy)
                destination = self.root / 'built' / package
                result = subprocess.run(
                    [sys.executable, '-m', 'build', '--no-isolation', directory, '--outdir', str(destination)],
                    capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run(
                    [sys.executable, '-m', 'twine', 'check', '--strict',
                     *map(str, destination.iterdir())], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                manifest = module.distributions(package, version, destination)
                self.assertEqual(manifest['version'], version)
                self.assertEqual(len(manifest['files']), 2)

    def test_wrong_policy_package_or_tag_fails(self):
        for changes in ({'policy': '.github/beta.json'}, {'name': 'beta-pkg'}, {'tag': 'beta-v7.0.1'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.source(**changes)

    def test_invalid_directory_or_policy_path_fails_before_git(self):
        for directory in ('', '..', '../escape', '/tmp', '-option', 'packages/../alpha',
                          'packages//alpha', './packages/alpha', 'packages\\alpha',
                          'missing', 'packages/alpha/VERSION', 'packages/alpha\n'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                self.source(directory=directory)
        for policy in ('', '.', '../policy.json', '/tmp/policy.json', '-policy',
                       '.github//alpha.json', '.github/../alpha.json', '.github/alpha.json\n',
                       '.github/missing.json'):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.source(policy=policy)

    def test_directory_symlinks_inside_or_outside_repository_fail(self):
        (self.root / 'alias').symlink_to(self.root / 'packages', target_is_directory=True)
        (self.root / 'outside').symlink_to(self.root.parent, target_is_directory=True)
        for directory in ('alias/alpha', 'outside'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                self.source(directory=directory)

    def test_invalid_package_policy_version_and_notes_fail(self):
        policy = (self.root / '.github/alpha.json').read_text()
        cases = [('.github/alpha.json', '{}'), ('packages/alpha/VERSION', '2.3.4rc1'),
                 ('packages/alpha/pyproject.toml', '[project]\nversion = "9.9.9"\n'),
                 ('packages/alpha/CHANGELOG.md', '## [2.3.4]\n\n### Added\n')]
        for path, text in cases:
            original = (self.root / path).read_text()
            self.write(path, text)
            self.commit()
            self.git('tag', '-f', 'alpha-v2.3.4')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.source()
            self.write(path, original)
        self.assertEqual((self.root / '.github/alpha.json').read_text(), policy)

    def test_tag_commit_and_main_ancestry_still_required_for_nested_package(self):
        tagged = self.git('rev-parse', 'HEAD')
        self.write('unrelated', 'new commit')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'tag commit'):
            self.source()
        self.git('tag', '-f', 'alpha-v2.3.4')
        self.git('update-ref', 'refs/remotes/origin/main', tagged)
        with self.assertRaisesRegex(ValueError, 'merge-base'):
            self.source()


if __name__ == '__main__':
    unittest.main()
