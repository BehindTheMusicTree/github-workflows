#!/usr/bin/env python3
"""Create an immutable annotated release tag; never build or publish artifacts."""

import json
import os
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class APIError(ValueError):
    def __init__(self, status):
        super().__init__(f"GitHub API request failed (HTTP {status})")
        self.status = status


class GitHub:
    def __init__(self, repository, token, api_url):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository")
        if not token:
            raise ValueError("release App token missing")
        if not api_url.startswith("https://"):
            raise ValueError("GitHub API URL must use HTTPS")
        self.base = f"{api_url.rstrip('/')}/repos/{repository}"
        self.token = token

    def request(self, method, path, data=None):
        request = Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise APIError(exc.code) from None


def existing_commit(api, tag):
    try:
        obj = api.request("GET", "/git/ref/tags/" + quote(tag, safe=""))["object"]
    except APIError as exc:
        if exc.status == 404:
            return None
        raise
    seen = set()
    while obj["type"] == "tag":
        sha = obj["sha"]
        if sha in seen or len(seen) >= 20 or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("invalid annotated tag chain")
        seen.add(sha)
        obj = api.request("GET", "/git/tags/" + sha)["object"]
    if obj["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", obj["sha"]):
        raise ValueError("release tag must resolve to a commit")
    return obj["sha"]


def points_to(obj, kind, sha):
    # GitHub adds fields such as "url" to object; compare only the identity.
    return isinstance(obj, dict) and obj.get("type") == kind and obj.get("sha") == sha


def wait_for_commit(api, tag, commit, sleep=time.sleep, attempts=6):
    # GitHub reads can lag right after a successful write: tolerate 404, never a mismatch.
    delay = 1
    for attempt in range(attempts):
        try:
            current = existing_commit(api, tag)
        except APIError as exc:
            # The tag object itself can lag behind the ref that points to it.
            if exc.status != 404:
                raise
            current = None
        if current is not None:
            if current != commit:
                raise ValueError("release tag collision: tag targets another commit")
            return current
        if attempt < attempts - 1:
            sleep(delay)
            delay = min(delay * 2, 8)
    return None


def create_tag(api, tag, commit, sleep=time.sleep):
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag):
        raise ValueError("invalid stable release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit == "0" * 40:
        raise ValueError("invalid commit SHA")
    current = existing_commit(api, tag)
    if current is not None:
        if current != commit:
            raise ValueError("release tag collision: existing tag targets another commit")
        return "existing"
    annotated = api.request("POST", "/git/tags", {
        "tag": tag, "message": f"Release {tag}", "object": commit, "type": "commit",
    })
    sha = annotated["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("invalid tag object SHA returned by GitHub")
    if not points_to(annotated.get("object"), "commit", commit):
        raise ValueError("annotated tag does not target the expected commit")
    try:
        created = api.request("POST", "/git/refs", {"ref": "refs/tags/" + tag, "sha": sha})
    except APIError as exc:
        # Another run may win the atomic ref creation. Only the same commit is a retry.
        if exc.status != 422:
            raise
        if wait_for_commit(api, tag, commit, sleep) is None:
            raise exc
        return "existing"
    if created.get("ref") != "refs/tags/" + tag or not points_to(created.get("object"), "tag", sha):
        raise ValueError("created ref does not match the annotated tag")
    if wait_for_commit(api, tag, commit, sleep) is None:
        raise ValueError("created tag not readable yet; rerun the job to verify")
    return "created"


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("usage: create-tag.py TAG COMMIT")
        api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["RELEASE_APP_TOKEN"], os.environ["GITHUB_API_URL"])
        sys.stdout.write(create_tag(api, *sys.argv[1:]) + "\n")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        sys.stderr.write(f"release tag creation failed: {exc}\n")
        sys.exit(1)
