from datetime import datetime

from brazil.exception import LowerMinDateError
from general.exception import MissingArgumentError


class CNPJ:
    PUBLIC_MIN_DATE = datetime.strptime("2023-05", "%Y-%m")

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

    @classmethod
    def download(cls, month=None, year=None):
        target_date = cls.validate_month_year(month, year)
