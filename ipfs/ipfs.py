import json
import os
import subprocess
from collections.abc import Iterable

import requests

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
                args=[str(globals.IPFS_BIN_PATH), "init"],
                env=env_customizado,
                check=False,
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
            check=False,
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
            check=False,
        )

    @staticmethod
    def __config_swarm_port(bin_path, env, port):
        subprocess.run(
            args=[
                str(bin_path),
                "config",
                "--json",
                "Addresses.Swarm",
                f'["/ip4/0.0.0.0/tcp/{port}", "/ip4/0.0.0.0/udp/{port}/quic-v1"]',
            ],
            env=env,
            check=False,
        )


class IPFSRPC:
    API_URL = f"http://localhost:{globals.CONFIGS["api-port"]}/api/v0"
    __SESSION = requests.Session()

    @classmethod
    def dag_put(
        cls,
        data: dict[str],
        store_codec="dag-cbor",
        input_codec="dag-json",
        pin=False,
        hash="sha2-256",
        allow_big_block=False,
    ) -> str:
        r = cls.__SESSION.post(
            f"{cls.API_URL}/dag/put",
            params={
                "store-codec": store_codec,
                "input-codec": input_codec,
                "pin": str(pin).lower(),
                "hash": hash,
                "allow-big-block": str(allow_big_block).lower(),
            },
            files=json.dumps(data, separators=(",", ":")),
        )
        r.raise_for_status()

        return r.json()["Cid"]["/"]

    @classmethod
    def dag_block(
        cls,
        data: list[Iterable[bytes]],
        cid_codec="raw",
        mhtype="sha2-256",
        mhlen=-1,
        pin=False,
        allow_big_block=False,
    ) -> list[str]:
        r = cls.__SESSION.post(
            f"{cls.API_URL}/block/put",
            params={
                "cid-codec": cid_codec,
                "mhtype": mhtype,
                "mhlen": mhlen,
                "pin": str(pin).lower(),
                "allow-big-block": str(allow_big_block).lower(),
            },
            files=data,
        )

        r.raise_for_status()
        b = [json.loads(c) for c in r.text.strip().split("\n")]
        return [k["Key"] for k in b]
