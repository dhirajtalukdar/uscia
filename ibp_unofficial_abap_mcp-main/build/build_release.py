"""
build_release.py -- Build standalone PyInstaller binaries for sap-ibp-abap-int.

Run from this directory (build/) with the source repo path as argument:

    python build_release.py --source-dir C:/Users/I520242/VSCode_Workspace/ibp-bud6-mcp

Produces:
    dist/sap-ibp-abap-int/         (onedir bundle)
    dist/sap-ibp-abap-int-<os>.zip (release archive with setup scripts)

Prerequisites:
    pip install pyinstaller

The script will:
1. pip install the source package into the current environment
2. Locate the installed package and data files
3. Run PyInstaller in --onedir mode
4. Package the result with setup scripts and .env.example into a release archive
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
import tarfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RELEASE_ASSETS = REPO_ROOT / "release-assets"


def find_package_dir() -> Path:
    """Find the installed sap_ibp_abap_int package directory."""
    try:
        import sap_ibp_abap_int
        return Path(sap_ibp_abap_int.__file__).resolve().parent
    except ImportError:
        print("ERROR: sap_ibp_abap_int is not installed.")
        print("Install it first:  pip install <source-dir>")
        sys.exit(1)


def install_source(source_dir: Path) -> None:
    """pip install the MCP server from source."""
    print(f"Installing sap-ibp-abap-int from {source_dir} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", str(source_dir)],
        stdout=subprocess.DEVNULL,
    )
    print("  OK")


def install_pyinstaller() -> None:
    """Ensure PyInstaller is available."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            stdout=subprocess.DEVNULL,
        )
        print("  OK")


def build_executable(pkg_dir: Path) -> Path:
    """Run PyInstaller and return the dist output directory."""
    data_dir = pkg_dir / "data"
    clean_abap = data_dir / "CleanABAP.md"

    if not clean_abap.is_file():
        print(f"WARNING: CleanABAP.md not found at {clean_abap}")
        print("  The binary will work but the CleanABAP guide will be unavailable.")

    # Determine the entry-point script
    entry_point = pkg_dir / "__main__.py"
    if not entry_point.is_file():
        # Fallback: create a tiny wrapper
        entry_point = SCRIPT_DIR / "_entry.py"
        entry_point.write_text(
            "from sap_ibp_abap_int.server import main\nmain()\n",
            encoding="utf-8",
        )

    runtime_hook = SCRIPT_DIR / "runtime_hook.py"

    # Build the PyInstaller command
    dist_dir = REPO_ROOT / "dist"
    build_dir = REPO_ROOT / "build_output"

    # Increase recursion limit for PyInstaller's deep module graph traversal
    sys.setrecursionlimit(5000)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "sap-ibp-abap-int",
        "--onedir",
        "--console",
        "--noconfirm",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        # Runtime hook for frozen-mode patches
        "--runtime-hook", str(runtime_hook),
        # Bundle CleanABAP.md into the right location
        "--add-data", f"{clean_abap}{os.pathsep}sap_ibp_abap_int/data",
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "mcp",
        "--hidden-import", "mcp.server",
        "--hidden-import", "mcp.server.fastmcp",
        "--hidden-import", "mcp.server.stdio",
        "--hidden-import", "mcp.types",
        "--hidden-import", "mcp.shared",
        "--hidden-import", "mcp.shared.session",
        "--hidden-import", "mcp.server.session",
        "--hidden-import", "mcp.server.models",
        "--hidden-import", "anyio",
        "--hidden-import", "anyio._backends",
        "--hidden-import", "anyio._backends._asyncio",
        "--hidden-import", "httpx",
        "--hidden-import", "httpcore",
        "--hidden-import", "h11",
        "--hidden-import", "pydantic",
        "--hidden-import", "pydantic.deprecated",
        "--hidden-import", "pydantic.deprecated.decorator",
        "--hidden-import", "pydantic_core",
        "--hidden-import", "annotated_types",
        "--hidden-import", "docx",
        "--hidden-import", "docx.opc",
        "--hidden-import", "docx.opc.constants",
        "--hidden-import", "docx.oxml",
        "--hidden-import", "docx.oxml.ns",
        "--hidden-import", "lxml",
        "--hidden-import", "lxml.etree",
        "--hidden-import", "starlette",
        "--hidden-import", "sse_starlette",
        "--hidden-import", "uvicorn",
        "--hidden-import", "click",
        "--hidden-import", "typing_extensions",
        # Collect all sub-packages for mcp and pydantic
        "--collect-submodules", "mcp",
        "--collect-submodules", "pydantic",
        "--collect-submodules", "anyio",
        # Exclude heavy transitive dependencies not needed at runtime
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",
        "--exclude-module", "tkinter",
        "--exclude-module", "test",
        "--exclude-module", "setuptools",
        str(entry_point),
    ]

    print("Running PyInstaller ...")
    print(f"  Entry point: {entry_point}")
    print(f"  Data:        {clean_abap}")
    print(f"  Output:      {dist_dir / 'sap-ibp-abap-int'}")
    subprocess.check_call(cmd)
    print("  OK")

    # Clean up temp entry point if we created it
    temp_entry = SCRIPT_DIR / "_entry.py"
    if temp_entry.is_file():
        temp_entry.unlink()

    return dist_dir / "sap-ibp-abap-int"


def package_release(exe_dir: Path) -> Path:
    """Package the executable with setup scripts into a release archive."""
    os_name = platform.system().lower()
    if os_name == "windows":
        os_label = "windows"
    elif os_name == "darwin":
        os_label = "macos"
    else:
        os_label = "linux"

    # Copy setup scripts and .env.example into the exe directory
    if os_name == "windows":
        setup_script = RELEASE_ASSETS / "setup.bat"
    else:
        setup_script = RELEASE_ASSETS / "setup.sh"

    env_example = RELEASE_ASSETS / ".env.example"

    if setup_script.is_file():
        shutil.copy2(setup_script, exe_dir / setup_script.name)
    if env_example.is_file():
        shutil.copy2(env_example, exe_dir / ".env.example")

    # Create archive
    archive_name = f"sap-ibp-abap-int-{os_label}"
    dist_dir = exe_dir.parent

    if os_name == "windows":
        archive_path = dist_dir / f"{archive_name}.zip"
        print(f"Creating {archive_path.name} ...")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(exe_dir):
                for file in files:
                    filepath = Path(root) / file
                    arcname = f"sap-ibp-abap-int/{filepath.relative_to(exe_dir)}"
                    zf.write(filepath, arcname)
        print(f"  OK  ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        archive_path = dist_dir / f"{archive_name}.tar.gz"
        print(f"Creating {archive_path.name} ...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(exe_dir, arcname="sap-ibp-abap-int")
        print(f"  OK  ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")

    return archive_path


def main():
    parser = argparse.ArgumentParser(
        description="Build standalone PyInstaller release for sap-ibp-abap-int"
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Path to the ibp-bud6-mcp source repo (containing pyproject.toml)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip pip install (assumes package is already installed)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not (source_dir / "pyproject.toml").is_file():
        print(f"ERROR: {source_dir}/pyproject.toml not found.")
        print("  Provide the path to the ibp-bud6-mcp source repo.")
        sys.exit(1)

    # Step 1: Install dependencies
    if not args.skip_install:
        install_source(source_dir)
    install_pyinstaller()

    # Step 2: Find the installed package
    pkg_dir = find_package_dir()
    print(f"Package found at: {pkg_dir}")

    # Step 3: Build executable
    exe_dir = build_executable(pkg_dir)

    # Step 4: Package release
    archive = package_release(exe_dir)

    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print(f"  Executable: {exe_dir}")
    print(f"  Archive:    {archive}")
    print()
    print("Upload the archive to a GitHub Release:")
    print("  https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/releases/new")
    print("=" * 60)


if __name__ == "__main__":
    main()
