import shutil
import zipfile
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from http.client import HTTPResponse
from pathlib import Path
from typing import Any

import requests

from general.exception import MissingArgumentError
from general.tools.downloader import HTTPDownloader

from ..exception import DateLowerThanPublicError


class SERPRO:
    PUBLIC_MIN_DATE = date(2023, 5, 1)
    PUBLIC_URL_MODEL = "https://arquivos.receitafederal.gov.br/public.php/dav/files/gn672Ad4CF8N6TK/Dados/Cadastros/CNPJ/{year}-{month}/?accept=zip"

    @classmethod
    def download(cls, month: str, year: str) -> requests.Response:
        return HTTPDownloader.download(
            cls.PUBLIC_URL_MODEL.format(month=f"{month:0>2}", year=f"{year:0>4}")
        )


class CNPJ:
    @classmethod
    def get_month_year(cls, month: int, year: int) -> date:
        date_defined = month is not None and year is not None
        just_month_defined = month is not None and year is None

        if not date_defined:
            to_check = SERPRO.PUBLIC_MIN_DATE
        elif date_defined:
            to_check = date(year, month, 1)
        elif just_month_defined:
            raise MissingArgumentError("year")
        else:
            if year < SERPRO.PUBLIC_MIN_DATE.year:
                raise DateLowerThanPublicError()
            elif year == SERPRO.PUBLIC_MIN_DATE.year:
                month = 5
            else:
                month = 1

            to_check = date(year, month, 1)

        if to_check < SERPRO.PUBLIC_MIN_DATE:
            raise DateLowerThanPublicError()
        return to_check

    @staticmethod
    def __months(starter_date: date) -> Generator[date]:
        now_date = datetime.now(tz=timezone.utc).date()

        while starter_date <= now_date:

            yield starter_date
            starter_date = (starter_date + timedelta(days=31)).replace(day=1)

    @staticmethod
    def __create_temp_folder() -> Path:
        path = Path("./temp/")
        path.mkdir(parents=True, exist_ok=True)

        return path

    @staticmethod
    def __create_file(target_file: Path, streaming_data: HTTPResponse | Any):
        with open(target_file, "wb") as output_file:
            shutil.copyfileobj(streaming_data, output_file)

    @classmethod
    def downloaded_zips(cls, init_date: date) -> Generator[Path]:
        temp_path = cls.__create_temp_folder()

        for current_date in CNPJ.__months(init_date):
            download_file = temp_path.joinpath(
                f"{current_date.year:0>4}-{current_date.month:0>2}.zip"
            )

            if not download_file.exists():
                with SERPRO.download(
                    month=current_date.month, year=current_date.year
                ) as response:
                    cls.__create_file(download_file, response.raw)

            yield download_file

    @staticmethod
    def __get_file(zip_path_info: zipfile.ZipInfo) -> str:
        if zip_path_info.is_dir():
            return

        if not zip_path_info.filename.endswith(".zip"):
            print(f"[WARN] Caminho {zip_path_info.filename} não é um zip.")
            return

        return zip_path_info.filename

    @classmethod
    def process(cls):
        # TODO: futuramente será passado o nome do último arquivo
        # baixado, corretamente interpretado para mês e ano.
        target_date = CNPJ.get_month_year(month=None, year=None)

        for i in CNPJ.downloaded_zips(target_date):
            with zipfile.ZipFile(i, "r") as zip_handler:
                for zip_path_info in zip_handler.filelist:
                    file = cls.__get_file(zip_path_info)
                    if not file is None:
                        with (
                            zip_handler.open(file) as inner_zip_stream,
                            zipfile.ZipFile(inner_zip_stream) as inner_zip_handler,
                            inner_zip_handler.open(
                                inner_zip_handler.filelist[0]
                            ) as deepest_inner_file,
                        ):
                            for line in deepest_inner_file:
                                # Leitura de zip aninhado
                                # com uso de memória otimizada
                                line.decode("latin-1").strip()
