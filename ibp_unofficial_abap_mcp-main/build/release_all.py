"""
release_all.py -- Build a complete release: MCP server binary + VS Code extension.

Usage:
    python build/release_all.py 1.2.0
    python build/release_all.py 1.3.0 --skip-pyinstaller   # extension only
    python build/release_all.py 1.3.0 --skip-extension      # MCP binary only

What it does:
    1. Bumps version in pyproject.toml (MCP server) and package.json (extension)
    2. Builds the MCP server standalone binary via build_release.py / PyInstaller
    3. Builds the VS Code extension .vsix via vsce
    4. Packages both into dist/ with versioned zip archives and INSTALL.md
    5. Prints a summary with file sizes and the GitHub Releases upload URL

Expects the following repo layout (sibling directories):
    ibp-bud6-mcp/              -- MCP server source (pyproject.toml)
    ibp-abap-intelligence/     -- VS Code extension source (package.json)
    ibp_unofficial_abap_mcp/   -- this repo (build/, dist/, docs/)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT.parent

MCP_SOURCE = WORKSPACE / "ibp-bud6-mcp"
EXT_SOURCE = WORKSPACE / "ibp-abap-intelligence"
DIST_DIR = REPO_ROOT / "dist"
BUILD_OUTPUT = REPO_ROOT / "build_output"


def check_prerequisites():
    """Verify source repos and tools exist."""
    errors = []

    if not (MCP_SOURCE / "pyproject.toml").is_file():
        errors.append(f"MCP server source not found at {MCP_SOURCE}")

    if not (EXT_SOURCE / "package.json").is_file():
        errors.append(f"Extension source not found at {EXT_SOURCE}")

    for cmd, name in [("python", "Python"), ("node", "Node.js"), ("npx", "npx")]:
        if shutil.which(cmd) is None:
            errors.append(f"{name} ({cmd}) not found in PATH")

    if errors:
        print("ERROR: Prerequisites not met:\n")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


def bump_version_pyproject(version: str):
    """Update version in pyproject.toml."""
    path = MCP_SOURCE / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        print(f"WARNING: Could not find version field in {path}")
        return
    path.write_text(new_text, encoding="utf-8")
    print(f"  pyproject.toml -> {version}")


def bump_version_package_json(version: str):
    """Update version in package.json."""
    path = EXT_SOURCE / "package.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  package.json   -> {version}")


def clean_dist():
    """Remove old dist/ and build_output/ contents."""
    for d in [DIST_DIR, BUILD_OUTPUT]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    print("  Cleaned dist/ and build_output/")


def build_mcp_server(version: str) -> Path:
    """Build MCP server binary via build_release.py. Returns archive path."""
    print("\n  Running build_release.py (this takes 2-4 minutes)...")
    subprocess.check_call(
        [
            sys.executable,
            str(SCRIPT_DIR / "build_release.py"),
            "--source-dir",
            str(MCP_SOURCE),
        ],
        cwd=str(SCRIPT_DIR),
    )

    # build_release.py creates sap-ibp-abap-int-windows.zip (no version).
    # Rename to include version.
    os_label = _os_label()
    old_name = DIST_DIR / f"sap-ibp-abap-int-{os_label}.zip"
    if not old_name.exists():
        old_name = DIST_DIR / f"sap-ibp-abap-int-{os_label}.tar.gz"
    ext = old_name.suffix if old_name.suffix != ".gz" else ".tar.gz"
    new_name = DIST_DIR / f"sap-ibp-abap-int-{os_label}-{version}{ext}"
    old_name.rename(new_name)
    print(f"  Archive: {new_name.name} ({new_name.stat().st_size / 1024 / 1024:.1f} MB)")
    return new_name


def build_extension(version: str) -> Path:
    """Build VS Code extension .vsix and package into a zip. Returns archive path."""
    print("\n  Running vsce package...")
    subprocess.check_call(
        ["npx", "vsce", "package"],
        cwd=str(EXT_SOURCE),
        shell=True,
    )

    vsix_name = f"ibp-abap-intelligence-{version}.vsix"
    vsix_path = EXT_SOURCE / vsix_name

    if not vsix_path.is_file():
        print(f"ERROR: Expected .vsix not found at {vsix_path}")
        sys.exit(1)

    # Stage into dist/ibp-abap-intelligence/
    staging = DIST_DIR / "ibp-abap-intelligence"
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copy2(vsix_path, staging / vsix_name)
    _write_install_md(staging, version)

    # Create zip archive
    archive = DIST_DIR / f"ibp-abap-intelligence-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(staging):
            for f in files:
                filepath = Path(root) / f
                arcname = f"ibp-abap-intelligence/{filepath.relative_to(staging)}"
                zf.write(filepath, arcname)

    print(f"  Archive: {archive.name} ({archive.stat().st_size / 1024:.1f} KB)")

    # Clean up .vsix from extension source dir
    vsix_path.unlink(missing_ok=True)

    return archive


def _write_install_md(staging: Path, version: str):
    """Generate INSTALL.md for the extension zip."""
    (staging / "INSTALL.md").write_text(
        f"""# IBP ABAP Intelligence — VS Code Extension

## Installation

1. Open VS Code
2. Press `Ctrl+Shift+P` → "Extensions: Install from VSIX..."
3. Select `ibp-abap-intelligence-{version}.vsix`
4. Reload VS Code

## Prerequisites

The extension requires the **SAP IBP ABAP MCP Server** to be running.
Install it from the `sap-ibp-abap-int-windows-{version}.zip` release or from source.
""",
        encoding="utf-8",
    )


def _os_label() -> str:
    import platform
    name = platform.system().lower()
    if name == "windows":
        return "windows"
    elif name == "darwin":
        return "macos"
    return "linux"


def print_summary(version: str, artifacts: list[Path]):
    """Print final summary."""
    print()
    print("=" * 64)
    print(f"  RELEASE {version} BUILD COMPLETE")
    print("=" * 64)
    print()
    for a in artifacts:
        size = a.stat().st_size
        if size > 1024 * 1024:
            label = f"{size / 1024 / 1024:.1f} MB"
        else:
            label = f"{size / 1024:.1f} KB"
        print(f"  {a.name:50s} {label}")
    print()
    print("  Upload to GitHub Releases:")
    print("  https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/releases/new")
    print(f"  Tag: v{version}")
    print()
    print("=" * 64)


def main():
    parser = argparse.ArgumentParser(
        description="Build a complete release: MCP server + VS Code extension",
    )
    parser.add_argument(
        "version",
        help="Version number (e.g. 1.2.0)",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="Skip the MCP server PyInstaller build",
    )
    parser.add_argument(
        "--skip-extension",
        action="store_true",
        help="Skip the VS Code extension build",
    )
    args = parser.parse_args()

    version = args.version
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        print(f"ERROR: Invalid version '{version}'. Expected format: X.Y.Z")
        sys.exit(1)

    print(f"\nBuilding release v{version}")
    print("-" * 40)

    check_prerequisites()

    print("\n[1/4] Bumping versions...")
    bump_version_pyproject(version)
    bump_version_package_json(version)

    print("\n[2/4] Cleaning build artifacts...")
    clean_dist()

    artifacts = []

    if not args.skip_pyinstaller:
        print("\n[3/4] Building MCP server binary...")
        artifacts.append(build_mcp_server(version))
    else:
        print("\n[3/4] Skipping MCP server binary (--skip-pyinstaller)")

    if not args.skip_extension:
        print("\n[4/4] Building VS Code extension...")
        artifacts.append(build_extension(version))
    else:
        print("\n[4/4] Skipping VS Code extension (--skip-extension)")

    print_summary(version, artifacts)


if __name__ == "__main__":
    main()
