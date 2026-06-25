import csv
import io
from pathlib import Path
import zipfile
from typing import Iterable, List

COMMON_CODE_DESCRIPTION_QUERY_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {nome_tabela} (
    id INTEGER  PRIMARY KEY ASC AUTOINCREMENT,
    codigo TEXT (7) NOT NULL,
    descricao TEXT
);"""

COMMON_CODE_DESCRIPTION_QUERY_INSERT = """
INSERT INTO {nome_tabela} (codigo, descricao) VALUES (?, ?);
"""


class BaseRawFile:
    def __init__(self, zip_path: Path, line_length: int, etl_context):
        counter = 0
        
        for row in BaseRawFile.zip_iter_rows(zip_path):
            if len(row) != line_length:
                raise Exception()
            self.apply_row_rule(row, etl_context)
            counter += 1
            
            if counter % 100_000 == 0:
                etl_context.local_cache.commit()

        etl_context.local_cache.commit()


    def apply_row_rule(self, row, etl_context):
        raise NotImplementedError()

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


class BaseCommonCodeDescription(BaseRawFile):
    def __init__(self, zip_path, context, table_name: str):
        context.local_cache.execute_query(
            COMMON_CODE_DESCRIPTION_QUERY_CREATE_TABLE.format(nome_tabela=table_name)
        )

        self.table_name = table_name

        super().__init__(zip_path=zip_path, line_length=2, etl_context=context)


    def apply_row_rule(self, row, etl_context):
        etl_context.local_cache.execute_query(
            COMMON_CODE_DESCRIPTION_QUERY_INSERT.format(nome_tabela=self.table_name),
            (row[0], row[1]),
        )


class Municipios(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="municipios")


class Cnaes(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="cnaes")


class Motivos(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="motivos")


class Naturezas(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="naturezas")


class Paises(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="paises")


class Qualificacoes(BaseCommonCodeDescription):
    def __init__(self, zip_path, context):
        super().__init__(zip_path=zip_path, context=context, table_name="qualificacoes")


class Simples(BaseRawFile):
    def __init__(self, zip_path, context):
        context.local_cache.execute_query("""
            CREATE TABLE IF NOT EXISTS simples (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                cnpj_basico TEXT (8) UNIQUE,
                opcao_simples BOOLEAN,
                data_opcao_simples TEXT (8),
                data_exclusao_simples TEXT (8),
                opcao_mei BOOLEAN,
                data_opcao_mei TEXT (8),
                data_exclusao_mei TEXT (8) 
            );
            """)

        super().__init__(zip_path=zip_path, line_length=7, etl_context=context)


    def apply_row_rule(self, row, etl_context):
        etl_context.local_cache.execute_query(
            """
            INSERT INTO simples (
                cnpj_basico, opcao_simples, data_opcao_simples, data_exclusao_simples, opcao_mei, data_opcao_mei, data_exclusao_mei
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (row[0],row[1],row[2],row[3],row[4],row[5],row[6],),
        )


class Empresas(BaseRawFile):
    def __init__(self, zip_path, context):
        context.local_cache.execute_query("""
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                cnpj_basico TEXT (8),
                razao_social TEXT,
                id_natureza_juridica INTEGER REFERENCES naturezas (id),
                id_qualificacao_responsavel INTEGER REFERENCES qualificacoes (id),
                capital_social TEXT,
                id_porte_empresa INTEGER REFERENCES porte_empresa (id),
                ente_federativo_responsavel TEXT
            );
            """)

        super().__init__(zip_path=zip_path, line_length=7, etl_context=context)

    def apply_row_rule(self, row, etl_context):
        etl_context.local_cache.execute_query(
            """
            INSERT INTO empresas (
                cnpj_basico, 
                razao_social, 
                id_natureza_juridica, 
                id_qualificacao_responsavel, 
                capital_social, 
                id_porte_empresa, 
                ente_federativo_responsavel
            )
            VALUES (
                ?, 
                ?, 
                (SELECT id FROM naturezas WHERE codigo = ?),      
                (SELECT id FROM qualificacoes WHERE codigo = ?),  
                ?,
                (SELECT id FROM porte_empresa WHERE codigo = ?),  
                ?
            );
            """,
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6]),
        )


class Estabelecimentos(BaseRawFile):
    def __init__(self, zip_path, context):
        # -- REVISAR
        context.local_cache.execute_query("""
            CREATE TABLE IF NOT EXISTS estabelecimentos (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                cnpj_basico TEXT (8),
                cnpj_ordem TEXT (4),
                cnpj_dv TEXT (2),
                id_matriz_filial INTEGER REFERENCES matriz_filial (id),
                nome_fantasia TEXT,
                id_situacao_cadastral INTEGER REFERENCES situacao_cadastral (id),
                data_situacao_cadastral TEXT (8),
                id_motivo_situacao_cadastral INTEGER REFERENCES motivos (id),
                nome_cidade_exterior TEXT,
                id_pais INTEGER REFERENCES paises (id),
                data_inicio_atividade TEXT (8),
                id_cnae_fiscal_principal INTEGER REFERENCES cnaes (id),
                tipo_logradouro TEXT,
                logradouro TEXT,
                numero TEXT,
                complemento TEXT,
                bairro TEXT,
                cep TEXT,
                uf TEXT,
                id_municipio INTEGER REFERENCES municipios (id),
                ddd_1 TEXT,
                telefone_1 TEXT,
                ddd_2 TEXT,
                telefone_2 TEXT,
                ddd_fax TEXT,
                fax TEXT,
                correio_eletronico TEXT,
                situacao_especial TEXT,
                data_situacao_especial TEXT (8)
            );
            """)
        
            # CRIAR TABELA RELACIONAL PARA CNAE SECUNDARIOS
        
        super().__init__(zip_path=zip_path, line_length=30, etl_context=context)
        
    
    def apply_row_rule(self, row, etl_context):
        etl_context.local_cache.execute_query(
            """
            INSERT INTO estabelecimentos (
                cnpj_basico, 
                cnpj_ordem, 
                cnpj_dv, 
                id_matriz_filial, 
                nome_fantasia, 
                id_situacao_cadastral, 
                data_situacao_cadastral, 
                id_motivo_situacao_cadastral, 
                nome_cidade_exterior, 
                id_pais, 
                data_inicio_atividade, 
                id_cnae_fiscal_principal, 
                tipo_logradouro, 
                logradouro, 
                numero, 
                complemento, 
                bairro, 
                cep, 
                uf, 
                id_municipio, 
                ddd_1, 
                telefone_1, 
                ddd_2, 
                telefone_2, 
                ddd_fax, 
                fax, 
                correio_eletronico, 
                situacao_especial, 
                data_situacao_especial
            )
            VALUES (
                ?, 
                ?, 
                ?, 
                (SELECT id FROM matriz_filial WHERE codigo = ?), 
                ?, 
                (SELECT id FROM situacao_cadastral WHERE codigo = ?), 
                ?, 
                (SELECT id FROM motivos WHERE codigo = ?), 
                ?, 
                (SELECT id FROM paises WHERE codigo = ?), 
                ?, 
                (SELECT id FROM cnaes WHERE codigo = ?), 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                (SELECT id FROM municipios WHERE codigo = ?), 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?, 
                ?
            );
            """, (
                row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],row[9],row[10],row[11],row[13],row[14],row[15],row[16],row[17],row[18],row[19],row[20],row[21],row[22],row[23],row[24],row[25],row[26],row[27],row[28],row[29],
            ),
        )



class Socios(BaseRawFile):
    def __init__(self, zip_path, context):
        context.local_cache.execute_query("""
            CREATE TABLE IF NOT EXISTS socios (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                cnpj_basico TEXT (8),
                id_socio INTEGER REFERENCES socio (id),
                nome_socio TEXT,
                cpf_cnpj_socio TEXT,
                qualificacao_socio INTEGER REFERENCES qualificacoes (id),
                data_entrada_sociedade TEXT (8),
                id_pais INTEGER REFERENCES paises (id),
                cpf_representante_legal TEXT (14),
                nome_representante_legal TEXT,
                qualificacao_representante_legal INTEGER REFERENCES qualificacoes (id),
                id_faixa_etaria INTEGER REFERENCES faixa_etaria (id)
            )
        """)
        
        super().__init__(zip_path=zip_path, line_length=11, etl_context=context)
        
    
    def apply_row_rule(self, row, etl_context):
        etl_context.local_cache.execute_query(
            """
            INSERT INTO socios (
                cnpj_basico,
                id_socio,
                nome_socio,
                cpf_cnpj_socio,
                qualificacao_socio,
                data_entrada_sociedade,
                id_pais,
                cpf_representante_legal,
                nome_representante_legal,
                qualificacao_representante_legal,
                id_faixa_etaria
            )
            VALUES (
                ?,
                (SELECT id FROM socio WHERE codigo = ?),
                ?,
                ?,
                (SELECT id FROM qualificacoes WHERE codigo = ?),
                ?,
                (SELECT id FROM paises WHERE codigo = ?),
                ?,
                ?,
                (SELECT id FROM qualificacoes WHERE codigo = ?),
                (SELECT id FROM faixa_etaria WHERE codigo = ?)
            );
            """, (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10],
            ),
        )
        