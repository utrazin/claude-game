@echo off
setlocal
title Visualizador de Assets
where node >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Node.js nao encontrado no sistema!
  echo Para instalar, execute no terminal:
  echo   winget install OpenJS.NodeJS.LTS
  echo Ou baixe o instalador em: https://nodejs.org
  pause
  exit /b 1
)
if not exist "%~dp0..\..\tools\asset-kit\node_modules" (
  echo [SETUP] Dependencias nao encontradas. Instalando pacotes com npm...
  pushd "%~dp0..\..\tools\asset-kit"
  call npm install
  popd
)
echo Abrindo o visualizador. Se ja estiver ativo, o servidor sera reutilizado.
echo Mantenha a primeira janela aberta. Ctrl+C encerra o servidor.
node "%~dp0..\..\tools\asset-kit\cli.mjs" preview "%~dp0." --open
if errorlevel 1 pause
endlocal
