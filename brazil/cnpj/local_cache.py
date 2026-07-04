from pathlib import Path

from general.sqlite import SQLiteBase


class LocalCache(SQLiteBase):
    def __init__(self, db_path: str):
        path = Path(db_path).absolute().joinpath("cnpj.db")
        if path.exists():
            path.unlink()
        super().__init__(path)

        self._conn.execute("PRAGMA synchronous = OFF;")
        self._conn.execute("PRAGMA journal_mode = OFF;")
        self._conn.execute("PRAGMA temp_store = MEMORY;")
        self._conn.execute("PRAGMA cache_size = -500000;")

        self.execute_query("""
            CREATE TABLE IF NOT EXISTS porte_empresa (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                codigo TEXT (2) NOT NULL UNIQUE,
                descricao TEXT
            );
            """)

        self.execute_query("""
            INSERT OR IGNORE INTO porte_empresa (codigo, descricao) VALUES
                ('00', 'NÃO INFORMADO'),
                ('01', 'MICRO EMPRESA'),
                ('03', 'EMPRESA DE PEQUENO PORTE'),
                ('05', 'DEMAIS');
            """)

        self.execute_query("""
            CREATE TABLE IF NOT EXISTS situacao_cadastral (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                codigo TEXT (2) NOT NULL UNIQUE,
                descricao TEXT
            );
            """)

        self.execute_query("""
            INSERT OR IGNORE INTO situacao_cadastral (codigo, descricao) VALUES
                ('01', 'NULA'),
                ('2', 'ATIVA'),
                ('3', 'SUSPENSA'),
                ('4', 'INAPTA'),
                ('08', 'BAIXADA');
            """)

        self.execute_query("""
            CREATE TABLE IF NOT EXISTS socio (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                codigo TEXT (1) NOT NULL UNIQUE,
                descricao TEXT
            );
            """)

        self.execute_query("""
            INSERT OR IGNORE INTO socio (codigo, descricao) VALUES
                ('2', 'PESSOA FÍSICA'),
                ('3', 'ESTRANGEIRO');
            """)

        self.execute_query("""
            CREATE TABLE IF NOT EXISTS matriz_filial (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                codigo TEXT (1) NOT NULL UNIQUE,
                descricao TEXT
            );
            """)

        self.execute_query("""
            INSERT OR IGNORE INTO matriz_filial (codigo, descricao) VALUES
                ('1', 'MATRIZ'),
                ('2', 'FILIAL');
            """)

        self.execute_query("""
            CREATE TABLE IF NOT EXISTS faixa_etaria (
                id INTEGER PRIMARY KEY ASC AUTOINCREMENT,
                codigo TEXT (1) NOT NULL UNIQUE,
                descricao TEXT
            );
            """)

        self.execute_query("""
            INSERT OR IGNORE INTO faixa_etaria (codigo, descricao) VALUES
                ('1', 'para os intervalos entre 0 a 12 anos'),
                ('2', 'para os intervalos entre 13 a 20 anos'),
                ('3', 'para os intervalos entre 21 a 30 anos'),
                ('4', 'para os intervalos entre 31 a 40 anos'),
                ('5', 'para os intervalos entre 41 a 50 anos'),
                ('6', 'para os intervalos entre 51 a 60 anos'),
                ('7', 'para os intervalos entre 61 a 70 anos'),
                ('8', 'para os intervalos entre 71 a 80 anos'),
                ('9', 'para maiores de 80 anos'),
                ('0', 'para não se aplica');

            """)

        self.commit()
