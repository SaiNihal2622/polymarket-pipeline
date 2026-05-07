@echo off
REM ── Switch Cline model config ──────────────────────────────────────────────
REM Usage: switch_cline_model.bat [coding|image]
REM   coding = Qwen3 Coder 480B via NVIDIA (best for code, no images)
REM   image  = MiMo v2 Omni (supports screenshots/images)

if "%1"=="image" (
    powershell -Command "Copy-Item -Path cline-mimo-config.json -Destination cline_config.json -Force"
    echo Switched to: MiMo v2 Omni (image support)
    echo Restart Cline to apply.
) else if "%1"=="coding" (
    powershell -Command "Copy-Item -Path cline-coding-config.json -Destination cline_config.json -Force"
    echo Switched to: Qwen3 Coder 480B via NVIDIA (best for coding)
    echo Restart Cline to apply.
) else (
    echo.
    echo Usage: switch_cline_model.bat [coding^|image]
    echo.
    echo   coding  - Qwen3 Coder 480B via NVIDIA (best for code, no images)
    echo   image   - MiMo v2 Omni via Xiaomi (supports screenshots/images)
    echo.
    echo Current config:
    if exist cline_config.json (
        findstr "Model" cline_config.json
    ) else (
        echo   No active config. Run: switch_cline_model.bat coding
    )
)