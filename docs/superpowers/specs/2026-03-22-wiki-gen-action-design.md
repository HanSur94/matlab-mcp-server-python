# Wiki Gen Action — Design Spec

## Overview

A reusable GitHub Composite Action (`HanSur94/wiki-gen-action`) that auto-generates wiki documentation for any GitHub project using the Anthropic Claude API. Language-agnostic, zero-config by default, customizable via config file.

## Goals

- **Reusable**: Add docs generation to any GitHub repo with 2 lines of YAML
- **Language-agnostic**: LLM reads source code regardless of language
- **Full coverage**: Two-pass generation ensures all code is captured
- **Mermaid diagrams**: Architecture, API, and flow diagrams generated automatically
- **Zero-config**: Auto-discovers repo structure; optional config for customization
- **Cost-conscious**: Uses cheap model for summaries, logs token usage, supports dry-run

## Repository Structure

```
wiki-gen-action/
├── action.yml              # GitHub Action definition (inputs, outputs, runs)
├── scripts/
│   ├── discover.py         # Auto-discovers repo structure -> page definitions
│   ├── generate.py         # Generates wiki pages via Claude API (two-pass)
│   └── push_wiki.sh        # Pushes to wiki repo (direct or PR)
├── defaults/
│   └── prompts.yml         # Default prompts per page type
├── README.md
└── LICENSE (MIT)
```

## Action Definition

### Inputs

```yaml
inputs:
  anthropic_api_key:
    description: 'Anthropic API key'
    required: true
  wiki_pat:
    description: 'GitHub PAT with wiki push access (requires repo scope for classic PATs, or contents:write for fine-grained PATs; add pull-requests:write if using push_strategy: pr)'
    required: true
  model:
    description: 'Claude model for Pass 2 page generation. Pass 1 always uses claude-haiku-4-5 for cost efficiency.'
    default: 'claude-haiku-4-5'
  config_path:
    description: 'Path to docs config file. If the file does not exist (default or custom path), auto-discovery runs.'
    default: '.github/docs-config.yml'
  dry_run:
    description: 'Generate pages without pushing to wiki'
    default: 'false'
  push_strategy:
    description: 'How to push wiki updates: "direct" (push to wiki repo) or "pr" (commit wiki files to a docs/ branch in the main repo and open a PR for review)'
    default: 'direct'
  auto_merge:
    description: 'Auto-merge wiki update PRs via gh pr merge --auto (only with push_strategy: pr). Note: requires branch protection to allow auto-merge and may not satisfy required-reviews if the workflow token is the PR creator.'
    default: 'false'
```

### Outputs

```yaml
outputs:
  pages_updated:
    description: 'Number of wiki pages successfully written'
  pages_failed:
    description: 'Number of wiki pages that failed generation'
  wiki_commit_sha:
    description: 'Git SHA of the wiki commit (empty on dry_run or no changes)'
```

### Runs Block

```yaml
runs:
  using: 'composite'
  steps:
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install dependencies
      shell: bash
      run: pip install anthropic pyyaml

    - name: Discover and generate wiki pages
      shell: bash
      env:
        ANTHROPIC_API_KEY: ${{ inputs.anthropic_api_key }}
        INPUT_MODEL: ${{ inputs.model }}
        INPUT_CONFIG_PATH: ${{ inputs.config_path }}
        INPUT_DRY_RUN: ${{ inputs.dry_run }}
      run: |
        python ${{ github.action_path }}/scripts/discover.py
        python ${{ github.action_path }}/scripts/generate.py

    - name: Push wiki
      if: inputs.dry_run != 'true'
      shell: bash
      env:
        WIKI_PAT: ${{ inputs.wiki_pat }}
        PUSH_STRATEGY: ${{ inputs.push_strategy }}
        AUTO_MERGE: ${{ inputs.auto_merge }}
        GITHUB_REPOSITORY: ${{ github.repository }}
      run: bash ${{ github.action_path }}/scripts/push_wiki.sh
```

## Consumer Workflow

Minimal integration in any repo:

```yaml
name: Generate Docs
on:
  push:
    branches: [main, master]

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  docs:
    runs-on: ubuntu-latest
    needs: [ci]  # Only generate after CI passes
    steps:
      - uses: actions/checkout@v4
      - uses: HanSur94/wiki-gen-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          wiki_pat: ${{ secrets.WIKI_PAT }}
```

**Note:** The `concurrency` group is recommended to prevent wiki push conflicts from rapid successive pushes.

## Auto-Discovery Logic

When no config file exists at `config_path`, `discover.py` scans the repo:

| Page             | Trigger                                | Source Files                                      |
|------------------|----------------------------------------|---------------------------------------------------|
| Home             | Always                                 | README.md + package manifest                      |
| Installation     | Always                                 | README + manifest + Dockerfile if present         |
| Architecture     | `src/` or `lib/` exists               | All source files (via two-pass summarization)     |
| API Reference    | Source files with docstrings found     | All source files grouped by module                |
| Configuration    | Config files detected                  | Config files + related source                     |
| Security         | Files matching security heuristic*     | Matched security files                            |
| Examples         | `examples/` directory exists           | All files under `examples/`                       |
| FAQ              | Always                                 | README + discovered context                       |
| Troubleshooting  | Always                                 | README + config files                             |

*Security heuristic: files/directories matching `security`, `auth`, `permissions`, `rbac`, `acl`, `crypto`, `encrypt`, `sanitiz`, `validat` (case-insensitive, in path or filename).

### Language Detection

File extensions are mapped to language labels for prompt context:

| Extensions | Language |
|-----------|----------|
| `.py` | Python |
| `.js`, `.mjs`, `.cjs` | JavaScript |
| `.ts`, `.tsx` | TypeScript |
| `.java` | Java |
| `.go` | Go |
| `.rs` | Rust |
| `.rb` | Ruby |
| `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp` | C++ |
| `.c` | C |
| `.cs` | C# |
| `.m` | MATLAB/Objective-C |
| `.swift` | Swift |
| `.kt`, `.kts` | Kotlin |
| `.php` | PHP |

For multi-language repos, all detected languages are listed in prompts.

### File Filtering

**Included:** Only text files matching known source extensions (above) plus: `.md`, `.yml`, `.yaml`, `.json`, `.toml`, `.cfg`, `.ini`, `.env.example`, `.sh`, `.bat`, `.ps1`, `.sql`, `.html`, `.css`, `.scss`, `.r`, `.R`, `.jl`.

**Excluded (always):**
- Binary files (detected by null-byte check on first 8KB)
- Symlinks (not followed)
- Files > 100KB (skipped with warning)
- Directories: `.git/`, `node_modules/`, `__pycache__/`, `.tox/`, `.venv/`, `venv/`, `.eggs/`, `dist/`, `build/`, `.mypy_cache/`

**Max directory depth:** 10 levels.

## Config File Format

Optional `.github/docs-config.yml` for custom control:

```yaml
# Optional overrides
model: claude-haiku-4-5
max_chars_per_file: 6000          # Default: 6000
include_mermaid: true             # Default: true

# Optional: restrict which dirs to scan (default: entire repo)
source_dirs:
  - src/
  - lib/
  - examples/

# Optional: exclude patterns (glob syntax)
exclude:
  - "*.test.*"
  - "vendor/"
  - "node_modules/"

# Optional: custom page definitions (overrides auto-discovery)
pages:
  Home:
    sources: ["README.md"]
    prompt: "Write a welcoming overview..."
  Architecture:
    sources: ["src/**/*.py"]
    prompt: "Document the system architecture with Mermaid diagrams..."

# Optional: extra pages beyond defaults
extra_pages:
  Deployment:
    sources: ["Dockerfile", "docker-compose.yml", "k8s/**/*"]
    prompt: "Document deployment options..."
```

**Rules:**
- `pages` omitted -> auto-discovery runs
- `pages` present -> only those pages are generated
- `extra_pages` always appended (works with or without auto-discovery)
- If an `extra_pages` key conflicts with a `pages` key, `extra_pages` is ignored for that key (explicit `pages` wins)
- Sources support glob patterns (`**/*.py`) and explicit paths. Directory paths without globs (e.g. `k8s/`) are treated as `k8s/**/*`
- `max_chars_per_file` default: 6000 characters
- All other fields have sensible defaults

## Two-Pass Generation

Ensures full code coverage regardless of codebase size.

### Pass 1 — Summarize

1. Walk all source files in the repo (respecting `source_dirs`, `exclude`, and file filters)
2. Group files into batches of ~15,000 tokens (~50k chars, using ~3.5 chars/token approximation for code). Each batch stays well within haiku's 200k context window after accounting for prompt overhead.
3. For each batch, call Claude (haiku — cheapest model):
   - Prompt: "Summarize each file: purpose, key classes/functions, dependencies"
4. Store summaries in memory
5. If a single file exceeds the batch size, it is truncated to `max_chars_per_file` and processed alone

### Pass 2 — Generate Pages

For each wiki page:

1. Build prompt containing:
   - All file summaries from Pass 1
   - Full source code of the most relevant files for that page
   - Page-type prompt from `defaults/prompts.yml` or config
   - Existing wiki page as style reference (if exists)
   - Instruction: "Include Mermaid diagrams using ```mermaid code blocks where they aid understanding"
2. Call Claude (configured model)
3. Validate output:
   - Not empty
   - Not a refusal (checked via stop_reason and content inspection)
   - Mermaid blocks are well-formed (regex check: opening ```mermaid has matching closing ```, and contains a valid diagram type keyword: graph, flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram, gantt, pie, gitgraph)
4. Write to `wiki/*.md`

### Mermaid Diagram Prompting

Prompts explicitly instruct Claude to include Mermaid diagrams:
- **Architecture** -> component diagrams, flowcharts
- **API Reference** -> class/module relationship diagrams
- **Async/Job pages** -> sequence diagrams
- **Installation** -> flowchart for setup paths

**Validation:** Regex-based fence check (no external Mermaid CLI dependency). Checks that ```mermaid blocks are properly closed and contain a recognized diagram type keyword. Invalid blocks are stripped with a warning, not a failure.

## Push Strategies

Three modes for publishing wiki updates:

### 1. Direct push (`push_strategy: direct`, default)

- Clones `<repo>.wiki.git` using `WIKI_PAT`
- If the wiki repo does not exist (first run), initializes it by creating a `Home.md` and pushing
- Copies generated `wiki/*.md` into the clone
- If no changes detected (`git status --porcelain` is empty), exits cleanly
- Commits with message `docs: auto-update wiki` and pushes
- On non-fast-forward rejection, pulls with rebase and retries push (max 2 retries)

### 2. PR with manual review (`push_strategy: pr`)

- Creates a branch `docs/wiki-update-<sha>` in the **main repo** (not the wiki repo, since GitHub does not support PRs on wiki repos)
- Commits generated `wiki/*.md` files to that branch
- Opens a PR against the default branch with title "docs: auto-update wiki pages"
- A separate merge step (manual or auto) then triggers the direct push to the wiki repo

### 3. PR with auto-merge (`push_strategy: pr`, `auto_merge: true`)

- Same as mode 2, but runs `gh pr merge --auto --squash` after creating the PR
- **Limitation:** GitHub does not allow a workflow to approve its own PR using `GITHUB_TOKEN`. If branch protection requires reviews, auto-merge will wait until a human approves. Consider using a separate bot PAT or relaxing review requirements for docs-only PRs.

## Cost Control

- Pass 1 always uses `claude-haiku-4-5` for summaries
- Pass 2 uses the configured model (default: `claude-haiku-4-5`)
- Token usage logged per page in structured format:
  ```
  [wiki-gen] Page: Architecture | input_tokens: 12450 | output_tokens: 3200 | model: claude-haiku-4-5
  ```
- Summary line at end: `[wiki-gen] Total: input=84200 output=28500 pages=9/11`
- `dry_run: true` generates pages locally without pushing (for testing)

## Error Handling

- Missing source files: warn and skip, don't fail the action
- API failures: retry with exponential backoff (2^attempt seconds, max 2 retries)
- Refusal detection: check `stop_reason` for `end_turn` and inspect content for refusal patterns. On refusal, skip page and log warning
- Empty output: skip page, log warning
- Invalid Mermaid blocks: strip the invalid block, keep the rest of the page, log warning
- Wiki repo does not exist: initialize with a Home.md stub (direct mode) or fail with clear error message (PR mode)
- `continue-on-error` behavior: generate as many pages as possible, report failures in summary
- Action exits with failure only if zero pages were generated successfully

## GitHub CLI Extension: `gh-wiki-gen`

A companion `gh` CLI extension (`HanSur94/gh-wiki-gen`) that bootstraps the wiki-gen workflow into any repo with a single command.

### Installation

```bash
gh extension install HanSur94/gh-wiki-gen
```

### Repository Structure

```
gh-wiki-gen/
├── gh-wiki-gen             # Main extension script (bash)
├── templates/
│   ├── docs.yml            # Workflow template
│   └── docs-config.yml     # Optional config template
└── README.md
```

### Commands

#### `gh wiki-gen init`

Interactive setup that:

1. Detects the current repo (`gh repo view --json name,owner`)
2. Creates `.github/workflows/docs.yml` with the wiki-gen-action workflow
   - Auto-detects default branch (main/master) for the trigger
   - If a CI workflow exists, adds `needs: [ci]` dependency
3. Prompts for secrets setup:
   ```
   Set up ANTHROPIC_API_KEY as a repo secret? (Y/n)
   Enter your Anthropic API key: ****
   Set up WIKI_PAT as a repo secret? (Y/n)
   Enter your GitHub PAT: ****
   ```
   Sets secrets via `gh secret set`
4. Asks whether to create a `.github/docs-config.yml` starter config:
   ```
   Create a docs config file for customization? (y/N)
   ```
   If yes, copies the starter template with comments explaining each option
5. Prints summary:
   ```
   Wiki generation configured for owner/repo
     Workflow: .github/workflows/docs.yml
     Secrets:  ANTHROPIC_API_KEY ✓  WIKI_PAT ✓
     Config:   .github/docs-config.yml (optional)

   Push to trigger: git add . && git commit -m "ci: add wiki generation" && git push
   ```

#### `gh wiki-gen status`

Shows the status of the last docs workflow run:
```bash
gh run list --workflow=docs.yml --limit=1
```

#### `gh wiki-gen run`

Manually triggers a docs generation run (requires `workflow_dispatch` in the workflow):
```bash
gh workflow run docs.yml
```

#### `gh wiki-gen dry-run`

Triggers a dry-run (no wiki push) to preview what would be generated:
```bash
gh workflow run docs.yml -f dry_run=true
```

### Flags

All commands support:
- `--repo <owner/repo>` — target a different repo (default: current directory)
- `--model <model>` — override the Claude model in the workflow template
- `--push-strategy <direct|pr>` — set push strategy in the workflow template
- `--auto-merge` — enable auto-merge in the workflow template

### Workflow Template

The template written by `gh wiki-gen init`:

```yaml
name: Generate Docs
on:
  push:
    branches: [{{DEFAULT_BRANCH}}]
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no wiki push)'
        type: boolean
        default: false

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  docs:
    runs-on: ubuntu-latest
    {{NEEDS_CI}}
    steps:
      - uses: actions/checkout@v4
      - uses: HanSur94/wiki-gen-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          wiki_pat: ${{ secrets.WIKI_PAT }}
          dry_run: ${{ inputs.dry_run || 'false' }}
          {{EXTRA_INPUTS}}
```

`{{DEFAULT_BRANCH}}`, `{{NEEDS_CI}}`, and `{{EXTRA_INPUTS}}` are replaced by the init command based on repo detection and user flags.

## Dependencies

Runtime (installed by the composite action's setup steps):
- Python 3.12 (via `actions/setup-python@v5`)
- `anthropic` Python SDK
- `pyyaml` for config parsing
- `git` (pre-installed on GitHub runners)
- `gh` CLI (pre-installed on GitHub runners, used for PR strategy)

CLI extension:
- `gh` CLI (user's machine)
- Bash (the extension script)
