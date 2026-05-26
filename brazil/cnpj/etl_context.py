from dataclasses import dataclass
from typing import Dict


@dataclass
class CNPJContext:
    Cnaes: Dict[str, str]


etl_context = CNPJContext(Cnaes={})
