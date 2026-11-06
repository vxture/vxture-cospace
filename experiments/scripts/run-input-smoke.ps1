param(
    [Parameter(Mandatory=$true)][string]$Image,
    [string]$RunName = 'input-smoke-001'
)
$ErrorActionPreference = 'Stop'
if ($Image -notmatch '^ros@sha256:[a-f0-9]{64}$') {
    throw 'Use an inspected official ros image digest, not a mutable tag.'
}
if ($RunName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid run name.' }
$experimentRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$scriptsRoot = Join-Path $experimentRoot 'scripts'
$outputRoot = Join-Path $experimentRoot ('runs\' + $RunName)
if (Test-Path -LiteralPath $outputRoot) { throw 'Run directory already exists; use a new run name.' }
New-Item -ItemType Directory -Path $outputRoot | Out-Null
$imageMetadata = & docker image inspect $Image
if ($LASTEXITCODE -ne 0) { throw 'Pinned image is not available locally.' }
$imageMetadata | Set-Content -LiteralPath (Join-Path $outputRoot 'image-inspect.json') -Encoding utf8
$runRecord = [ordered]@{
    started_at_utc = [DateTime]::UtcNow.ToString('o')
    image = $Image
    data_kind = 'synthetic_test_fixture_not_truth'
    scripts = @(Get-ChildItem -LiteralPath $scriptsRoot -File | ForEach-Object {
        @{ name = $_.Name; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    limits = @{ network = 'none'; cpus = 2; memory = '2g'; pids = 128 }
}
$recordPath = Join-Path $outputRoot 'run-record.json'
$runRecord | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding utf8
& docker run --rm --pull never --network none --cpus 2 --memory 2g --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges `
    --mount "type=bind,source=$scriptsRoot,target=/work/scripts,readonly" `
    --mount "type=bind,source=$outputRoot,target=/work/output" `
    --env PYTHONDONTWRITEBYTECODE=1 $Image bash -lc `
    'source /opt/ros/noetic/setup.bash && python3 /work/scripts/smoke_rosbag.py /work/output'
$runExitCode = $LASTEXITCODE
$runRecord['finished_at_utc'] = [DateTime]::UtcNow.ToString('o')
$runRecord['exit_code'] = $runExitCode
$runRecord | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding utf8
if ($runExitCode -ne 0) { throw 'Input smoke failed; inspect run outputs.' }
Get-Content -LiteralPath (Join-Path $outputRoot 'summary.json')
