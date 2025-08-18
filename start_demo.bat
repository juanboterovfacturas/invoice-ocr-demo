@echo off
echo ===============================================
echo  Invoice OCR Demo - Moeed's Portfolio Project
echo ===============================================
echo.
echo Starting application...
echo Open your browser to: http://localhost:8502
echo.
echo Press Ctrl+C to stop the demo
echo ===============================================
echo.

cd /d %~dp0
call uv run streamlit run app.py --server.port=8502

pause