# Gate 1 Windows Internal Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible Windows 10/11 internal `onedir` executable for the approved Gate 1 checkpoint and prove that it starts offline, initializes and writes a new workspace, and imports DOCX/PDF/PPTX without requiring a local Python installation.

**Architecture:** Use PyInstaller in `onedir`, windowed, no-UPX mode. Set its content directory to `src` so the frozen module paths preserve the repository's existing resource-root calculations; copy contracts, migrations, notices, and an internal-only smoke-test kit beside the executable, then hash the complete package. The application bundle and test kit remain separate: deterministic research fixtures support internal verification but are not runtime application content.

**Tech Stack:** Python 3.12, uv/uv.lock, PyInstaller, PySide6/QtUiTools, Alembic, SQLite, python-docx, pypdf, python-pptx, pytest, pytest-qt, pytest-socket, PowerShell, Windows Sandbox or a clean Windows 10/11 VM, Microsoft Defender.

## Global Constraints

- Baseline is exactly Gate 1 checkpoint `25c5230000511c5982a669c18fe4b636edeecb36` on `feature/v0.2-deterministic`.
- This work packages existing Gate 1 behavior only. It adds no Gate 2 feature, installer, auto-update, OCR, network access, Agent/Task execution, signing service, or public distribution workflow.
- The internal artifact is `onedir`, not `onefile`, uses no UPX, is not installed system-wide, and never writes beside the executable.
- The frozen application directory is immutable at runtime. All database, snapshots, derived data, logs, and configuration remain under the selected per-user writable locations.
- Build and smoke-test outputs are written outside the Git worktree. No generated executable, temporary database, fixture copy, or evidence screenshot is committed.
- “Reproducible” means the exact Git SHA, lockfile, build command, resources, and output hashes are recorded and another host can repeat the build; bit-for-bit PE equality is not claimed unless a two-build comparison proves it.
- `.ui` files remain the only runtime layouts. Top-level supplied `ui/` inputs are not packaged; only `src/research_workspace/presentation/ui/` is runtime content.
- The bundle includes exact Gate 1 migrations `0001` and `0002`, required JSON contracts, runtime UI resources, parser dependencies, Qt plugins, and `THIRD_PARTY_NOTICES.md`.
- The Gate 1 deterministic fixture set is copied only into the sibling internal test kit and must remain 14/14 manifest-valid.
- Every build uses the existing `uv.lock`. A lock change reruns the full commercial-license gate before another executable is produced.
- PyInstaller's exact resolved license and bootloader exception, and every new transitive/test dependency, must be reviewed explicitly. Unknown, incompatible, or unverifiable terms are a hard stop.
- No test may be weakened, skipped, or marked xfail to accept a package.
- `REL-GATE-001` remains `BLOCKED_BY_ENVIRONMENT`; it blocks public packaged release only. Single-monitor 100/125/150% evidence does not close the mixed-DPI gate.

## Locked Package Layout

```text
ResearchWorkspace-internal-<git-sha>/
├─ app/
│  ├─ ResearchWorkspace.exe
│  ├─ src/                         # PyInstaller contents_directory / sys._MEIPASS
│  │  ├─ research_workspace/
│  │  │  └─ presentation/ui/*.ui + design_tokens.json
│  │  └─ PySide6/Qt/plugins/platforms/qwindows.dll
│  ├─ contracts/*.json + provider_interfaces.md
│  ├─ migrations/env.py
│  ├─ migrations/script.py.mako
│  ├─ migrations/versions/0001_foundation_schema.py
│  ├─ migrations/versions/0002_gate1_import_parse.py
│  ├─ THIRD_PARTY_NOTICES.md
│  └─ BUILD-MANIFEST.json
└─ test-kit/
   ├─ fixtures/                    # exact tests/gate1/fixtures docx/pdf/pptx bytes
   ├─ fixture-manifest.json
   ├─ run-smoke.ps1
   └─ windows-internal-checklist.md
```

`BUILD-MANIFEST.json` contains Git SHA, locked dependency digest, build timestamp, Python/PyInstaller/application versions, relative path, byte size, SHA-256, and role for every ordinary file. It excludes itself from its inventory and has a sibling `BUILD-MANIFEST.sha256`.

## File Map

- Modify: `pyproject.toml`, `uv.lock`, `THIRD_PARTY_NOTICES.md`, `tests/acceptance/test_license_policy.py`, `README.md`
- Create: `packaging/windows/research_workspace.spec`
- Create: `packaging/windows/build_internal.ps1`
- Create: `packaging/windows/build_manifest.py`
- Create: `packaging/windows/verify_bundle.py`
- Create: `packaging/windows/run_smoke.ps1`
- Create: `packaging/windows/windows-internal-checklist.md`
- Create: `packaging/windows/ResearchWorkspaceInternal.wsb`
- Create: `tests/packaging/conftest.py`
- Create: `tests/packaging/test_packager_license.py`
- Create: `tests/packaging/test_packaging_contract.py`
- Create: `tests/packaging/test_bundle_inventory.py`
- Create: `tests/packaging/test_packaged_startup.py`
- Create: `tests/packaging/test_packaged_imports.py`
- Create: `tests/packaging/test_packaging_checkpoint.py`

No `src/`, migration, contract, UI, or database change is planned. If `contents_directory="src"` plus the declared package layout cannot satisfy the existing resource lookups, stop and request approval before changing production resource-location code.

---

### Task 1: Resolve and license-gate packaging dependencies

**Files:**
- Create: `tests/packaging/test_packager_license.py`
- Modify: `pyproject.toml`, `uv.lock`, `THIRD_PARTY_NOTICES.md`, `tests/acceptance/test_license_policy.py`

**Consumes:** Gate 1 lockfile and fail-closed commercial-license policy.

**Produces:** Exact locked PyInstaller and UI-smoke-driver dependency closure with complete notices; no executable.

- [ ] **Step 1: Write genuine dependency and exception-policy RED tests**

```python
def test_packager_and_smoke_driver_are_exactly_locked():
    locked = locked_distributions()
    assert {"pyinstaller", "pywinauto"} <= locked.keys()
    assert parser_and_packaging_closure(locked) <= notice_inventory()

def test_only_verified_pyinstaller_bootloader_exception_is_allowed():
    assert packaging_license_decision(
        name="pyinstaller", license_expression=observed_expression(),
        license_text=observed_license_text(),
    ).approved
    assert not packaging_license_decision(
        name="other", license_expression="GPL-2.0-or-later",
        license_text="GPL only",
    ).approved
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/packaging/test_packager_license.py tests/acceptance/test_license_policy.py`

Expected: FAIL because the approved packager/smoke driver are not in `uv.lock`; no policy is changed before exact metadata is known.

- [ ] **Step 3: Resolve through uv and fail closed on license uncertainty**

Run: `uv add --group dev pyinstaller pywinauto`

Regenerate notices using the repository's existing `pip-licenses` command. Record every direct/transitive version, source URL, license expression, and license text. Permit PyInstaller only when the exact resolved distribution carries its recognized bootloader exception; do not allow bare GPL/AGPL or make a name-agnostic exception. Any ambiguity stops Task 1.

- [ ] **Step 4: GREEN and accumulated verification**

```powershell
uv run pytest -q tests/packaging/test_packager_license.py tests/acceptance/test_license_policy.py tests/gate1/acceptance/test_gate1_license_inventory.py
uv run pytest -q
git diff --check
```

- [ ] **Step 5: Commit and stop for the license checkpoint**

```powershell
git add pyproject.toml uv.lock THIRD_PARTY_NOTICES.md tests/acceptance/test_license_policy.py tests/packaging/test_packager_license.py
git commit -m "build: license-gate the Windows packager"
```

Report the resolved closure literally. Do not begin the build if this checkpoint is not approved.

---

### Task 2: Lock the reproducible onedir build contract

**Files:**
- Create: `packaging/windows/research_workspace.spec`
- Create: `packaging/windows/build_internal.ps1`
- Create: `packaging/windows/build_manifest.py`
- Create: `tests/packaging/test_packaging_contract.py`

**Consumes:** Approved Task 1 lockfile; `app.py`; runtime UI package; top-level contracts and migrations.

**Produces:** `Build-InternalPackage -OutputRoot <outside-worktree>` and deterministic bundle manifest generation.

- [ ] **Step 1: Write RED contract tests**

```python
def test_spec_is_windowed_onedir_without_upx_and_preserves_source_depth(spec_contract):
    assert spec_contract == {
        "entry": "app.py", "name": "ResearchWorkspace", "console": False,
        "onefile": False, "upx": False, "contents_directory": "src",
    }

def test_build_output_must_be_outside_git_worktree(build_script):
    assert build_script.rejects(ROOT / "dist")
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/packaging/test_packaging_contract.py`

Expected: FAIL because the spec/build scripts do not exist.

- [ ] **Step 3: Implement the minimal build**

The spec collects only imported runtime code plus `research_workspace.presentation/ui/*.ui` and `design_tokens.json`. PyInstaller's PySide6 hooks collect Qt libraries/plugins; do not use an unrestricted `collect_all("PySide6")`. The PowerShell build:

```powershell
uv sync --frozen
uv run pyinstaller --clean --noconfirm packaging/windows/research_workspace.spec `
  --distpath $WorkRoot/dist --workpath $WorkRoot/work
Copy-Item contracts, migrations, THIRD_PARTY_NOTICES.md -Destination $AppRoot -Recurse
uv run python packaging/windows/build_manifest.py $PackageRoot
```

It checks `git status --porcelain` before building, records the source SHA, copies fixtures into `test-kit` only, verifies the existing fixture manifest, and refuses an output path inside the repository or an existing nonempty package directory.

- [ ] **Step 4: GREEN and commit**

```powershell
uv run pytest -q tests/packaging/test_packaging_contract.py
uv run pytest -q
git add packaging/windows/research_workspace.spec packaging/windows/build_internal.ps1 packaging/windows/build_manifest.py tests/packaging/test_packaging_contract.py
git commit -m "build: define the Gate 1 Windows bundle"
```

---

### Task 3: Verify resources, Qt plugins, parsers, migrations, and DLL closure

**Files:**
- Create: `packaging/windows/verify_bundle.py`
- Create: `tests/packaging/conftest.py`
- Create: `tests/packaging/test_bundle_inventory.py`

**Consumes:** Built package and `BUILD-MANIFEST.json`.

**Produces:** `verify_bundle(package_root: Path) -> VerificationReport` with stable failure codes.

- [ ] **Step 1: Write bundle-inventory RED tests**

```python
def test_bundle_contains_every_runtime_resource(bundle):
    assert bundle.alembic_heads == ("0002",)
    assert bundle.ui_files == expected_runtime_ui_files()
    assert bundle.contract_files == expected_contract_files()
    assert bundle.has_qwindows_plugin
    assert bundle.parser_imports == {"docx", "pypdf", "pptx"}
    assert bundle.fixture_files_in_app == set()
    assert bundle.test_kit_fixture_manifest_matches
```

Also assert every manifest hash/size, `ResearchWorkspace.exe`, `qwindows.dll`, QtUiTools support, both Alembic versions, schema validation files, notices, and ordinary-file/no-link rules. Reject missing/extra manifest members and any absolute path in the manifest.

- [ ] **Step 2: Observe RED, build, and implement verification**

```powershell
uv run pytest -q tests/packaging/test_bundle_inventory.py
& packaging/windows/build_internal.ps1 -OutputRoot $env:RW_INTERNAL_BUILD_ROOT
uv run python packaging/windows/verify_bundle.py $env:RW_INTERNAL_BUILD_ROOT
```

Expected first RED: no bundle/verifier. GREEN must fail with a stable resource or DLL code if any runtime item is missing; do not add broad hidden imports merely to silence the verifier.

- [ ] **Step 3: GREEN and commit**

```powershell
uv run pytest -q tests/packaging/test_bundle_inventory.py
uv run pytest -q
git add packaging/windows/verify_bundle.py tests/packaging/conftest.py tests/packaging/test_bundle_inventory.py
git commit -m "test: verify the Windows bundle inventory"
```

---

### Task 4: Prove packaged offline startup and writable data-directory behavior

**Files:**
- Create: `packaging/windows/run_smoke.ps1`
- Create: `tests/packaging/test_packaged_startup.py`

**Consumes:** Verified bundle.

**Produces:** Host smoke evidence for first launch, exact schema `0002`, graceful shutdown, and custom writable data-directory activation.

- [ ] **Step 1: Write packaged-startup RED tests**

```python
def test_packaged_exe_starts_offline_and_initializes_new_workspace(packaged_app, isolated_profile):
    result = run_startup_smoke(packaged_app, isolated_profile, network_disabled=True)
    assert result.window_seen and result.graceful_exit
    assert result.alembic_revision == "0002"
    assert result.workspace_layout_complete

def test_packaged_exe_writes_only_to_approved_profile_and_data_root(result):
    assert result.unexpected_written_paths == ()
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/packaging/test_packaged_startup.py`

Expected: FAIL because the packaged smoke runner is absent.

- [ ] **Step 3: Implement bounded process smoke**

`run_smoke.ps1` gives the process isolated `APPDATA`/`LOCALAPPDATA`, starts `ResearchWorkspace.exe`, waits for the main window and database, requests normal `CloseMainWindow()`, and times out by failing rather than force-reporting success. A second case pre-seeds `config.json` with a writable custom data directory. It verifies schema head, required tables/directories, logs free of missing-DLL/import errors, and no writes under `app/`.

Offline proof is run in the network-disabled Sandbox in Task 6; the host test must not create firewall rules or require administrator privileges.

- [ ] **Step 4: GREEN and commit**

```powershell
uv run pytest -q tests/packaging/test_packaged_startup.py
uv run pytest -q
git add packaging/windows/run_smoke.ps1 tests/packaging/test_packaged_startup.py
git commit -m "test: smoke-test the packaged Gate 1 startup"
```

---

### Task 5: Exercise DOCX, PDF, and PPTX imports through the packaged UI

**Files:**
- Create: `tests/packaging/test_packaged_imports.py`

**Consumes:** Main executable, isolated writable workspace, pywinauto test driver, test-kit fixtures.

**Produces:** One packaged-UI smoke for each approved parser without adding a diagnostic or automation API to production.

- [ ] **Step 1: Write import RED tests**

```python
@pytest.mark.parametrize(
    ("fixture", "expected_status"),
    [
        ("docx/body_order.docx", "已导入，可检索文本"),
        ("pdf/normal_text.pdf", "已导入，可检索文本"),
        ("pptx/ordered_shapes.pptx", "已导入，可检索文本"),
    ],
)
def test_packaged_ui_imports_gate1_formats(packaged_ui, fixture, expected_status):
    record = packaged_ui.import_file(fixture)
    assert record.status_text == expected_status
    assert record.snapshot_exists and record.parse_artifact_registered
```

Add one image-only PDF assertion for the approved “已导入，无可提取文本，需要 OCR” state. The driver may invoke only visible implemented controls; it must not import Python modules from the source checkout into the packaged process.

- [ ] **Step 2: Observe RED and implement the external UI driver**

Run: `uv run pytest -q tests/packaging/test_packaged_imports.py`

Expected: FAIL until the external UI smoke driver can select files, wait for terminal status, close normally, and inspect the resulting database/snapshot files read-only after shutdown.

- [ ] **Step 3: GREEN and commit**

```powershell
uv run pytest -q tests/packaging/test_packaged_imports.py
uv run pytest -q
git add tests/packaging/test_packaged_imports.py
git commit -m "test: import Gate 1 formats through the Windows executable"
```

---

### Task 6: Run clean-machine, Defender, missing-DLL, and single-monitor DPI gates

**Files:**
- Create: `packaging/windows/ResearchWorkspaceInternal.wsb`
- Create: `packaging/windows/windows-internal-checklist.md`
- Modify: `packaging/windows/run_smoke.ps1`
- Create: `tests/packaging/test_packaging_checkpoint.py`
- Modify: `README.md`

**Consumes:** Hash-verified internal package; Windows Sandbox or clean Windows 10/11 VM with no project Python/uv environment.

**Produces:** Internal-package checkpoint evidence; does not produce a public release claim.

Native JSON reports, logs, and screenshots live under the required external path `RW_INTERNAL_EVIDENCE_ROOT`. `tests/packaging/conftest.py` fails closed when that path or any required evidence member is absent; it never substitutes repository fixtures for native evidence.

- [ ] **Step 1: Write the final evidence RED test**

```python
def test_internal_package_evidence_is_complete(evidence):
    assert evidence.clean_machine.python_installed is False
    assert evidence.network_enabled is False
    assert evidence.startup_and_imports_passed
    assert evidence.missing_dll_errors == ()
    assert evidence.defender.new_detections == ()
    assert evidence.single_monitor_scales == (100, 125, 150)
    assert evidence.rel_gate_001 == "BLOCKED_BY_ENVIRONMENT"
    assert evidence.public_release_ready is False
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/packaging/test_packaging_checkpoint.py`

Expected: FAIL because native evidence has not yet been recorded. Do not mark it skip/xfail if Sandbox, Defender, or display settings are unavailable; report the internal-package checkpoint as blocked by that environment.

- [ ] **Step 3: Execute the native checklist**

In Windows Sandbox or a clean VM:

1. Disable networking and confirm neither Python nor uv is installed.
2. Copy the complete hash-verified `onedir` package; never run it from a network share.
3. Launch, initialize a new workspace, close normally, restart, and verify persistence.
4. Import the DOCX, PDF, PPTX and image-only PDF smoke fixtures.
5. Select a separate writable data directory, restart, and verify activation without writing to `app/`.
6. Record absence of missing-DLL/plugin/import errors in process exit, application log, and Windows Application event log.
7. On the build host, record Defender engine/signature versions, run `Start-MpScan -ScanType CustomScan` on the package, and prove no new threat detection. Do not upload the package to an external scanning service.
8. At native single-monitor Windows scaling 100%, 125%, and 150%, launch the packaged executable and capture imports page/dialog screenshots with no clipping or unreachable controls.
9. Leave the two-monitor live transition unexecuted unless the approved hardware exists; retain `REL-GATE-001` as blocked regardless of single-monitor success.

- [ ] **Step 4: Final verification**

```powershell
git diff --check
uv run python tests/gate1/fixtures/build_fixtures.py --check
uv run pytest -q tests/packaging
uv run pytest -q tests/gate1
uv run pytest -q
uv run python packaging/windows/verify_bundle.py $env:RW_INTERNAL_BUILD_ROOT
git status --short
```

Expected: no failures/errors/skips/xfails/warnings; Gate 1 remains green; bundle and fixture manifests match; only intentional plan-approved source changes appear before commit.

- [ ] **Step 5: Commit and stop**

```powershell
git add packaging/windows/ResearchWorkspaceInternal.wsb packaging/windows/windows-internal-checklist.md packaging/windows/run_smoke.ps1 tests/packaging/test_packaging_checkpoint.py README.md
git commit -m "test: verify the Gate 1 Windows internal package"
git status --short
```

Submit commit, branch, exact package SHA-256/manifest, resolved licenses, changed files, literal test counts, clean-machine OS facts, Defender result, missing-DLL evidence, data-directory result, import matrix, 100/125/150 screenshots, deviations, and the unchanged `REL-GATE-001` status. Stop; do not start Gate 2.

## Internal Packaging Acceptance Map

| ID | Criterion | Exact evidence |
|---|---|---|
| PKG-AC01 | Exact packager/test closure is locked, noticed, and commercially approved | `test_packager_license.py`, existing license policy |
| PKG-AC02 | Reproducible windowed onedir/no-UPX build from exact Git SHA | `test_packaging_contract.py`, build manifest |
| PKG-AC03 | Qt plugins, `.ui`, schemas, Alembic 0001/0002, parsers and notices are complete | `test_bundle_inventory.py`, `verify_bundle.py` |
| PKG-AC04 | Test fixtures are 14/14 valid and excluded from runtime app content | `test_bundle_inventory.py`, fixture builder `--check` |
| PKG-AC05 | Package starts offline without installed Python and initializes schema 0002 | `test_packaged_startup.py`, clean-machine evidence |
| PKG-AC06 | Runtime writes only to approved config/data directories | `test_packaged_startup.py` |
| PKG-AC07 | Packaged UI imports DOCX/PDF/PPTX and preserves image-only PDF semantics | `test_packaged_imports.py` |
| PKG-AC08 | No missing DLL/Qt plugin error on a clean Windows 10/11 machine | Sandbox/VM checklist and Windows event evidence |
| PKG-AC09 | Microsoft Defender reports no new detection for the exact package hash | Defender evidence |
| PKG-AC10 | Native single-monitor 100/125/150% layouts pass | screenshots/checklist plus existing DPI tests |
| PKG-AC11 | Gate 1/full regressions stay green with no skip/xfail/warnings | final pytest sequence |
| PKG-AC12 | Mixed-DPI remains truthful and public release is not claimed | checkpoint report: `REL-GATE-001 = BLOCKED_BY_ENVIRONMENT` |

## Hard Stops and Non-goals

- A packager or transitive license that is unknown, incompatible, or not tied to the exact lockfile stops before build.
- If PyInstaller requires a production resource-path change, an unrestricted hidden-import sweep, runtime network access, or disabling a security test, stop for review.
- A missing DLL/plugin, Defender detection, nonempty write under `app/`, schema other than exact `0002`, fixture mismatch, parser smoke failure, or test regression blocks internal package acceptance.
- Windows Sandbox absence is not converted to skip/xfail; use a documented clean VM or report the packaging checkpoint blocked.
- This plan does not create an installer/MSIX, code signing, auto-update, crash telemetry, public download, Gate 2 feature, or public-release-ready claim.
- `REL-GATE-001` can close only on the separately approved packaged release candidate with the required physical mixed-DPI monitor transition.
