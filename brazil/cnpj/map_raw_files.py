import csv
import io
import zipfile
from typing import Iterable, List


class BaseRawFile:
    __map_index: dict[str, int]
    __main_data: List[List[str]]

    def __init__(self, zip_path, line_size, key_index):
        self.__map_index = {}
        self.__main_data = []

        for row in BaseRawFile.zip_iter_rows(zip_path):
            if len(row) != line_size:
                raise Exception()

            self.__map_index[row[key_index]] = len(self.__main_data)
            self.__main_data.append(row)

    def index_from_key(self, key: str):
        index = self.__map_index.get(key)
        if index is None:
            raise Exception()

        return index

    def data_from_index(self, index: int):
        return self.__main_data[index]

    @staticmethod
    def zip_iter_rows(zip_path: str) -> Iterable[List[str]]:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            file_buffer = zip_ref.open(zip_ref.namelist()[0], "r")
            csv_buffer = csv.reader(
                io.TextIOWrapper(file_buffer, encoding="latin-1"), delimiter=";"
            )

            for row in csv_buffer:
                if not row:
                    continue

                yield row


class Municipios(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Cnaes(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Motivos(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Naturezas(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Paises(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Qualificacoes(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 2, 0)


class Simples(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 7, 0)


class Empresas(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 7, 0)


class Estabelecimentos(BaseRawFile):
    def __init__(self, zip_path):
        super().__init__(zip_path, 30, 0)
