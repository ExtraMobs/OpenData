import json
import sys
from pathlib import Path
from subprocess import Popen

APP_FOLDER = Path(sys.modules["__main__"].__file__).resolve().parent
OS_NAME = sys.platform
CONFIGS = json.load(APP_FOLDER.joinpath("config.json").absolute().open("r"))
IPFS_DAEMON_PROCESS: Popen = None
IPFS_BIN_NAME = None
IPFS_BIN_PATH = None
IPFS_STORAGE_PATH = None
