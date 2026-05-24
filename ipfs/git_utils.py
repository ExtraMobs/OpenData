import subprocess
from typing import List


class GitTag:
    def __init__(self, hash: str, tag: str):
        self.hash = hash
        self.tag = tag

    @staticmethod
    def from_cli_ordered(repository_url: str) -> List[GitTag]:
        result = subprocess.run(
            args=[
                "git",
                "ls-remote",
                "--tags",
                "--refs",
                "--sort=-v:refname",
                repository_url,
            ],
            capture_output=True,
        )

        to_result = []
        for line in result.stdout.decode("utf-8").split("\n"):
            if len(line) == 0:
                continue

            to_result.append(GitTag.__from_line(line))

        return to_result

    def __repr__(self):
        return f"{self.tag}"

    @staticmethod
    def __from_line(line: bytes):
        hash, tag = line.split("\t")
        return GitTag(hash=hash, tag=tag)

    @staticmethod
    def get_lastest(tags: List[GitTag]) -> GitTag:
        for tag in tags:
            if tag.tag.split(".")[-1].isdigit():
                return tag
