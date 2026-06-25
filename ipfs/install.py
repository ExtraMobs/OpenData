import io
import sys
import tarfile
import zipfile

import requests

from globals import APP_FOLDER
from ipfs.git_utils import GitTag


def ipfs_is_installed():
    ipfs_bin_path = APP_FOLDER.joinpath("bin/kubo/")

    return ipfs_bin_path.exists()


def download_ipfs(tag: GitTag):
    os_name = sys.platform
    version = tag.tag[10:]

    if os_name == "win32":
        filename = f"kubo_{version}_windows-amd64.zip"
    else:
        filename = f"kubo_{version}_linux-amd64.tar.gz"

    url = f"https://github.com/ipfs/kubo/releases/download/{version}/{filename}"

    response = requests.get(url)

    if response.status_code == 200:
        content = io.BytesIO(response.content)

        extract_path = APP_FOLDER.joinpath("bin/")

        if os_name == "win32":
            with zipfile.ZipFile(content) as zip_ref:
                zip_ref.extractall(extract_path)
        else:
            with tarfile.open(fileobj=content) as tar:
                tar.extractall(extract_path)
    else:
        raise NotImplementedError(f"Falha ao baixar IPFS: {response.status_code}")


def install_ipfs():
    refs = GitTag.from_cli_ordered("https://github.com/ipfs/kubo.git")
    ref = GitTag.get_lastest(refs)

    download_ipfs(ref)
