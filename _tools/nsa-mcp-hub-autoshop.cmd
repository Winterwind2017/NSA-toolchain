@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONPATH=D:\bililive\nsa-mcp-hub
"C:\Users\yuche\AppData\Local\Programs\Python\Python312\python.exe" -m nsa_mcp_hub.servers.autoshop_mcp %*
