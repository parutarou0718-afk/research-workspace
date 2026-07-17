[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,

    [Parameter(Mandatory = $true)]
    [string]$IconPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProductTag = "v0.2-personal"
$ProductCommit = "fe8e38bfa88a1a7c7282d46fbd42e9da97af2c43"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ResolvedIcon = (Resolve-Path -LiteralPath $IconPath).Path

if (-not (Test-Path -LiteralPath $OutputRoot)) {
    New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}
$ResolvedOutput = (Resolve-Path -LiteralPath $OutputRoot).Path
$projectPrefix = $ProjectRoot.TrimEnd("\") + "\"
if (
    $ResolvedOutput.Equals($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedOutput.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw "Portable output must be outside the Git worktree."
}

$dirty = (& git -C $ProjectRoot status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty) {
    throw "Build source must be a clean Git worktree."
}

$tagTarget = (& git -C $ProjectRoot rev-list -n 1 $ProductTag).Trim()
if ($LASTEXITCODE -ne 0 -or $tagTarget -ne $ProductCommit) {
    throw "The v0.2-personal tag does not identify the approved product commit."
}
& git -C $ProjectRoot merge-base --is-ancestor $ProductCommit HEAD
if ($LASTEXITCODE -ne 0) {
    throw "The build commit does not descend from the approved product commit."
}
$BuildCommit = (& git -C $ProjectRoot rev-parse HEAD).Trim()

$PackageName = "ResearchWorkspace-v0.2-personal-win64"
$PackageRoot = Join-Path $ResolvedOutput $PackageName
$ZipPath = Join-Path $ResolvedOutput "$PackageName.zip"
$WorkRoot = Join-Path $ResolvedOutput ".portable-build-$BuildCommit"
if ((Test-Path -LiteralPath $PackageRoot) -or (Test-Path -LiteralPath $ZipPath)) {
    throw "Portable package output already exists."
}

New-Item -ItemType Directory -Path $WorkRoot | Out-Null
try {
    $env:RW_PORTABLE_ICON = $ResolvedIcon
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }

    & uv run pyinstaller --clean --noconfirm `
        (Join-Path $PSScriptRoot "research_workspace.spec") `
        --distpath (Join-Path $WorkRoot "dist") `
        --workpath (Join-Path $WorkRoot "work")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    $AppRoot = Join-Path $PackageRoot "app"
    New-Item -ItemType Directory -Path $PackageRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $WorkRoot "dist\ResearchWorkspace") `
        -Destination $AppRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "contracts") `
        -Destination (Join-Path $AppRoot "contracts") -Recurse
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "migrations") `
        -Destination (Join-Path $AppRoot "migrations") -Recurse
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md") `
        -Destination (Join-Path $AppRoot "THIRD_PARTY_NOTICES.md")

    $requiredMigration = Join-Path $AppRoot `
        "migrations\versions\0004_gate3_protected_crud.py"
    if (-not (Test-Path -LiteralPath $requiredMigration)) {
        throw "Gate 3 migration is missing from the portable package."
    }

    & uv run python (Join-Path $PSScriptRoot "build_manifest.py") `
        $PackageRoot `
        --product-tag $ProductTag `
        --product-commit $ProductCommit `
        --build-commit $BuildCommit
    if ($LASTEXITCODE -ne 0) { throw "Manifest generation failed." }
    if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot "BUILD-MANIFEST.json"))) {
        throw "BUILD-MANIFEST.json was not generated."
    }

    Compress-Archive -LiteralPath $PackageRoot -DestinationPath $ZipPath `
        -CompressionLevel Optimal
    $ZipSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLower()
    [ordered]@{
        package_root = $PackageRoot
        zip_path = $ZipPath
        zip_sha256 = $ZipSha256
        product_commit = $ProductCommit
        build_commit = $BuildCommit
    } | ConvertTo-Json
}
finally {
    Remove-Item -LiteralPath $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
}
