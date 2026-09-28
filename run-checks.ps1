param([string]$Docker = "C:\Users\Jean-Christophe\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$config = Get-Content -LiteralPath './compose.yaml' -Raw -Encoding UTF8 | ConvertFrom-Json
$databases = @{}
foreach ($mount in $config.services.checks.volumes) {
    if ($mount.type -eq 'bind' -and $mount.target -like '/corpus/*' -and $mount.source -match '\.(db|sqlite)$') {
        $active = $false
        foreach ($suffix in @('-wal', '-journal')) {
            $journal = $mount.source + $suffix
            if ((Test-Path -LiteralPath $journal) -and (Get-Item -LiteralPath $journal).Length -gt 0) { $active = $true }
        }
        $databases[$mount.target.Substring(8)] = @{ exists = (Test-Path -LiteralPath $mount.source -PathType Leaf); active_journal = $active }
    }
}
$runtime = Join-Path $PSScriptRoot '.runtime'
[System.IO.Directory]::CreateDirectory($runtime) | Out-Null
$report = @{ checked_at_epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); databases = $databases } | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText((Join-Path $runtime 'corpus-preflight.json'), $report, [System.Text.UTF8Encoding]::new($false))
& $Docker compose --profile checks run --rm --no-deps checks
if ($LASTEXITCODE -ne 0) { throw 'Le conteneur de contrôle a échoué.' }
