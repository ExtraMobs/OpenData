from abc import ABC, abstractmethod


class Downloader(ABC):
    base_url: str

    def __init__(self, base_url: str):
        self.base_url = base_url

    @abstractmethod
    def download(self):
        pass


class HTTPDownloader(Downloader):
    @abstractmethod
    def download(self):
        pass
