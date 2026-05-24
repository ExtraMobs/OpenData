import io
import sys
import tarfile
from pathlib import Path

import requests

from globals import APP_FOLDER
from ipfs.git_utils import GitTag


def ipfs_is_installed():
    ipfs_bin_path = APP_FOLDER.joinpath("bin/kubo/")

    return ipfs_bin_path.exists()


def download_ipfs(tag: GitTag):
    url = f"https://github.com/ipfs/kubo/releases/download/v0.41.0/kubo_{tag.tag[10:]}_linux-amd64.tar.gz"

    response = requests.get(url)

    if response.status_code == 200:
        content = io.BytesIO(response.content)

        with tarfile.open(fileobj=content) as tar:
            tar.extractall(APP_FOLDER.joinpath("bin/"))
    else:
        raise NotImplementedError()


def install_ipfs():
    refs = GitTag.from_cli_ordered("https://github.com/ipfs/kubo.git")
    ref = GitTag.get_lastest(refs)

    download_ipfs(ref)
