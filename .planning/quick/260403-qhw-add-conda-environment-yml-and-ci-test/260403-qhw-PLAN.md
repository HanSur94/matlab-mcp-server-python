---
phase: quick
plan: 260403-qhw
type: execute
wave: 1
depends_on: []
files_modified:
  - environment.yml
  - .github/workflows/ci.yml
autonomous: true
requirements: []
must_haves:
  truths:
    - "environment.yml creates a working conda env with Python 3.12 and all runtime deps"
    - "conda-test CI job creates the env, verifies module imports, and runs unit tests"
  artifacts:
    - path: "environment.yml"
      provides: "Conda environment definition with pip-installed matlab-mcp-server"
    - path: ".github/workflows/ci.yml"
      provides: "conda-test job using conda-incubator/setup-miniconda"
  key_links:
    - from: ".github/workflows/ci.yml (conda-test job)"
      to: "environment.yml"
      via: "setup-miniconda activate-environment + environment-file"
      pattern: "environment-file.*environment.yml"
---

<objective>
Add conda/miniconda installation support with CI validation.

Purpose: Enable users who prefer conda environments to install and use the MATLAB MCP server, and verify this path works in CI.
Output: environment.yml at repo root, new conda-test job in CI workflow.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@pyproject.toml
@.github/workflows/ci.yml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create environment.yml and add conda-test CI job</name>
  <files>environment.yml, .github/workflows/ci.yml</files>
  <action>
1. Create `environment.yml` at repo root with:
   - `name: matlab-mcp`
   - `channels: [conda-forge, defaults]`
   - `dependencies:` section with `python=3.12`
   - A `pip:` subsection that installs the local package with dev+monitoring extras: `- -e ".[dev,monitoring]"`
   - This approach leverages conda for Python/env management while using pip for the actual package (since matlab-mcp-python is not on conda-forge)

2. Add a `conda-test` job to `.github/workflows/ci.yml`:
   - `needs: lint` (same pattern as other test jobs)
   - `runs-on: ubuntu-latest`
   - Steps:
     a. `actions/checkout@v4`
     b. `conda-incubator/setup-miniconda@v3` with:
        - `activate-environment: matlab-mcp`
        - `environment-file: environment.yml`
        - `auto-activate-base: false`
        - `python-version: "3.12"`
     c. Module import verification step (shell: bash -el {0}):
        ```
        python -c "from matlab_mcp.server import main; print('OK: server')"
        python -c "from matlab_mcp.auth.middleware import BearerAuthMiddleware; print('OK: auth')"
        python -c "from matlab_mcp.hitl.gate import request_execute_approval; print('OK: hitl')"
        ```
     d. Run unit tests step (shell: bash -el {0}):
        `pytest tests/ -v -k "not matlab" --ignore=tests/test_integration.py --ignore=tests/test_mcp_integration.py -W ignore::pytest.PytestUnraisableExceptionWarning`
   - IMPORTANT: All run steps in the conda-test job MUST use `shell: bash -el {0}` so the conda environment is activated via the login shell profile. This is required by conda-incubator/setup-miniconda.
   - Place the job after `test-macos` and before `integration-test` in the file for logical grouping.
  </action>
  <verify>
    <automated>python -c "import yaml; d=yaml.safe_load(open('environment.yml')); assert d['name']=='matlab-mcp'; assert any('python=3.12' in str(x) for x in d['dependencies']); print('environment.yml OK')" && grep -q 'conda-test' .github/workflows/ci.yml && grep -q 'setup-miniconda' .github/workflows/ci.yml && grep -q 'environment-file' .github/workflows/ci.yml && echo "CI config OK"</automated>
  </verify>
  <done>
    - environment.yml exists with Python 3.12, pip install of local package with dev+monitoring extras
    - .github/workflows/ci.yml has a conda-test job that uses setup-miniconda, verifies module imports, and runs tests
    - All run steps use `shell: bash -el {0}` for conda activation
  </done>
</task>

</tasks>

<verification>
- `cat environment.yml` shows valid conda env spec with pip local install
- `grep -A 30 'conda-test' .github/workflows/ci.yml` shows complete job definition
- YAML is valid: `python -c "import yaml; yaml.safe_load(open('environment.yml')); yaml.safe_load(open('.github/workflows/ci.yml'))"`
</verification>

<success_criteria>
- environment.yml creates a conda env named matlab-mcp with Python 3.12 and all deps via pip
- CI workflow has conda-test job that validates the conda install path end-to-end
</success_criteria>

<output>
After completion, create `.planning/quick/260403-qhw-add-conda-environment-yml-and-ci-test/260403-qhw-SUMMARY.md`
</output>
