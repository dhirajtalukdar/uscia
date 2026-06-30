@echo off
setlocal enabledelayedexpansion

echo.
echo  ============================================
echo   SAP IBP ABAP Internal MCP Server - Setup
echo  ============================================
echo.

set "INSTALL_DIR=%~dp0"

:: Check that the executable exists
if not exist "%INSTALL_DIR%sap-ibp-abap-int.exe" (
    echo ERROR: sap-ibp-abap-int.exe not found in %INSTALL_DIR%
    echo Please extract the full zip archive first.
    pause
    exit /b 1
)

:: Create .env if it doesn't exist
if not exist "%INSTALL_DIR%.env" (
    echo --- SAP Credentials Setup ---
    echo.
    echo Enter your SAP ADT connection details.
    echo Press Enter to skip a field ^(you can edit .env later^).
    echo.

    set /p SAP_URL="SAP Base URL [https://your-sap-system.sap.corp]: "
    if "!SAP_URL!"=="" set "SAP_URL=https://your-sap-system.sap.corp"

    set /p SAP_USER="SAP Username: "
    set /p SAP_PASS="SAP Password: "

    (
        echo SAP_BASE_URL=!SAP_URL!
        echo SAP_USERNAME=!SAP_USER!
        echo SAP_PASSWORD=!SAP_PASS!
        echo # SAP_VERIFY_SSL=false
        echo # SAP_CLIENT=001
    ) > "%INSTALL_DIR%.env"

    echo.
    echo .env file created at %INSTALL_DIR%.env
    echo You can edit it later with any text editor.
    echo.
) else (
    echo Found existing .env file. Skipping credential setup.
    echo.
)

:: Detect Claude Code
where claude >nul 2>nul
if %errorlevel% equ 0 (
    echo --- Claude Code Registration ---
    echo.
    set /p REGISTER="Register with Claude Code? [Y/n]: "
    if /i "!REGISTER!"=="" set "REGISTER=Y"
    if /i "!REGISTER!"=="Y" (
        echo Registering MCP server with Claude Code...
        claude mcp add SAP-IBP-ABAP-INT -s user -- "%INSTALL_DIR%sap-ibp-abap-int.exe" --env-file "%INSTALL_DIR%.env"
        if !errorlevel! equ 0 (
            echo.
            echo Successfully registered! You can now use SAP IBP ABAP tools in Claude Code.
        ) else (
            echo.
            echo Registration failed. You can register manually later:
            echo   claude mcp add SAP-IBP-ABAP-INT -s user -- "%INSTALL_DIR%sap-ibp-abap-int.exe" --env-file "%INSTALL_DIR%.env"
        )
    )
) else (
    echo Claude Code CLI not found. Skipping auto-registration.
)

echo.
echo --- Manual Registration ---
echo.
echo To register with other AI clients, use these paths:
echo.
echo   Executable: %INSTALL_DIR%sap-ibp-abap-int.exe
echo   Env file:   %INSTALL_DIR%.env
echo.
echo Claude Code:
echo   claude mcp add SAP-IBP-ABAP-INT -s user -- "%INSTALL_DIR%sap-ibp-abap-int.exe" --env-file "%INSTALL_DIR%.env"
echo.
echo Cline / GitHub Copilot: use the executable path above in your settings.
echo.
echo Setup complete!
echo.
pause
