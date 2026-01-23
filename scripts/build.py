import pathlib
import subprocess
import sys
import tomllib
from enum import Enum, auto

import semver
import tomli_w


class BumpType(Enum):
    MINOR = auto()
    MAJOR = auto()


def update_versions_toml():
    path = "../cli/versions.toml"
    toml_txt = pathlib.Path(path).read_text()
    toml = tomllib.loads(toml_txt)
    toml["release_version"] = str(
        semver.VersionInfo.parse(toml["release_version"]).bump_patch()
    )
    sdk_ver = toml["sdk"]["version"]
    toml["sdk"]["version"] = str(
        semver.VersionInfo.parse(toml["sdk"]["version"]).bump_patch()
    )
    toml["sdk"]["wheel_url"] = toml["sdk"]["wheel_url"].replace(
        sdk_ver, toml["sdk"]["version"]
    )
    cli_ver = toml["cli"]["version"]
    toml["cli"]["version"] = str(
        semver.VersionInfo.parse(toml["cli"]["version"]).bump_patch()
    )
    toml["cli"]["wheel_url"] = toml["cli"]["wheel_url"].replace(
        cli_ver, toml["cli"]["version"]
    )
    engine_ver = toml["engine"]["version"]
    toml["engine"]["version"] = str(
        semver.VersionInfo.parse(toml["engine"]["version"]).bump_patch()
    )
    toml["engine"]["wheel_url"] = toml["engine"]["wheel_url"].replace(
        engine_ver, toml["engine"]["version"]
    )
    shared_ver = toml["shared"]["version"]
    toml["shared"]["version"] = str(
        semver.VersionInfo.parse(toml["shared"]["version"]).bump_patch()
    )
    toml["shared"]["wheel_url"] = toml["shared"]["wheel_url"].replace(
        shared_ver, toml["shared"]["version"]
    )
    print("versions.toml:", tomli_w.dumps(toml))
    pathlib.Path(path).write_text(tomli_w.dumps(toml))
    pathlib.Path("../versions.toml").write_text(tomli_w.dumps(toml))
    return toml["shared"]["version"]


def update_pyproject_toml():
    path = "../engine/shared/pyproject.toml"
    shared_txt = pathlib.Path(path).read_text()
    shared = tomllib.loads(shared_txt)
    shared_start_version = str(semver.VersionInfo.parse(shared["project"]["version"]))
    shared["project"]["version"] = str(
        semver.VersionInfo.parse(shared["project"]["version"]).bump_patch()
    )
    pathlib.Path(path).write_text(tomli_w.dumps(shared))

    path = "../engine/sdk/pyproject.toml"
    sdk_txt = pathlib.Path(path).read_text()
    sdk = tomllib.loads(sdk_txt)
    sdk["project"]["version"] = str(
        semver.VersionInfo.parse(sdk["project"]["version"]).bump_patch()
    )
    for i, dep in enumerate(sdk["project"]["dependencies"]):
        if dep.startswith("shared=="):
            sdk["project"]["dependencies"][i] = dep.replace(
                shared_start_version, shared["project"]["version"]
            )
    pathlib.Path(path).write_text(tomli_w.dumps(sdk))

    path = "../engine/inference/pyproject.toml"
    engine_txt = pathlib.Path(path).read_text()
    engine = tomllib.loads(engine_txt)
    engine["project"]["version"] = str(
        semver.VersionInfo.parse(engine["project"]["version"]).bump_patch()
    )
    for i, dep in enumerate(sdk["project"]["dependencies"]):
        if dep.startswith("shared=="):
            engine["project"]["dependencies"][i] = dep.replace(
                shared_start_version, shared["project"]["version"]
            )
    pathlib.Path(path).write_text(tomli_w.dumps(engine))

    print("shared.toml:", tomli_w.dumps(shared))
    print("sdk.toml:", tomli_w.dumps(sdk))
    print("engine.toml:", tomli_w.dumps(engine))


def remove_artifacts():
    result = subprocess.run(["rm", "-rf", "../artifacts/*"])
    print("remove artifacts:", result)
    return result.returncode


def run_build():
    result = subprocess.run(["bash", "./build.sh"])
    return result.returncode


def run_publish(tag):
    result = subprocess.run(["bash", "./publish.sh", "--tag", f"{tag}"])
    print("publish:", result)
    return result.returncode


def gh_release(tag):
    result = subprocess.run(
        [
            "gh",
            "release",
            "create",
            f"{tag}",
            "--repo",
            "concordance-co/concordance-artifacts",
        ]
    )
    return result.returncode


if __name__ == "__main__":
    ver = update_versions_toml()
    update_pyproject_toml()
    tag = "v" + ver
    if gh_release(tag) != 0:
        print("error creating gh release")
        sys.exit(1)
    if remove_artifacts() != 0:
        print("error removing artifacts")
        sys.exit(1)
    if run_build() != 0:
        print("error running build")
        sys.exit(1)
    if run_publish(tag) != 0:
        print("error running build")
        sys.exit(1)
    pathlib.Path("../VERSION").write_text(ver)
