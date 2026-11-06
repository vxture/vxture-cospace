param([int]$Port = 8766, [switch]$Jobs)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$name = 'cospace-workbench-demo-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$password = [guid]::NewGuid().ToString('N')
$imageId = & docker image inspect postgres:18 --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Local postgres:18 image required' }
try {
    & docker run --detach --rm --pull never --name $name --cpus 1 --memory 512m --pids-limit 128 `
        --publish '127.0.0.1::5432' --env "POSTGRES_PASSWORD=$password" `
        --env POSTGRES_DB=cospace_demo --tmpfs '/var/lib/postgresql:rw,size=256m' $imageId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Database start failed' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        & docker exec $name pg_isready -U postgres -d cospace_demo *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Database readiness timeout' }
    $binding = & docker port $name 5432/tcp
    $dbPort = ($binding.Trim() -split ':')[-1]
    $env:COSPACE_DATABASE_URL = "postgresql+psycopg://postgres:${password}@127.0.0.1:${dbPort}/cospace_demo"
    Push-Location $repoRoot
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
        & $python -m apps.cli.releases register examples/indoor-spatial | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Registration failed' }
        & $python -m apps.cli.releases activate --scene synthetic-equipment-corridor --release release-spatial-sample-001 --expected-revision 0 --actor demo-engineer | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Activation failed' }
        if ($Jobs) {
            $env:COSPACE_DATA_ROOT = Join-Path $repoRoot ('var/' + $name)
            & $python -m experiments.scripts.seed_jobview
            if ($LASTEXITCODE -ne 0) { throw 'Job fixture failed' }
        }
        Write-Output "Temporary demo container: $name"
        Write-Output "Workbench: http://127.0.0.1:$Port/workbench/"
        & $python -m uvicorn apps.api.managed:managed_app --factory --host 127.0.0.1 --port $Port
    } finally { Pop-Location }
} finally {
    Remove-Item Env:COSPACE_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:COSPACE_DATA_ROOT -ErrorAction SilentlyContinue
    & docker rm --force $name *> $null
}
