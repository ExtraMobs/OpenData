import csv
import os
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from pprint import pp
from typing import Generator

import requests

from brazil.cnpj.raw_dataset_types import RawDataset
from brazil.exception import LowerMinDateError
from general.exception import MissingArgumentError


class CNPJ:
    PUBLIC_MIN_DATE = datetime.strptime("2023-05", "%Y-%m")
    PUBLIC_URL_MODEL = "https://arquivos.receitafederal.gov.br/public.php/dav/files/gn672Ad4CF8N6TK/Dados/Cadastros/CNPJ/{year}-{month}/?accept=zip"

    @classmethod
    def validate_month_year(cls, month: str, year: str) -> datetime:
        date_undefined = month is None and year is None
        date_defined = month is not None and year is not None
        just_month_defined = month is not None and year is None

        if date_undefined:
            to_check = cls.PUBLIC_MIN_DATE
        elif date_defined:
            to_check = datetime.strptime(f"{month}-{year}", "%Y-%m")
        elif just_month_defined:
            raise MissingArgumentError("year")
        else:
            if not year.isdigit():
                raise ValueError("Parâmetro 'year' deve ser um número.")
            _year = int(year)

            if _year < cls.PUBLIC_MIN_DATE.year:
                raise LowerMinDateError()
            elif _year == cls.PUBLIC_MIN_DATE.year:
                _month = 5
            else:
                _month = 1

            to_check = datetime.strptime(f"{_month:0>2}-{_year:0>4}", "%Y-%m")

        if to_check < cls.PUBLIC_MIN_DATE:
            raise LowerMinDateError()
        return to_check

    @staticmethod
    def __month_iterator(starter_date: date):
        now_date = datetime.now().date()

        while starter_date <= now_date:

            yield starter_date
            starter_date = (starter_date + timedelta(days=31)).replace(day=1)

    @staticmethod
    def downloaded_months(starter_month: int, starter_year: int) -> Generator[Path]:
        path = Path("./temp/")
        path.mkdir(parents=True, exist_ok=True)

        starter_date_as_string = f"{starter_year:0>4}-{starter_month:0>2}"
        from_date = datetime.strptime(starter_date_as_string, "%Y-%m").date()

        for target_date in CNPJ.__month_iterator(from_date):
            file_path = path.joinpath(
                f"{target_date.year:0>4}-{target_date.month:0>2}.zip"
            )

            if not file_path.exists():
                with requests.get(
                    CNPJ.PUBLIC_URL_MODEL.format(
                        month=f"{starter_month:0>2}", year=f"{starter_year:0>4}"
                    ),
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    with open(file_path, "wb") as output_file:
                        shutil.copyfileobj(response.raw, output_file)

            yield file_path

    @staticmethod
    def process():
        target_date = CNPJ.validate_month_year(None, None)

        for i in CNPJ.downloaded_months(
            starter_month=target_date.month, starter_year=target_date.year
        ):
            with zipfile.ZipFile(i, "r") as zip_ref:
                for file_info in zip_ref.filelist:

                    if file_info.is_dir():
                        continue

                    if not file_info.filename.endswith(".zip"):
                        print(
                            f"Caminho {file_info.filename} do arquivo {i.name} não é um zip."
                        )
                        continue

                    extracted_path = Path(
                        zip_ref.extract(file_info, path="./temp/")
                    ).absolute()

                    _type = RawDataset.type_from_filename(extracted_path)
                    if _type == None:
                        continue

                    _type.process(extracted_path)

            shutil.rmtree(i.parent.joinpath(i.stem))
