param(
    [switch]$NativeCpu,
    [string]$ProfileGenerate,
    [string]$ProfileUse,
    [string]$TargetDirectory = "Alpha/build/performance-target"
)
$ErrorActionPreference = "Stop"
if ($ProfileGenerate -and $ProfileUse) { throw "Select profile generation or use, not both." }
if ($ProfileUse -and !(Test-Path -LiteralPath $ProfileUse -PathType Leaf)) {
    throw "Merged LLVM profile does not exist: $ProfileUse"
}
$oldFlags = $env:RUSTFLAGS
try {
    $flags = @()
    if ($oldFlags) { $flags += $oldFlags }
    if ($NativeCpu) { $flags += "-C target-cpu=native" }
    if ($ProfileGenerate) { $flags += "-C profile-generate=$([IO.Path]::GetFullPath($ProfileGenerate))" }
    if ($ProfileUse) {
        $flags += "-C profile-use=$([IO.Path]::GetFullPath($ProfileUse))"
        $flags += "-C llvm-args=-pgo-warn-missing-function"
    }
    $env:RUSTFLAGS = $flags -join " "
    & cargo build --profile performance -j 1 --manifest-path Alpha/vendor/nokamute/Cargo.toml --target-dir $TargetDirectory
    if ($LASTEXITCODE -ne 0) { throw "Cargo failed: $LASTEXITCODE" }
    $exe = Join-Path $TargetDirectory "performance/alpha_nokamute_mit.exe"
    [ordered]@{
        executable = [IO.Path]::GetFullPath($exe)
        sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
        rustflags = $env:RUSTFLAGS
        native_cpu = [bool]$NativeCpu
        profile_generate = $ProfileGenerate
        profile_use = $ProfileUse
        compiler = (& rustc --version)
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $TargetDirectory "build-manifest.json")
} finally { $env:RUSTFLAGS = $oldFlags }
