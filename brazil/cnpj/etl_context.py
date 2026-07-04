from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from brazil.cnpj.local_cache import LocalCache

from .map_raw_files import (Cnaes, Empresas, Estabelecimentos, Motivos,
                            Municipios, Naturezas, Paises, Qualificacoes,
                            Simples, Socios)


@dataclass
class EntidadeEmresa:
    CNPJ: str[8]
    NomeEmpresarial: str
    NaturezaJuridica: str
    QualificacaoRepresentante: str
    CapitalSocial: float
    Porte: str
    EnteFederativoResponsavel: str


@dataclass
class DadosSociosAdmin:
    IdSocioAdmin: str
    Nome: str
    CpfCnpj: str
    Qualificacao: str
    DataInclusao: datetime
    CodigoPaisSocioAdmin: str
    FaixaEtaria: str
    NomeResponsavelLegal: str
    CpfResponsavelLegal: str
    QualificacaoResponsavelLegal: str


@dataclass
class DadosSimplesNacional:
    CNPJ: str[8]
    OpcaoSimplesNacional: str
    DataOpcaoSimplesNacional: datetime
    DataExclusaoSimplesNacional: datetime
    OpcaoMei: str
    DataOpcaoMei: datetime
    DataExclusaoMei: datetime


@dataclass
class DadosEstabelecimento:
    Tipo: str
    CNPJ: str[14]
    DataInscricao: datetime
    NomeFantasia: str
    SituacaoCadastral: str
    MotivoSituacaoCadastral: str
    DataSituacaoCadastral: datetime
    SituacaoEspecial: str
    DataSituacaoEspecial: datetime

    TipoLogradouro: str
    Logradouro: str
    Numero: str
    Complemento: str
    Bairro: str
    Municipio: str
    UF: str
    CEP: str
    Pais: str
    CidadeExterior: str

    Telefone: str
    Email: str
    FAX: str

    CNAEPrincipal: str
    CNAESecundario: str


class EtlContext:
    local_cache: LocalCache

    def __init__(self):
        self.local_cache = LocalCache("./temp")

    def update_from_zip_path(self, zip_path: Path):
        stem = zip_path.stem.lower()
        if stem == "cnaes":
            self.CNAEs = Cnaes(zip_path, self)
        elif stem == "municipios":
            self.municipios = Municipios(zip_path, self)
        elif stem == "motivos":
            self.motivos = Motivos(zip_path, self)
        elif stem == "naturezas":
            self.naturezas = Naturezas(zip_path, self)
        elif stem == "paises":
            self.paises = Paises(zip_path, self)
        elif stem == "qualificacoes":
            self.qualificacoes = Qualificacoes(zip_path, self)
        elif stem == "simples":
            self.simples = Simples(zip_path, self)
        elif stem.startswith("empresas"):
            self.empresas = Empresas(zip_path, self)
        elif stem.startswith("estabelecimentos"):
            self.estabelecimentos = Estabelecimentos(zip_path, self)
        elif stem.startswith("socios"):
            self.socios = Socios(zip_path, self)
        else:
            raise Exception()
