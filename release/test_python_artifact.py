import hashlib
import importlib.util
import io
import json
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


if __name__ == '__main__':
    unittest.main()
