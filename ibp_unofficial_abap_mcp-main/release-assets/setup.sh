#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "  ============================================"
echo "   SAP IBP ABAP Internal MCP Server - Setup"
echo "  ============================================"
echo ""

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check that the executable exists
if [ ! -f "$INSTALL_DIR/sap-ibp-abap-int" ]; then
    echo "ERROR: sap-ibp-abap-int not found in $INSTALL_DIR"
    echo "Please extract the full archive first."
    exit 1
fi

chmod +x "$INSTALL_DIR/sap-ibp-abap-int"

# Create .env if it doesn't exist
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "--- SAP Credentials Setup ---"
    echo ""
    echo "Enter your SAP ADT connection details."
    echo "Press Enter to skip a field (you can edit .env later)."
    echo ""

    read -rp "SAP Base URL [https://your-sap-system.sap.corp]: " SAP_URL
    SAP_URL="${SAP_URL:-https://your-sap-system.sap.corp}"

    read -rp "SAP Username: " SAP_USER
    read -rsp "SAP Password: " SAP_PASS
    echo ""

    cat > "$INSTALL_DIR/.env" <<EOF
SAP_BASE_URL=$SAP_URL
SAP_USERNAME=$SAP_USER
SAP_PASSWORD=$SAP_PASS
# SAP_VERIFY_SSL=false
# SAP_CLIENT=001
EOF

    echo ""
    echo ".env file created at $INSTALL_DIR/.env"
    echo "You can edit it later with any text editor."
    echo ""
else
    echo "Found existing .env file. Skipping credential setup."
    echo ""
fi

# Detect Claude Code
if command -v claude &>/dev/null; then
    echo "--- Claude Code Registration ---"
    echo ""
    read -rp "Register with Claude Code? [Y/n]: " REGISTER
    REGISTER="${REGISTER:-Y}"

    if [[ "$REGISTER" =~ ^[Yy]$ ]]; then
        echo "Registering MCP server with Claude Code..."
        if claude mcp add SAP-IBP-ABAP-INT -s user -- "$INSTALL_DIR/sap-ibp-abap-int" --env-file "$INSTALL_DIR/.env"; then
            echo ""
            echo "Successfully registered! You can now use SAP IBP ABAP tools in Claude Code."
        else
            echo ""
            echo "Registration failed. You can register manually later:"
            echo "  claude mcp add SAP-IBP-ABAP-INT -s user -- \"$INSTALL_DIR/sap-ibp-abap-int\" --env-file \"$INSTALL_DIR/.env\""
        fi
    fi
else
    echo "Claude Code CLI not found. Skipping auto-registration."
fi

echo ""
echo "--- Manual Registration ---"
echo ""
echo "To register with other AI clients, use these paths:"
echo ""
echo "  Executable: $INSTALL_DIR/sap-ibp-abap-int"
echo "  Env file:   $INSTALL_DIR/.env"
echo ""
echo "Claude Code:"
echo "  claude mcp add SAP-IBP-ABAP-INT -s user -- \"$INSTALL_DIR/sap-ibp-abap-int\" --env-file \"$INSTALL_DIR/.env\""
echo ""
echo "Cline / GitHub Copilot: use the executable path above in your settings."
echo ""
echo "Setup complete!"
