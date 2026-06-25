import csv
import io
from pathlib import Path
from typing import Iterable, List

from general.tools.nested_zip import NestedZipReader


def iter_nested_csv(base_zip: Path, internal_path: str) -> Iterable[List[str]]:
    full_path = base_zip / internal_path

    with NestedZipReader(full_path, encoding="latin1") as reader:
        with reader.open_entry(reader._leaf_name) as file_buffer:
            csv_buffer = csv.reader(
                io.TextIOWrapper(file_buffer, encoding="latin1"), delimiter=";"
            )

            for row in csv_buffer:
                if not row:
                    continue
                yield row


file_path = ""  # to tests
base = Path(file_path).absolute()
if base.exists() and base.is_file():
    with NestedZipReader(base) as reader:
        for path in reader.walk():
            if NestedZipReader.is_path_leaf(path):
                for row in iter_nested_csv(base, path):
                    pass
                print(path)
