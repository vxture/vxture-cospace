$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$name = 'cospace-lifecycle-eval-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$password = [guid]::NewGuid().ToString('N')
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$imageId = & docker image inspect postgres:18 --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Local postgres:18 image required' }
$results = Join-Path $repoRoot 'experiments/runs/p2-lifecycle-001'
New-Item -ItemType Directory -Force -Path $results | Out-Null
& docker image inspect $imageId | Set-Content (Join-Path $results 'postgres-image.json') -Encoding utf8
try {
    & docker run --detach --rm --pull never --name $name --cpus 1 --memory 512m --pids-limit 128 `
        --publish '127.0.0.1::5432' --env "POSTGRES_PASSWORD=$password" `
        --env POSTGRES_DB=cospace_eval --tmpfs '/var/lib/postgresql:rw,size=256m' $imageId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Database start failed' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        & docker exec $name pg_isready -U postgres -d cospace_eval *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Database readiness timeout' }
    $binding = & docker port $name 5432/tcp
    $port = ($binding.Trim() -split ':')[-1]
    $env:COSPACE_TEST_DATABASE_URL = "postgresql+psycopg://postgres:${password}@127.0.0.1:${port}/cospace_eval"
    Push-Location $repoRoot
    try {
        & $python -m pytest -q --tb=short --junitxml (Join-Path $results 'tests.xml') *> (Join-Path $results 'tests.log')
        $testExit = $LASTEXITCODE
        Get-Content (Join-Path $results 'tests.log')
        if ($testExit -ne 0) { throw 'PostgreSQL lifecycle tests failed' }
    } finally { Pop-Location }
} finally {
    Remove-Item Env:COSPACE_TEST_DATABASE_URL -ErrorAction SilentlyContinue
    & docker rm --force $name *> $null
}
