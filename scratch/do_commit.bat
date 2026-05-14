@echo off
cd /d c:\Users\saini\Desktop\iplclaude\polymarket-pipeline
git add web_dashboard.py
git commit -m "fix: dashboard config mismatch - env vars read first, defaults match demo_runner"
git push origin main