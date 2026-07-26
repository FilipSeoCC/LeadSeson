@echo off
title LeadSeason
echo.
echo ==========================================
echo              LeadSeason
echo ==========================================
echo.
streamlit run bulk_app.py --server.port 8510 --server.headless true
pause
