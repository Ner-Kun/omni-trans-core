DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

LAUNCHER_PATH="launcher/start.py"

if [ ! -f "$LAUNCHER_PATH" ]; then
    echo "Launcher not found. Downloading..."
    URL="https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/launcher/start.py"
    LAUNCHER_DIR="launcher"
    
    mkdir -p "$LAUNCHER_DIR"
    
    if curl -fsSL -o "$LAUNCHER_PATH" "$URL"; then
        echo "Launcher downloaded successfully."
    else
        echo "Failed to download launcher. Please check your internet connection."
        exit 1
    fi
fi

python3 "$LAUNCHER_PATH" "$@"