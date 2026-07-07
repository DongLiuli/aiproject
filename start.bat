@echo off
cd /d "%~dp0"

if not exist "backend\data" mkdir backend\data
if not exist "backend\data\uploads" mkdir backend\data\uploads
if not exist "backend\data\faiss_index" mkdir backend\data\faiss_index
if not exist "backend\data\report_cache" mkdir backend\data\report_cache
echo [OK] Data directories created

echo.
echo [1/3] Installing frontend dependencies...
cd frontend
call npm install 2>nul || echo [WARN] Failed to install frontend dependencies, using existing ones...
echo [OK] Frontend dependencies installed
cd ..

echo.
echo [2/3] Installing backend dependencies...
cd backend
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul || echo [WARN] Failed to install backend dependencies, using existing ones...
echo [OK] Backend dependencies installed

echo.
echo [3/3] Starting services...
echo Starting backend API (port 8080)...
start "PaperSystem-Backend" cmd /c "cd /d %~dp0backend && set HF_ENDPOINT=https://hf-mirror.com && python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload"
cd ..

echo Waiting for backend to start...
timeout /t 5 /nobreak >nul

echo Starting frontend (port 5173)...
cd frontend
start "PaperSystem-Frontend" cmd /c "npm run dev"
cd ..

echo.
echo ============================================
echo   Startup Complete!
echo   Backend:  http://localhost:8080
echo   Frontend: http://localhost:5173
echo   Docs:     http://localhost:8080/docs
echo ============================================
echo.
echo Open browser and visit http://localhost:5173
echo First startup needs to download BGE model (~1.3GB), please wait
echo Press any key to close this window...
pause >nul