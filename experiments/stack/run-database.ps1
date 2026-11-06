$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$containerName = 'cospace-stack-eval-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$password = [guid]::NewGuid().ToString('N')
$imageId = & docker image inspect postgres:18 --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Local postgres:18 image missing' }
$resultDir = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
& docker image inspect $imageId | Set-Content (Join-Path $resultDir 'postgres-image.json') -Encoding utf8
try {
    & docker run --detach --rm --pull never --name $containerName --cpus 1 --memory 512m --pids-limit 128 `
        --publish '127.0.0.1::5432' --env "POSTGRES_PASSWORD=$password" `
        --env POSTGRES_DB=cospace_eval --tmpfs '/var/lib/postgresql:rw,size=256m' $imageId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Database trial start failed' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        & docker exec $containerName pg_isready -U postgres -d cospace_eval *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Database trial readiness timeout' }
    $binding = & docker port $containerName 5432/tcp
    $port = ($binding.Trim() -split ':')[-1]
    $env:COSPACE_EVAL_DATABASE_URL = "postgresql+psycopg://postgres:${password}@127.0.0.1:${port}/cospace_eval"
    & (Join-Path $PSScriptRoot 'python/.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'python/evaluate.py')
    if ($LASTEXITCODE -ne 0) { throw 'Database compatibility checks failed' }
} finally {
    Remove-Item Env:COSPACE_EVAL_DATABASE_URL -ErrorAction SilentlyContinue
    & docker rm --force $containerName *> $null
}
