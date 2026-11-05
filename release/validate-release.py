#!/usr/bin/env python3
"""Validate a push's release intent without credentials or side effects."""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import PurePosixPath

SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def repository_path(path):
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("-")
        or PurePosixPath(path).is_absolute()
        or any(part in ("", ".", "..") for part in path.split("/"))
        or any(char in path for char in ":\\\r\n\0")
    ):
        raise ValueError("invalid repository path")
    return path


def read_file(commit, path):
    return git("show", f"{commit}:{repository_path(path)}")


def source_config(source):
    if not isinstance(source, dict) or set(source) not in ({"path", "format"}, {"path", "format", "key"}):
        raise ValueError("invalid version source")
    repository_path(source["path"])
    fmt = source["format"]
    if fmt == "text" and "key" not in source:
        return
    if fmt not in ("json", "toml") or not isinstance(source.get("key"), str):
        raise ValueError("invalid version format or key")
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in source["key"].split(".")):
        raise ValueError("invalid version key")


def version_at(commit, source):
    source_config(source)
    data = read_file(commit, source["path"])
    fmt = source["format"]
    if fmt == "text":
        version = data.strip()
    else:
        obj = json.loads(data) if fmt == "json" else tomllib.loads(data)
        for part in source["key"].split("."):
            if not isinstance(obj, dict) or part not in obj:
                raise ValueError("version key missing")
            obj = obj[part]
        version = obj
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError("version must be stable SemVer without leading zeroes")
    return version


def policy_at(commit, path):
    policy = json.loads(read_file(commit, path))
    fields = {"release_branch", "version", "mirrors", "tag_prefix", "changelog", "outputs"}
    if not isinstance(policy, dict) or set(policy) != fields or policy["release_branch"] != "main":
        raise ValueError("invalid release policy")
    source_config(policy["version"])
    prefix = policy["tag_prefix"]
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", prefix):
        raise ValueError("invalid tag prefix")
    mirrors = policy["mirrors"]
    if not isinstance(mirrors, list):
        raise ValueError("invalid mirrors")
    sources = [policy["version"]]
    for mirror in mirrors:
        source_config(mirror)
        if mirror in sources:
            raise ValueError("duplicate version source")
        sources.append(mirror)
    repository_path(policy["changelog"])
    outputs = policy["outputs"]
    if (
        not isinstance(outputs, dict)
        or set(outputs) != {"github_release", "packages"}
        or type(outputs["github_release"]) is not bool
        or not isinstance(outputs["packages"], list)
        or any(not isinstance(p, str) or not p.strip() or "\n" in p for p in outputs["packages"])
        or len(set(outputs["packages"])) != len(outputs["packages"])
    ):
        raise ValueError("invalid outputs")
    return policy


def check_current(commit, policy):
    version = version_at(commit, policy["version"])
    for mirror in policy["mirrors"]:
        if version_at(commit, mirror) != version:
            raise ValueError("version mirror mismatch")
    changelog = read_file(commit, policy["changelog"])
    sections = list(re.finditer(r"^## \[" + re.escape(version) + r"\](?:[^\S\n][^\n]*)?$", changelog, re.MULTILINE))
    if len(sections) != 1:
        raise ValueError("exactly one versioned changelog section required")
    body = re.split(r"^## ", changelog[sections[0].end():], maxsplit=1, flags=re.MULTILINE)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    if not any(line.strip() and not line.lstrip().startswith("#") for line in body.splitlines()):
        raise ValueError("versioned changelog section is empty")
    git("check-ref-format", f"refs/tags/{policy['tag_prefix']}{version}")
    return version


def validate(before, after, policy_path):
    for sha in (before, after):
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or sha == "0" * 40:
            raise ValueError("push requires two exact nonzero commit SHAs")
        if git("cat-file", "-t", sha).strip() != "commit":
            raise ValueError("push SHA must identify a commit")
    git("merge-base", "--is-ancestor", before, after)
    git("merge-base", "--is-ancestor", after, "refs/remotes/origin/main")
    policy = policy_at(after, policy_path)
    new = check_current(after, policy)
    # Activation never publishes the pre-existing version, even without a tag.
    paths = git("ls-tree", "--name-only", before, "--", repository_path(policy_path)).splitlines()
    if policy_path not in paths:
        return {"release": False}
    previous = policy_at(before, policy_path)
    old = check_current(before, previous)
    if old == new:
        return {"release": False}
    if policy != previous:
        raise ValueError("release policy changes and version bumps require separate pushes")
    if tuple(map(int, new.split("."))) <= tuple(map(int, old.split("."))):
        raise ValueError("version must increase")
    return {"release": True, "version": new, "tag": policy["tag_prefix"] + new, "commit": after}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("usage: validate-release.py BEFORE AFTER POLICY_PATH")
        sys.stdout.write(json.dumps(validate(*sys.argv[1:])) + "\n")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        sys.stderr.write(f"release validation failed: {exc}\n")
        sys.exit(1)
