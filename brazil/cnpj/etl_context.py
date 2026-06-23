from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .map_raw_files import (Cnaes, Empresas, Estabelecimentos, Motivos,
                            Municipios, Naturezas, Paises, Qualificacoes,
                            Simples)



@dataclass
class EtlContext:
    CNAEs: Cnaes
    municipios: Municipios
    motivos: Motivos
    naturezas: Naturezas
    paises: Paises
    qualificacoes: Qualificacoes
    simples: Simples
    estabelecimentos: Estabelecimentos
    empresas: Empresas

    def __init__(self):
        pass

    def update_from_zip_path(self, zip_path: Path):
        stem = zip_path.stem.lower()
        if stem == "cnaes":
            self.CNAEs = Cnaes(zip_path)
        elif stem == "municipios":
            self.municipios = Municipios(zip_path)
        elif stem == "motivos":
            self.motivos = Motivos(zip_path)
        elif stem == "naturezas":
            self.naturezas = Naturezas(zip_path)
        elif stem == "paises":
            self.paises = Paises(zip_path)
        elif stem == "qualificacoes":
            self.qualificacoes = Qualificacoes(zip_path)
        elif stem == "simples":
            self.simples = Simples(zip_path)
        elif stem.startswith("estabelecimentos"):
            self.estabelecimentos = Estabelecimentos(zip_path)
        elif stem.startswith("empresas"):
            self.empresas = Empresas(zip_path)
        else:
            raise Exception()
