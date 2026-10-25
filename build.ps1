# Build do app desktop "Secretaria EBD" (Windows, pasta autónoma, offline).
# Pré-requisito: venv criado e requirements-app.txt instalado (ver README no histórico).
# Uso:  .\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host '[1/3] A instalar dependências de build...'
& .\venv\Scripts\pip.exe install -r requirements-app.txt

Write-Host '[2/3] A compilar (flet pack, onedir, runtime Flet embutido)...'
& .\venv\Scripts\flet.exe pack main.py -n 'Secretaria EBD' -D --product-name 'Secretaria EBD' -y
if ($LASTEXITCODE -ne 0) { throw 'Build falhou (flet pack).' }

Write-Host '[3/3] A copiar ficheiros de configuração/dados para a pasta da app...'
Copy-Item config.json, database.sqlite 'dist\Secretaria EBD\' -Force
Remove-Item 'dist\Secretaria EBD\erro.log' -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Build pronto.' -ForegroundColor Green
Write-Host '  App:      dist\Secretaria EBD\'
Write-Host '  Distrib.: compactar a pasta "dist\Secretaria EBD" em .zip e levar no pen.'
Write-Host '  Nota:     a 1ª execução extrai o runtime Flet para %USERPROFILE%\.flet (offline).'
