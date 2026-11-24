@echo off
rem Portable launcher: uses this repo's hub package, no absolute paths.
rem Override the interpreter with NSA_PYTHON if needed.
chcp 65001 >nul
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0..\..\hub"
if defined NSA_PYTHON goto :run
set "NSA_PYTHON=python"
where py >nul 2>nul && set "NSA_PYTHON=py -3"
:run
%NSA_PYTHON% -m nsa_mcp_hub.servers.nx_mcp %*
