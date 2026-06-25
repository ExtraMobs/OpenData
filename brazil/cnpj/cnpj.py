import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Generator

import requests

from general.exception import MissingArgumentError

from ..exception import LowerMinDateError
from .etl_context import EtlContext


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
            etl_context = EtlContext()

            zip_paths = {}

            with zipfile.ZipFile(i, "r") as zip_ref:
                for file_info in zip_ref.filelist:

                    if file_info.is_dir():
                        continue

                    if not file_info.filename.endswith(".zip"):
                        print(
                            f"Caminho {file_info.filename} do arquivo {i.name} não é um zip."
                        )
                        continue

                    tail_path = Path(file_info.filename)
                    target_extracted_path = Path("./temp/").absolute()

                    predicted_extracted_path = target_extracted_path.joinpath(tail_path)

                    zip_paths[predicted_extracted_path.stem.lower()] = (
                        predicted_extracted_path
                    )

                    if predicted_extracted_path.exists():
                        continue

                    zip_ref.extract(file_info, path=target_extracted_path)

            etl_context.update_from_zip_path(zip_paths.pop("cnaes"))
            etl_context.update_from_zip_path(zip_paths.pop("municipios"))
            etl_context.update_from_zip_path(zip_paths.pop("motivos"))
            etl_context.update_from_zip_path(zip_paths.pop("naturezas"))
            etl_context.update_from_zip_path(zip_paths.pop("paises"))
            etl_context.update_from_zip_path(zip_paths.pop("qualificacoes"))
            etl_context.update_from_zip_path(zip_paths.pop("simples"))

            for i in range(10):
                i = (i + 1) % 10
                path = zip_paths.pop(f"empresas{i}")
                etl_context.update_from_zip_path(path)
            
            etl_context.local_cache.execute_query("""
                CREATE INDEX idx_empresas_cnpj ON empresas (cnpj_basico);
            """)
            etl_context.local_cache.commit()

            for i in range(10):
                i = (i + 1) % 10
                path = zip_paths.pop(f"estabelecimentos{i}")
                etl_context.update_from_zip_path(path)
            
            etl_context.local_cache.execute_query("""
                CREATE INDEX idx_estabelecimentos_cnpj ON estabelecimentos (cnpj_basico, cnpj_ordem, cnpj_dv);
            """)
            etl_context.local_cache.commit()

            for i in range(10):
                i = (i + 1) % 10
                path = zip_paths.pop(f"socios{i}")
                etl_context.update_from_zip_path(path)
            
            etl_context.local_cache.execute_query("""
                CREATE INDEX idx_socios_cnpj ON socios (cnpj_basico);
            """)
            etl_context.local_cache.commit()

            etl_context.local_cache.close()
            shutil.rmtree(i.parent.joinpath(i.stem))
