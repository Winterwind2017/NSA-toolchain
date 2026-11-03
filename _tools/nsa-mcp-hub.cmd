@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONPATH=D:\bililive\kitmcp
"C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe" -m kitmcp.servers.nsa_hub_mcp %*
