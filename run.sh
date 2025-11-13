echo "Starting Omni Trans Launcher..."
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"
python3 launcher/start.py "$@"