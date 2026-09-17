"""Install actual .conda artifacts in clean Pixi consumers and test relocation/update."""

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from conda_package_handling.api import extract

ROOT = Path(__file__).resolve().parents[1]
PIXI = shutil.which("pixi")
RATTLER_BUILD = shutil.which("rattler-build")
SUBDIR = {("Darwin", "arm64"): "osx-arm64", ("Linux", "x86_64"): "linux-64"}.get(
    (platform.system(), platform.machine())
)
# Keep the user's home for Pixi's cache, but no build/compiler/library variables.
CLEAN = {k: os.environ[k] for k in ("HOME", "USER", "TMPDIR") if k in os.environ}
CLEAN.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", LANG="C.UTF-8")


def run(command, log, cwd=None, env=None, timeout=600, success=True):
    result = subprocess.run(
        list(map(str, command)),
        cwd=cwd,
        env=env or CLEAN,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    log.write_text(result.stdout)
    if success and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")
    return result


def artifact(path, work):
    path = Path(path).resolve(strict=True)
    # A build's --exclude-newer also excludes the just-built package in 0.68.0.
    # Run its standard recipe tests separately, without that build-solver cutoff.
    run(
        [
            RATTLER_BUILD,
            "test",
            "--package-file",
            path,
            "-c",
            "conda-forge",
            "--output-dir",
            work / "rattler-tests",
        ],
        work / (path.stem + ".recipe-test.log"),
    )
    dest = work / (path.stem + "-extracted")
    extract(str(path), dest_dir=str(dest))
    meta = json.loads((dest / "info/index.json").read_text())
    extra = json.loads((dest / "info/about.json").read_text())["extra"]
    assert meta["name"] == "raspa3" and meta["subdir"] == SUBDIR, meta
    assert meta["build"].startswith(
        f"g{extra['upstream_sha']}_r{extra['configuration_hash']}_"
    )
    assert meta["build"].endswith(f"_{meta['build_number']}")
    for relative in (
        "bin/raspa3",
        "bin/raspa3-cli",
        "libexec/raspa3/raspa3",
        "libexec/raspa3/raspa3-cli",
        "info/licenses",
    ):
        assert (dest / relative).exists(), relative
    return {
        "path": path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "meta": meta,
    }


def index_channel(channel, item, work):
    subdir = channel / SUBDIR
    subdir.mkdir(parents=True, exist_ok=True)
    (channel / "noarch").mkdir(exist_ok=True)
    target = subdir / item["path"].name
    if target.exists():
        raise RuntimeError(f"Refusing to replace existing artifact: {target}")
    shutil.copy2(item["path"], target)
    run([sys.executable, "-m", "conda_index", channel], work / "index.log")


def consumer(directory, channel, version):
    directory.mkdir()
    manifest = directory / "pixi.toml"
    manifest.write_text(
        '[workspace]\nname = "raspa-consumer"\nchannels = ['
        + json.dumps(channel.as_uri())
        + ', "conda-forge"]\nplatforms = ['
        + json.dumps(SUBDIR)
        + "]\n\n[dependencies]\nraspa3 = "
        + json.dumps("==" + version)
        + "\n"
    )
    run([PIXI, "install", "--manifest-path", manifest], directory / "install.log")
    return manifest


def installed(manifest, item, channel):
    prefix = manifest.parent / ".pixi/envs/default"
    entries = list((prefix / "conda-meta").glob("raspa3-*.json"))
    assert len(entries) == 1, entries
    meta = json.loads(entries[0].read_text())
    expected = item["meta"]
    for key in ("version", "build", "build_number", "subdir"):
        assert meta[key] == expected[key], (key, meta[key], expected[key])
    assert meta["sha256"] == item["sha256"], meta
    assert meta["url"] == (channel / SUBDIR / item["path"].name).as_uri(), meta["url"]
    # Verify the lock chose the same package, not just the installed prefix.
    lock = yaml.safe_load((manifest.parent / "pixi.lock").read_text())
    selected = lock["environments"]["default"]["packages"][SUBDIR]

    # Pixi 0.78 records local package locations as paths, remote ones as URLs.
    def location(value):
        return value if "://" in value else (manifest.parent / value).resolve().as_uri()

    urls = [location(p["conda"]) for p in selected if "conda" in p]
    assert meta["url"] in urls
    assert not any("/raspa3-" in u and u != meta["url"] for u in urls)
    records = [
        p
        for p in lock["packages"]
        if "conda" in p and location(p["conda"]) == meta["url"]
    ]
    assert len(records) == 1 and records[0]["sha256"] == item["sha256"]
    return prefix


def numbers(value):
    if isinstance(value, dict):
        for x in value.values():
            yield from numbers(x)
    elif isinstance(value, list):
        for x in value:
            yield from numbers(x)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


def pixi_command(manifest, prefix, *arguments):
    # --clean-env removes even /usr/bin from PATH. Restore only the target
    # environment and OS standard tools (the POSIX launcher uses dirname).
    return [
        PIXI,
        "run",
        "--manifest-path",
        manifest,
        "--clean-env",
        "/usr/bin/env",
        f"PATH={prefix}/bin:{CLEAN['PATH']}",
        *arguments,
    ]


def simulation(manifest, prefix, local_data, build_number):
    directory = manifest.parent / (
        str(build_number) + ("-local-example" if local_data else "-installed-data")
    )
    directory.mkdir()
    example = prefix / "share/raspa3/examples/methane-in-box"
    data = json.loads((example / "simulation.json").read_text())
    data.update(
        NumberOfProductionCycles=100,
        NumberOfInitializationCycles=20,
        NumberOfBlocks=5,
        PrintEvery=20,
        RandomSeed=42,
    )
    data["Systems"][0]["OutputPDBMovie"] = False
    if local_data:
        for name in ("force_field.json", "methane.json"):
            shutil.copy2(example / name, directory / name)
    else:
        data["ForceField"] = "example_molecule_forcefield"
        data["Components"][0]["FileName"] = (
            "share/raspa3/molecules/example_definitions/methane.json"
        )
    (directory / "simulation.json").write_text(json.dumps(data, indent=2))
    command = pixi_command(manifest, prefix, "raspa3")
    run(command, directory / "run.log", cwd=directory, timeout=180)
    text = "\n".join(p.read_text(errors="replace") for p in directory.rglob("*.txt"))
    assert "Simulation finished!" in text, directory
    assert "Final state after 100 cycles" in text, directory
    outputs = [
        json.loads(p.read_text())
        for p in directory.rglob("*.json")
        if p.name != "simulation.json"
    ]
    energies = []
    for output in outputs:
        if isinstance(output, dict) and "output" in output:
            for key in ("runningEnergies", "recomputedEnergies"):
                values = output["output"][key]
                assert "Total potential energy [K]" in values
                assert values and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in values.values()
                ), values
                energies.extend(numbers(values))
    assert energies and all(math.isfinite(v) for v in energies), directory
    if not local_data:
        # Run directly with an explicit bad data root to prove the launcher
        # preserves the override and the source tree is not a fallback.
        bad = manifest.parent / f"{build_number}-missing-data"
        bad.mkdir()
        shutil.copy2(directory / "simulation.json", bad / "simulation.json")
        env = dict(CLEAN, RASPA_DIR=str(bad))
        result = run(
            [prefix / "bin/raspa3"],
            bad / "run.log",
            cwd=bad,
            env=env,
            timeout=60,
            success=False,
        )
        assert result.returncode != 0, "Missing installed data unexpectedly succeeded"


def smoke(manifest, item, channel):
    prefix = installed(manifest, item, channel)
    for command in ("raspa3", "raspa3-cli"):
        run(
            pixi_command(manifest, prefix, command, "--help"),
            manifest.parent / f"{command}-help.log",
            timeout=60,
        )
        binary = prefix / "libexec/raspa3" / command
        if SUBDIR == "osx-arm64":
            output = run(
                ["/usr/bin/otool", "-L", binary],
                manifest.parent / f"{command}-links.log",
            ).stdout
            output += run(
                ["/usr/bin/otool", "-l", binary],
                manifest.parent / f"{command}-load.log",
            ).stdout
        else:
            output = run(
                ["/usr/bin/ldd", binary], manifest.parent / f"{command}-links.log"
            ).stdout
            output += run(
                ["/usr/bin/readelf", "-d", binary],
                manifest.parent / f"{command}-load.log",
            ).stdout
            assert "not found" not in output
        for forbidden in (
            "/opt/homebrew",
            "/usr/local/",
            "/output/bld/",
            "host_env_placehold",
            "/build_env/",
        ):
            assert forbidden not in output, (command, forbidden)
    simulation(manifest, prefix, True, item["meta"]["build_number"])
    simulation(manifest, prefix, False, item["meta"]["build_number"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--test-update", action="store_true")
    parser.add_argument("--old", type=Path)
    parser.add_argument("--new", type=Path)
    args = parser.parse_args()
    if not SUBDIR or not PIXI or not RATTLER_BUILD:
        parser.error(
            "A native osx-arm64 or linux-64 host with Pixi and rattler-build is required"
        )
    if args.test_update and not (args.old and args.new):
        parser.error("--test-update requires --old and --new actual .conda files")
    if not args.test_update and not args.package:
        parser.error("--package is required")
    (ROOT / ".work").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="verify-", dir=ROOT / ".work"))
    print(f"Verification logs: {work}", flush=True)
    old = artifact(args.old if args.test_update else args.package, work)
    channel = work / "channel"
    index_channel(channel, old, work)
    manifest = consumer(work / "consumer", channel, old["meta"]["version"])
    smoke(manifest, old, channel)
    if args.test_update:
        new = artifact(args.new, work)
        assert new["meta"]["version"] == old["meta"]["version"]
        assert new["meta"]["build_number"] > old["meta"]["build_number"]
        original_manifest = manifest.read_bytes()
        index_channel(channel, new, work)
        run(
            [PIXI, "update", "--manifest-path", manifest, "raspa3"], work / "update.log"
        )
        run(
            [PIXI, "install", "--locked", "--manifest-path", manifest],
            work / "update-install.log",
        )
        assert manifest.read_bytes() == original_manifest
        smoke(manifest, new, channel)
        old = new
    # A longer prefix with spaces exercises binary and launcher relocation.
    relocated = consumer(
        work / "relocated consumer with spaces", channel, old["meta"]["version"]
    )
    smoke(relocated, old, channel)
    report = {
        "status": "passed",
        "platform": SUBDIR,
        "update_test": args.test_update,
        "artifact": str(old["path"]),
        "sha256": old["sha256"],
        "metadata": old["meta"],
    }
    (work / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
