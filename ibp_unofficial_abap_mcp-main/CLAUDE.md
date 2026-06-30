# IBP Unofficial ABAP MCP - Release & Documentation Repository

This is the **release repository** for the SAP IBP ABAP Intelligence suite. It does NOT contain the Python source code directly -- it contains:
- PyInstaller build scripts that compile `ibp-bud6-mcp` (the source repo) into standalone binaries
- Pre-built Windows binary distribution (`dist/sap-ibp-abap-int/`)
- GitHub Pages documentation site (`docs/index.html`)
- Setup scripts for end-user installation (`release-assets/`)
- GitHub issue templates

The actual MCP server source lives at `../ibp-bud6-mcp/` (sibling directory).
The VS Code extension source lives at `../ibp-abap-intelligence/` (sibling directory).

## Repository Layout

```
ibp_unofficial_abap_mcp/
  build/                        # Build tooling
    build_release.py            # PyInstaller binary builder
    release_all.py              # Full release orchestrator (MCP + extension)
    runtime_hook.py             # PyInstaller frozen-mode patch
    README.md                   # Build instructions
  dist/                         # Built output (gitignored except for reference)
    sap-ibp-abap-int/           # PyInstaller onedir bundle
      sap-ibp-abap-int.exe      # Standalone Windows executable
      _internal/                # Bundled Python runtime + dependencies
      setup.bat                 # End-user setup script (copied from release-assets)
  release-assets/               # Files shipped in every release archive
    setup.bat                   # Windows interactive setup
    setup.sh                    # macOS/Linux interactive setup
  docs/                         # GitHub Pages site
    index.html                  # Full documentation (MCP Server, Extension, Studio)
    *.png                       # Screenshots
  .github/ISSUE_TEMPLATE/       # Bug report, feature request, question templates
  README.md                     # Project overview and installation guide
  .gitignore                    # Ignores dist/, build_output/, .env, .venv, .claude/
```

## How Releases Work

Run from this repo's `build/` directory:

```bash
python build/release_all.py 1.3.0
```

This:
1. Bumps version in `ibp-bud6-mcp/pyproject.toml` and `ibp-abap-intelligence/package.json`
2. Cleans `dist/` and `build_output/`
3. `pip install`s the MCP source, runs PyInstaller to produce `sap-ibp-abap-int.exe`
4. Runs `npx vsce package` to produce the `.vsix` extension
5. Creates versioned zip archives in `dist/`

Artifacts are uploaded to GitHub Releases at:
`https://github.tools.sap/I520242/ibp_unofficial_abap_mcp/releases`

## Source Repository: ibp-bud6-mcp

### Tech Stack
- Python 3.10+
- Build system: Hatchling (`pyproject.toml`)
- Package name: `sap-ibp-abap-int`
- Entry point: `sap_ibp_abap_int.server:main`
- Dependencies: `mcp[cli]`, `requests`, `python-docx`
- Optional: `pymupdf` (PDF ingestion), `pytest` (dev)

### Module Structure

```
src/sap_ibp_abap_int/
  __init__.py          # Package marker, version string
  __main__.py          # python -m entry: calls server.main()
  server.py            # MCP server: all 32+ tools, 6 resources, CLI arg parsing
  config.py            # Centralized config: data dir, DB paths, .env loading
  adt_client.py        # SAP ADT REST API client (HTTP Basic Auth, CSRF, XML parsing)
  indexer.py           # In-memory index + SQLite persistence, ABAPObject dataclass
  cache.py             # SQLite schema (WAL mode), FTS5 search index
  reviewer.py          # Static lint: prefix checks, method length, nesting, modernization
  generators.py        # Test skeleton generator (template-based)
  class_generator.py   # Full class skeleton generator from interfaces/superclass
  docx_generator.py    # .docx test documentation generator (python-docx)
  conventions.py       # 13 IBP/CODAP convention topics (architecture, naming, etc.)
  clean_abap.py        # CleanABAP FTS5 search interface
  clean_abap_ingest.py # Ingests CleanABAP.md into FTS5 SQLite DB
  ibp_knowledge.py     # IBP domain documentation FTS5 search
  pdf_ingest.py        # Extracts IBP PDFs into ibp_knowledge.db
  llm_client.py        # Thin HTTP client for LiteLLM proxy (OpenAI-compatible)
  prompts.py           # 4 prompt templates (write-class, write-test, write-cds, review)
  rap_knowledge.py     # 18 RAP topics with IBP examples
  abap_reference.py    # ~100 ABAP keyword/syntax reference entries
  syntax_checker.py    # Live SAP syntax check via temp class create/push/check/delete
  logger.py            # Shared file logger (server.log)
  data/                # Bundled data files
    CleanABAP.md       # Full CleanABAP style guide
```

## MCP Tools (32 total)

### Search & Lookup (5 tools)
| Tool | Description |
|------|-------------|
| `search_code` | Regex/keyword search across cached ABAP, test classes, CDS, tables, CleanABAP. Supports `file_type` filter and `context='method'` for full method blocks. |
| `search_ibp_docs` | FTS5 search across ingested IBP documentation (PDFs). Filter by source document name. |
| `search_adt_objects` | SAP repository quickSearch by name pattern with wildcards. Filter by `object_type` (CLAS, INTF, TABL, DDLS). |
| `lookup_object` | Get source code of a specific class/interface/CDS/table. Six include modes: source (auto-chunks >20KB), test, both, methods, overview, definition, full. Supports `method` param for specific methods (comma-separated). |
| `explain_object` | Structured explanation of an object: purpose, public API, patterns, dependencies. |

### Analysis (4 tools)
| Tool | Description |
|------|-------------|
| `class_hierarchy` | Superclass chain and direct subclasses via ADT. Tree-format output. |
| `method_callers` | Call graph: extracts callees from method source (static calls, instance calls, NEW), finds callers via index search. |
| `cds_dependencies` | Recursive CDS view data-source chain traversal via ADT. Configurable depth (default 3). |
| `where_used` | ADT where-used list: all objects referencing a class/interface. Grouped by type. |

### Version History (3 tools)
| Tool | Description |
|------|-------------|
| `list_class_versions` | Transport-based change log. Supports `include='main'|'test'|'both'`. Returns version ID, date, author, description, transport number. |
| `get_class_version_source` | Fetch full source at a specific version ID or timestamp. Supports main and test class sources. |
| `diff_class_versions` | Unified diff between two historical versions. Shows stats (additions/deletions). Caps at 500 lines. |

### Code Quality (5 tools)
| Tool | Description |
|------|-------------|
| `review_abap_code` | Static lint: IBP prefix violations, missing logging/exception handling, method too long, deep nesting, magic numbers, modernization (MOVE TO, CALL METHOD, READ TABLE+sy-subrc, etc.), performance (SELECT in LOOP, SELECT *, etc.). |
| `syntax_check` | **Live SAP compiler check** -- creates temp class in TEST_SYNTAX_CHECK package, pushes source, runs ADT checkruns, deletes temp class. Returns real compilation errors. |
| `diff_abap_conventions` | Compare code against indexed codebase patterns. Checks logging pattern, exception pattern, naming, testability. |
| `diff_with_sap` | Unified diff of local code vs live SAP system version. Opportunistically re-indexes if changes detected. |
| `get_sap_source` | Raw ABAP source from live SAP (no markdown). Used by VS Code extension for native diff. |

### Code Generation (3 tools)
| Tool | Description |
|------|-------------|
| `generate_test` | Template-based test skeleton: CLASS DEFERRED, LOCAL FRIENDS, OSQL environment, TEST-INJECTION stubs, one test method per public method. |
| `generate_test_documentation` | .docx test case document. Type A (API/scenario) or Type B (integration/component). Auto-derives test steps from method signatures and behavior. Gathers domain context from IBP knowledge base. |
| `generate_class` | Full class skeleton from interfaces + superclass. Resolves contracts, finds similar classes for pattern extraction. Template-based (no LLM). |

### Type System (4 tools)
| Tool | Description |
|------|-------------|
| `get_method_signatures` | Full parameter signatures from CLASS...DEFINITION: direction, name, type, optional flag, RAISING. Also resolves interface method signatures. |
| `get_interface_contract` | All methods, constants, and type definitions from an INTERFACE. |
| `lookup_data_dictionary` | Resolves data elements (type, length, labels), structures (field definitions), and table types (row type, access, key). Auto-detects object category. |
| `lookup_message_class` | T100 message texts with placeholder info. Filter by message number. |

### Knowledge Base (4 tools)
| Tool | Description |
|------|-------------|
| `get_abap_conventions` | 13 topics: architecture, naming, logging, testing, exceptions, cds, tables, service_layer, amdp, db_access, validation, instantiation, interfaces, constants, method_signatures. |
| `get_clean_abap` | CleanABAP style guide via FTS5 search. Topic-based retrieval. |
| `get_rap_knowledge` | 18 RAP topics: architecture, managed_vs_unmanaged, cds_naming, behavior_definition, behavior_implementation, saver_pattern, eml, validations, determinations, actions, testing, draft_handling, service_exposure, exception_class, utility_class, package_structure, fiori_annotations, checklist. |
| `search_abap_reference` | ~100 curated ABAP keyword entries with syntax, notes, examples, cross-references. |

### ADT Live Fetch (3 tools)
| Tool | Description |
|------|-------------|
| `fetch_adt_object` | Fetch single object from SAP via ADT REST API. Auto-indexes for future use. |
| `fetch_adt_package` | Bulk-fetch all objects in a SAP package. Discovers classes, interfaces, tables, CDS views. |
| `fetch_with_dependencies` | BFS dependency traversal: interfaces, superclass, TYPE REF TO, static calls. Configurable depth (1-3) and max objects (1-100). |

### Transport System (1 tool)
| Tool | Description |
|------|-------------|
| `list_user_transports` | CTS transport requests by user: workbench + customizing, tasks, contained objects. |

### LLM-Powered Tools (4 tools, require LLM_API_KEY)
| Tool | Description |
|------|-------------|
| `ai_review_code` | Deep semantic review via Claude. Structured findings with line numbers, severity, fix suggestions. |
| `ai_generate_test` | AI-generated complete unit test class from source code. |
| `ai_explain_object` | AI-powered structured explanation of ABAP objects. |
| `ai_review_transport` | Holistic cross-object review of all changes in a transport request. Collects diffs, sends combined changeset to Claude. |

## MCP Resources (6 total)

| URI | Description |
|-----|-------------|
| `abap://clean-abap` | CleanABAP topics overview |
| `abap://objects` | List of all indexed objects |
| `abap://prompts/write-class` | System prompt for writing ABAP classes |
| `abap://prompts/write-test` | System prompt for writing unit tests |
| `abap://prompts/write-cds` | System prompt for writing CDS views |
| `abap://prompts/review` | System prompt for code reviews |

## SAP Connectivity

- **Protocol**: ADT REST API over HTTPS
- **Authentication**: HTTP Basic Auth (username/password)
- **Session types**: Stateless (normal fetch) and Stateful (syntax checker needs lock persistence)
- **CSRF**: Fetched from `/sap/bc/adt/discovery` endpoint
- **SSL**: Configurable via `SAP_VERIFY_SSL` (defaults to false for internal SAP systems)
- **Client**: Optional `SAP_CLIENT` parameter for multi-client systems
- **Mode**: Read-only (except syntax_checker which creates/deletes temp objects in TEST_SYNTAX_CHECK)

### ADT Endpoints Used
- `/sap/bc/adt/discovery` -- CSRF token fetch + connectivity test
- `/sap/bc/adt/programs/classes/{name}/source/main` -- Class main source
- `/sap/bc/adt/programs/classes/{name}/includes/testclasses/source` -- Test classes
- `/sap/bc/adt/repository/informationsystem/search` -- Object search (quickSearch)
- `/sap/bc/adt/vit/wb/object_type/devck/object_name/{package}` -- Package contents
- `/sap/bc/adt/programs/classes/{name}/versions` -- Version list
- `/sap/bc/adt/programs/classes/{name}/versions/{id}/source` -- Version source
- `/sap/bc/adt/relations/whereused` -- Where-used list
- `/sap/bc/adt/cts/transportrequests` -- Transport requests
- `/sap/bc/adt/ddic/dataelements/{name}` -- Data element metadata
- `/sap/bc/adt/ddic/tabletypes/{name}` -- Table type metadata
- `/sap/bc/adt/ddic/structures/{name}/source/main` -- Structure source
- `/sap/bc/adt/messageclass/{name}` -- Message class with messages
- `/sap/bc/adt/checkruns` -- Syntax check execution

## Configuration

All via environment variables (loaded from `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAP_BASE_URL` | For live fetch | -- | SAP system URL (ADT endpoint base) |
| `SAP_USERNAME` | For live fetch | -- | SAP ADT user |
| `SAP_PASSWORD` | For live fetch | -- | SAP ADT password |
| `SAP_VERIFY_SSL` | No | `false` | SSL certificate verification |
| `SAP_CLIENT` | No | -- | SAP client number |
| `IBP_DATA_DIR` | No | `src/sap_ibp_abap_int/data/` | Directory for index.db, server.log, generated_docs/ |
| `IBP_CACHE_TTL_HOURS` | No | `24` | Hours before cached objects are considered stale |
| `LLM_PROXY_URL` | For AI tools | `http://localhost:6655/litellm/v1/chat/completions` | OpenAI-compatible chat completions endpoint |
| `LLM_API_KEY` | For AI tools | -- | Bearer token for the LLM proxy |
| `LLM_MODEL` | No | `anthropic--claude-4.6-opus` | Model identifier |
| `IBP_EXTENSION_CLIENT` | No | -- | When set, keeps ai_* tools registered (VS Code extension mode) |

### CLI Arguments

```
sap-ibp-abap-int [--data-dir DIR] [--env-file PATH] [--transport stdio]
```

### .env File Resolution Order
1. Current working directory
2. Package directory (`src/sap_ibp_abap_int/.env`)
3. Data directory

## Key Data Structures

### ABAPObject (dataclass in indexer.py)
```python
@dataclass
class ABAPObject:
    name: str                    # e.g., "/IBP/CL_DBP_BO"
    object_type: str             # "class", "cds_view", "table", "interface", "function_group", "program"
    description: str = ""
    source_path: str = ""        # synthetic path (e.g., "adt:/IBP/CL_DBP_BO")
    test_path: str = ""
    package: str = ""            # "adt_live" for ADT-fetched objects
    interfaces: list[str]        # implemented interfaces
    methods: list[str]           # method names from IMPLEMENTATION section
    source_code: str = ""        # full cached source
    test_code: str = ""          # test class source
    references: list[str]        # objects this one depends on
    referenced_by: list[str]     # objects that reference this one
    fetched_at: str = ""         # ISO timestamp of last ADT fetch
    adt_updated_at: str = ""     # SAP-side last-modified timestamp
```

### SQLite Schema (cache.py, SCHEMA_VERSION = 2)
- `schema_version` -- version tracking
- `source_files` -- file path, mtime, size, object name, role
- `abap_objects` -- mirrors ABAPObject fields (interfaces/methods stored as JSON arrays)
- `dependencies` -- source_name/target_name pairs
- `source_fts` -- FTS5 virtual table for full-text search

### CodebaseIndex (indexer.py)
- `objects: dict[str, ABAPObject]` -- upper-cased name -> object mapping
- `build()` -- loads all objects from SQLite on startup
- `lookup(name)` -- fuzzy name resolution (handles /IBP/, IBP_, partial match)
- `search(query, file_type, context)` -- regex search across all cached source
- `persist_adt_object(obj)` -- saves an ADT-fetched object to SQLite

## Architecture Design Principles

1. **Read-only** -- no write operations to the SAP system (except temp class for syntax check)
2. **On-demand fetching** -- objects fetched from SAP only when requested, then cached in SQLite
3. **Graceful degradation** -- works without SAP credentials using cached data only
4. **Auto-chunking** -- objects >20KB return overview + method index to preserve context window
5. **Cache staleness** -- TTL-based (default 24h). Classes use lightweight version-list check; non-class objects re-fetch when stale. `diff_with_sap` and `get_sap_source` opportunistically update index when differences detected
6. **Dependency BFS** -- `fetch_with_dependencies` traverses structural deps (interfaces, superclass, TYPE REF TO, static calls)

## Differences from ibp-bud6-mcp

This repository (`ibp_unofficial_abap_mcp`) is the **release/distribution** repo:
- Contains build scripts, not source code
- Produces standalone executables via PyInstaller
- Hosts GitHub Pages documentation site
- Contains setup scripts for end-user onboarding
- Manages versioned release archives

`ibp-bud6-mcp` is the **source** repo:
- Contains all Python source code
- Has `pyproject.toml` with dependencies
- Installable via `pip install .`
- Contains the `sap_ibp_abap_int` package

They are siblings in the workspace -- `release_all.py` expects this layout:
```
workspace/
  ibp-bud6-mcp/              # MCP server source
  ibp-abap-intelligence/     # VS Code extension source
  ibp_unofficial_abap_mcp/   # This repo (build + release)
```

## Commands

### Build a release
```bash
python build/release_all.py 1.3.0              # Full release
python build/release_all.py 1.3.0 --skip-extension  # MCP binary only
python build/release_all.py 1.3.0 --skip-pyinstaller  # Extension only
```

### Install MCP server from source
```bash
cd ../ibp-bud6-mcp
pip install .
```

### Run MCP server
```bash
sap-ibp-abap-int --env-file /path/to/.env
```

### Register with Claude Code
```bash
claude mcp add SAP-IBP-ABAP-INT -s user -- sap-ibp-abap-int --env-file /path/to/.env
```

## Internal SAP Project

- GitHub Enterprise: `https://github.tools.sap/I520242/ibp_unofficial_abap_mcp`
- Status: Unofficial, SAP Internal only, not for productive use
- License: SAP Internal - Confidential
- Tag: v1.0.0-beta exists
