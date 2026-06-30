# SAP IBP ABAP MCP Server (Unofficial)

> **Unofficial MCP server -- intended for investigation and non-productive code only. Not an official SAP product.**

MCP server that gives AI coding assistants (Claude Code, Cline, GitHub Copilot) access to SAP IBP ABAP source code via the ADT REST API. Fetches any ADT-discoverable object on demand, caches locally in SQLite, and works offline with previously cached objects.

**Documentation & feature overview:** [pages.github.tools.sap/I520242/ibp_unofficial_abap_mcp](https://pages.github.tools.sap/I520242/ibp_unofficial_abap_mcp/)

---

## Installation

### Option 1 -- Standalone binary (Windows)

Download the latest release from the [Releases](https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/releases) page.

1. Download `sap-ibp-abap-int-windows.zip` from the latest release
2. Extract the zip to a folder, e.g. `C:\Tools\sap-ibp-abap-int\`
3. Double-click **`setup.bat`**
4. Follow the prompts to enter your SAP credentials and register with your AI client

### Option 2 -- Install from source (macOS / Linux / Windows with Python 3.10+)

```bash
git clone https://github.tools.sap/I520242/ibp-bud6-mcp.git
cd ibp-bud6-mcp
pip install .
```

Then register with Claude Code:

```bash
claude mcp add SAP-IBP-ABAP-INT -s user -- sap-ibp-abap-int --env-file /path/to/.env
```

---

## Configuration

Create a `.env` file with your SAP ADT credentials:

```
SAP_BASE_URL=https://your-sap-system.sap.corp
SAP_USERNAME=your_user
SAP_PASSWORD=your_password
```

> Without credentials the server starts in **cache-only mode** -- previously fetched objects still work.

### Register with your AI client

**Claude Code:**
```bash
claude mcp add SAP-IBP-ABAP-INT -s user -- /path/to/sap-ibp-abap-int --env-file /path/to/.env
```

**Cline** (VS Code `settings.json`):
```json
{
  "cline.mcpServers": {
    "SAP-IBP-ABAP-INT": {
      "command": "/path/to/sap-ibp-abap-int",
      "args": ["--env-file", "/path/to/.env"]
    }
  }
}
```

**GitHub Copilot** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "SAP-IBP-ABAP-INT": {
      "command": "/path/to/sap-ibp-abap-int",
      "args": ["--env-file", "/path/to/.env"]
    }
  }
}
```

---

## What's included

| Category | Tools | Description |
|----------|-------|-------------|
| **Search** | `search_code`, `search_ibp_docs`, `search_adt_objects`, `lookup_object`, `explain_object` | Find and understand ABAP objects, search across code and IBP domain docs |
| **Analysis** | `class_hierarchy`, `method_callers`, `cds_dependencies`, `where_used` | Navigate class hierarchies, call graphs, CDS lineage, and references |
| **Version History** | `list_class_versions`, `get_class_version_source`, `diff_class_versions` | Browse transport history, fetch historical source, diff versions |
| **Quality** | `review_abap_code`, `syntax_check`, `diff_abap_conventions`, `diff_with_sap` | Lint, syntax check, convention diff, compare local vs SAP system |
| **Generation** | `generate_test`, `generate_test_documentation`, `generate_class` | Generate unit tests, test docs, and class skeletons from patterns |
| **Knowledge** | `get_abap_conventions`, `get_clean_abap` | IBP architecture reference and CleanABAP style guide |
| **ADT** | `fetch_adt_object`, `fetch_adt_package`, `fetch_with_dependencies`, `get_sap_source` | Fetch objects live from SAP, with dependency resolution |

---

## Issues & feedback

Please open an [Issue](https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/issues) for bug reports, feature requests, or questions.
