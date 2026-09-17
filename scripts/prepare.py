"""Generate standard rattler variants for one fixed revision; no remote writes."""

import argparse
import hashlib
import json
import platform
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def configuration_hash():
    paths = [ROOT / p for p in ("config.toml", "pixi.toml", "pixi.lock")]
    for directory in ("recipe", "scripts", "tests", ".github"):
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )
    digest = hashlib.sha256()
    for path in sorted(paths):
        name = path.relative_to(ROOT).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-number", type=int)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".work")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check a frozen run manifest against this checkout",
    )
    args = parser.parse_args()
    work = args.output_dir
    frozen = json.loads((work / "run.json").read_text()) if args.check else None
    number = (
        args.build_number
        if args.build_number is not None
        else (frozen["nightly_build_number"] if frozen else 0)
    )
    if number < 0:
        parser.error("build number must be nonnegative")
    config = tomllib.loads((ROOT / "config.toml").read_text())
    config["configuration_hash"] = configuration_hash()
    config["nightly_build_number"] = number
    if args.check:
        assert frozen == config, (
            "Frozen build inputs do not match this checkout/configuration"
        )
    work.mkdir(parents=True, exist_ok=True)
    native = {("Darwin", "arm64"): "osx-arm64", ("Linux", "x86_64"): "linux-64"}.get(
        (platform.system(), platform.machine())
    )
    pattern = f"**/{native}/raspa3-{config['upstream_version']}-g{config['upstream_sha']}_r{config['configuration_hash']}_*_{number}.conda"
    existing = list((ROOT / "output").glob(pattern))
    if existing:
        raise RuntimeError(
            f"Artifact already exists; choose a new build number: {existing}"
        )
    if args.check:
        print(
            "Frozen inputs match this checkout; no existing artifact will be overwritten"
        )
        return
    (work / "run-variants.yaml").write_text(
        yaml.safe_dump({k: [v] for k, v in config.items()})
    )
    (work / "run.json").write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
