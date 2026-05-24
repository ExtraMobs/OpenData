import os
import subprocess

import globals

from .install import install_ipfs, ipfs_is_installed


class IPFS:
    @staticmethod
    def init():
        if not ipfs_is_installed():
            install_ipfs()

        globals.IPFS_BIN_NAME = "ipfs" + (".exe" if globals.OS_NAME == "win32" else "")
        globals.IPFS_BIN_PATH = globals.APP_FOLDER.joinpath(
            "bin", "kubo", globals.IPFS_BIN_NAME
        )

        globals.IPFS_STORAGE_PATH = globals.APP_FOLDER.absolute().joinpath(
            "storage", ".ipfs"
        )
        globals.IPFS_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

        env_customizado = os.environ.copy()
        env_customizado["IPFS_PATH"] = str(globals.IPFS_STORAGE_PATH)

        if not globals.IPFS_STORAGE_PATH.exists():
            subprocess.run(
                args=[str(globals.IPFS_BIN_PATH), "init"], env=env_customizado
            )

        IPFS.__config_api_port(
            globals.IPFS_BIN_PATH, env_customizado, globals.CONFIGS["api-port"]
        )
        IPFS.__config_gateway_port(
            globals.IPFS_BIN_PATH, env_customizado, globals.CONFIGS["gateway-port"]
        )
        IPFS.__config_swarm_port(
            globals.IPFS_BIN_PATH, env_customizado, globals.CONFIGS["swarm-port"]
        )

        globals.IPFS_DAEMON_PROCESS = subprocess.Popen(
            args=[str(globals.IPFS_BIN_PATH), "daemon"], env=env_customizado
        )

    def close_daemon():
        globals.IPFS_DAEMON_PROCESS.terminate()
        globals.IPFS_DAEMON_PROCESS.wait()

    @staticmethod
    def __config_api_port(bin_path, env, port):
        subprocess.run(
            args=[
                str(bin_path),
                "config",
                "Addresses.API",
                f"/ip4/127.0.0.1/tcp/{port}",
            ],
            env=env,
        )

    @staticmethod
    def __config_gateway_port(bin_path, env, port):
        subprocess.run(
            args=[
                str(bin_path),
                "config",
                "Addresses.Gateway",
                f"/ip4/127.0.0.1/tcp/{port}",
            ],
            env=env,
        )

    @staticmethod
    def __config_swarm_port(bin_path, env, port):
        subprocess.run(
            args=[
                str(bin_path),
                "config",
                "--json",
                "Addresses.Swarm",
                f'["/ip4/0.0.0.0/tcp/{port}", "/ip4/0.0.0.0/udp/{port}/quic-v1"]',  # Corrigido: Array JSON
            ],
            env=env,
        )
