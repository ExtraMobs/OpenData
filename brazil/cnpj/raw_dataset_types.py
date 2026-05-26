import csv
import io
import zipfile
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol

from brazil.cnpj.etl_context import etl_context


@dataclass
class IRawDataSet(Protocol):
    @staticmethod
    def load_from_zip(zip_path: Path) -> Iterable[List[str]]:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            file_buffer = zip_ref.open(zip_ref.namelist()[0], "r")
            csv_buffer = csv.reader(
                io.TextIOWrapper(file_buffer, encoding="latin-1"), delimiter=";"
            )

            for row in csv_buffer:
                if not row:
                    continue

                yield row

    @staticmethod
    def process(zip_path: Path) -> None: ...

    @classmethod
    def get_fields_metadata(cls) -> Dict[str, Any]:
        return {field.name: field.metadata for field in fields(cls)}


@dataclass
class Cnaes(IRawDataSet):
    CODIGO: int = field(metadata={"index": 0})
    DESCRICAO: str = field(metadata={"index": 1})

    @staticmethod
    def process(zip_path: Path) -> Iterable[Cnaes]:
        metadata = Cnaes.get_fields_metadata()

        for line in Cnaes.load_from_zip(zip_path):
            cnae = Cnaes(
                CODIGO=line[metadata["CODIGO"]["index"]],
                DESCRICAO=line[metadata["DESCRICAO"]["index"]],
            )
            etl_context.Cnaes[cnae.CODIGO] = cnae.DESCRICAO


class RawDataset:
    @staticmethod
    def type_from_filename(filepath: Path) -> IRawDataSet | None:
        simple_filename = filepath.stem.lower().split("-")[0]
        if simple_filename == "cnaes":
            return Cnaes

        return None
