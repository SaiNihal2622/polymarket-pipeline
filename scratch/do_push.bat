@echo off
cd /d c:\Users\saini\Desktop\iplclaude\polymarket-pipeline
git add -A
git commit -m "fix: aggressive trade engine with persistent storage"
git push origin main
echo DONE