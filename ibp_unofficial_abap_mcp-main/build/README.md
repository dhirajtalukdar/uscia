# Building a release

## Quick release (recommended)

Build everything — MCP server binary + VS Code extension — in one command:

```bash
python build/release_all.py 1.3.0
```

This will:
1. Bump version in `pyproject.toml` and `package.json`
2. Clean `dist/` and `build_output/`
3. Build the MCP server standalone binary via PyInstaller
4. Build the VS Code extension `.vsix` via `vsce`
5. Package both into `dist/` with versioned zip archives

Output:
- `dist/sap-ibp-abap-int-windows-1.3.0.zip` (MCP server)
- `dist/ibp-abap-intelligence-1.3.0.zip` (VS Code extension + INSTALL.md)

### Partial builds

```bash
python build/release_all.py 1.3.0 --skip-pyinstaller   # extension only
python build/release_all.py 1.3.0 --skip-extension      # MCP binary only
```

## Prerequisites

- Python 3.10+ with pip
- Node.js with npx (for `vsce package`)
- Source repos as sibling directories:
  - `ibp-bud6-mcp/` (MCP server)
  - `ibp-abap-intelligence/` (VS Code extension)
  - `ibp_unofficial_abap_mcp/` (this repo)

## Upload to GitHub Release

1. Go to [Releases](https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/releases/new)
2. Create a new tag (e.g., `v1.3.0`)
3. Upload both zip archives from `dist/`
4. Publish the release

## MCP server binary only (advanced)

If you only need the PyInstaller binary without version bumping:

```bash
python build/build_release.py --source-dir /path/to/ibp-bud6-mcp
```

## Building for a different platform

PyInstaller produces binaries for the platform you run it on. To build for both Windows and macOS, run the build script on each platform separately.

## Troubleshooting

### MCP server exe is locked

If pip install fails with "file is being used by another process", kill running `sap-ibp-abap-int.exe` processes first:

```bash
taskkill /F /IM sap-ibp-abap-int.exe
```

### Missing hidden imports

If the built executable fails with `ModuleNotFoundError`, add the missing module to the `--hidden-import` list in `build_release.py` and rebuild.

### Large binary size

The `--onedir` bundle includes the Python runtime and all dependencies. Typical size is 50-65 MB compressed. This is expected.
