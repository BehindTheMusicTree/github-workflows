"""Exercise API failures and interleavings without creating remote tags."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

spec = importlib.util.spec_from_file_location("tagger", Path(__file__).with_name("create-tag.py"))
tagger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tagger)
COMMIT = "a" * 40
OTHER = "b" * 40
OBJECT = "c" * 40


class FakeGitHub:
    def __init__(self):
        self.refs = {}
        self.tags = {}
        self.calls = []
        self.failure = None
        self.race = None
        self.lag = 0
        self.tag_lag = 0
        self.bad_tag_object = None
        self.bad_ref_response = None

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if self.failure:
            raise tagger.APIError(self.failure)
        if path.startswith("/git/ref/tags/"):
            name = path.removeprefix("/git/ref/tags/")
            if name not in self.refs:
                raise tagger.APIError(404)
            if self.lag:
                self.lag -= 1
                raise tagger.APIError(404)
            return {"object": self.refs[name]}
        if path.startswith("/git/tags/"):
            if self.tag_lag:
                self.tag_lag -= 1
                raise tagger.APIError(404)
            return {"object": self.tags[path.removeprefix("/git/tags/")]}
        if path == "/git/tags":
            sha = f"{len(self.tags) + 1:040x}"
            self.tags[sha] = {"type": "commit", "sha": data["object"]}
            return {"sha": sha, "object": self.bad_tag_object or {**self.tags[sha], "url": "https://api.github.com/x"}}
        if path == "/git/refs":
            name = data["ref"].removeprefix("refs/tags/")
            if self.race:
                self.refs[name] = {"type": "commit", "sha": self.race}
                raise tagger.APIError(422)
            self.refs[name] = {"type": "tag", "sha": data["sha"]}
            if self.bad_ref_response is not None:
                return self.bad_ref_response
            return {"ref": data["ref"], "object": {**self.refs[name], "url": "https://api.github.com/x"}}
        raise AssertionError((method, path, data))


class TagCreationTest(unittest.TestCase):
    def test_annotated_creation_and_retry(self):
        api = FakeGitHub()
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT), "created")
        self.assertEqual(api.refs["v1.1.0"]["type"], "tag")
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT), "existing")
        self.assertEqual(sum(method == "POST" for method, _, _ in api.calls), 2)

    def test_lightweight_retry_and_collision(self):
        api = FakeGitHub()
        api.refs["v1.1.0"] = {"type": "commit", "sha": COMMIT}
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT), "existing")
        with self.assertRaisesRegex(ValueError, "collision"):
            tagger.create_tag(api, "v1.1.0", OTHER)
        self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_atomic_collision_same_and_different_sha(self):
        for target in (COMMIT, OTHER):
            with self.subTest(target=target):
                api = FakeGitHub()
                api.race = target
                if target == COMMIT:
                    self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT), "existing")
                else:
                    with self.assertRaisesRegex(ValueError, "collision"):
                        tagger.create_tag(api, "v1.1.0", COMMIT)

    def test_two_close_bumps_keep_event_commits(self):
        api = FakeGitHub()
        tagger.create_tag(api, "v1.1.0", COMMIT)
        tagger.create_tag(api, "v1.2.0", OTHER)
        targets = [data["object"] for method, path, data in api.calls if method == "POST" and path == "/git/tags"]
        self.assertEqual(targets, [COMMIT, OTHER])
        self.assertEqual(tagger.existing_commit(api, "v1.1.0"), COMMIT)
        self.assertEqual(tagger.existing_commit(api, "v1.2.0"), OTHER)

    def test_nested_tag_and_cycle(self):
        api = FakeGitHub()
        api.refs["v1.1.0"] = {"type": "tag", "sha": OBJECT}
        api.tags[OBJECT] = {"type": "tag", "sha": OTHER}
        api.tags[OTHER] = {"type": "commit", "sha": COMMIT}
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT), "existing")
        api.tags[OTHER] = {"type": "tag", "sha": OBJECT}
        with self.assertRaisesRegex(ValueError, "chain"):
            tagger.create_tag(api, "v1.1.0", COMMIT)

    def test_api_errors_do_not_mean_absence(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                api = FakeGitHub()
                api.failure = status
                with self.assertRaises(tagger.APIError):
                    tagger.create_tag(api, "v1.1.0", COMMIT)
                self.assertEqual(len(api.calls), 1)

    def test_ref_validation_failure_is_not_success(self):
        api = FakeGitHub()
        original = api.request

        def request(method, path, data=None):
            if path == "/git/refs":
                raise tagger.APIError(422)
            return original(method, path, data)

        api.request = request
        with self.assertRaises(tagger.APIError):
            tagger.create_tag(api, "v1.1.0", COMMIT, sleep=lambda _: None)

    def test_read_lag_after_creation_is_tolerated(self):
        for lag in (1, 3, 5):
            with self.subTest(lag=lag):
                api = FakeGitHub()
                api.lag = lag
                waits = []
                self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT, sleep=waits.append), "created")
                self.assertEqual(waits, [1, 2, 4, 8, 8][:lag])

    def test_tag_object_read_lag_is_tolerated(self):
        api = FakeGitHub()
        original = api.request

        def request(method, path, data=None):
            if path == "/git/refs":
                result = original(method, path, data)
                api.tag_lag = 2
                return result
            return original(method, path, data)

        api.request = request
        waits = []
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT, sleep=waits.append), "created")
        self.assertEqual(waits, [1, 2])

    def test_read_lag_beyond_attempts_fails_with_rerun_hint(self):
        api = FakeGitHub()
        api.lag = 6
        waits = []
        with self.assertRaisesRegex(ValueError, "rerun the job"):
            tagger.create_tag(api, "v1.1.0", COMMIT, sleep=waits.append)
        self.assertEqual(waits, [1, 2, 4, 8, 8])

    def test_read_lag_on_atomic_collision_is_existing(self):
        api = FakeGitHub()
        api.race = COMMIT
        api.lag = 2
        self.assertEqual(tagger.create_tag(api, "v1.1.0", COMMIT, sleep=lambda _: None), "existing")

    def test_mismatch_after_lag_fails_without_waiting_further(self):
        api = FakeGitHub()
        api.race = OTHER
        api.lag = 1
        waits = []
        with self.assertRaisesRegex(ValueError, "collision"):
            tagger.create_tag(api, "v1.1.0", COMMIT, sleep=waits.append)
        self.assertEqual(waits, [1])

    def test_malformed_write_responses_fail(self):
        api = FakeGitHub()
        api.bad_tag_object = {"type": "commit", "sha": OTHER}
        with self.assertRaisesRegex(ValueError, "annotated tag"):
            tagger.create_tag(api, "v1.1.0", COMMIT, sleep=lambda _: None)
        for response in ({}, {"ref": "refs/tags/other", "object": {"type": "tag", "sha": "1" * 40}}):
            with self.subTest(response=response):
                api = FakeGitHub()
                api.bad_ref_response = response
                with self.assertRaisesRegex(ValueError, "created ref"):
                    tagger.create_tag(api, "v1.1.0", COMMIT, sleep=lambda _: None)

    def test_missing_token_and_invalid_inputs(self):
        with self.assertRaisesRegex(ValueError, "token missing"):
            tagger.GitHub("owner/repo", "", "https://api.github.com")
        for tag, commit in (("v1.2.3\n", COMMIT), ("v1.0.0", "main"), ("v1.0.0", "0" * 40)):
            with self.subTest(tag=tag, commit=commit), self.assertRaises(ValueError):
                tagger.create_tag(FakeGitHub(), tag, commit)

    def test_transport_errors_propagate_and_auth_is_not_logged(self):
        api = tagger.GitHub("owner/repo", "private-token", "https://api.github.com")
        with patch.object(tagger, "urlopen", side_effect=URLError("network unavailable")):
            with self.assertRaises(URLError):
                api.request("GET", "/git/ref/tags/v1.0.0")
        with patch.object(tagger, "urlopen", side_effect=HTTPError("url", 403, "private-token", {}, None)):
            with self.assertRaises(tagger.APIError) as caught:
                api.request("GET", "/git/ref/tags/v1.0.0")
            self.assertNotIn("private-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
