# Gerado por IA para facilitar a leitura de zips STORED sem usar
# espaço em disco desnecessário, como é o caso dos snapshot de CNPJ.

# Precisa de revisão,validação e otimização humana.
"""
Módulo `nested_zip`
===================

Este módulo fornece uma interface transparente e de alto desempenho para leitura
de arquivos ZIP aninhados (ZIPs dentro de ZIPs) sem a necessidade de extração
prévia no disco.

Estratégias de Leitura Automáticas:
1. STORED (Sem compressão): Usa `FileSlice` para mapear os bytes diretamente do
   disco com abstração zero-copy. Consome praticamente 0 RAM e suporta `seek()` livre.
2. Outros: Levanta uma exceção indicando que não é possível iterar sobre o zip.

Classes Principais:
- `NestedZipReader`: A API principal que você deve usar. Recebe um Path e navega pelos zips aninhados.
- `FileSlice`: Cria uma visão virtual (read-only) de um pedaço do arquivo original.
- `ZipLayer`: Encapsula a lógica de gerenciar uma sub-camada ZIP.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from typing import BinaryIO, Iterator, Union

PathLike = Union[str, Path]


class FileSlice:
    """Janela seekable read-only sobre um intervalo de bytes de outro arquivo.

    Custo de memória: ~64 bytes (4 slots) por camada, independente do
    tamanho do zip interno.  Pode ser encadeado (slice de slice).
    """

    __slots__ = ("_source", "_offset", "_length", "_pos")

    def __init__(self, source: BinaryIO, offset: int, length: int) -> None:
        self._source = source
        self._offset = offset
        self._length = length
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        """Lê e retorna até `size` bytes. Se `size` for negativo, lê até o fim do slice."""
        if self._pos >= self._length:
            return b""
        if size < 0:
            size = self._length - self._pos
        size = min(size, self._length - self._pos)
        self._source.seek(self._offset + self._pos)
        data = self._source.read(size)
        self._pos += len(data)
        return data

    def readinto(self, b: bytearray) -> int:
        """Lê bytes para dentro do buffer `b` pré-alocado, retornando o total lido."""
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        """Move o ponteiro de leitura da janela virtual.

        Suporta os modos convencionais (0=início, 1=relativo, 2=fim).
        """
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._length + offset
        self._pos = max(0, min(self._pos, self._length))
        return self._pos

    def tell(self) -> int:
        """Retorna a posição atual do ponteiro de leitura em relação ao slice."""
        return self._pos

    def seekable(self) -> bool:
        """Indica que o stream suporta navegação (seek)."""
        return True

    def readable(self) -> bool:
        """Indica que o stream suporta leitura."""
        return True

    def writable(self) -> bool:
        """Indica que o stream é somente leitura."""
        return False

    def close(self) -> None:
        pass

    def __enter__(self) -> FileSlice:
        return self

    def __exit__(self, *exc) -> None:
        pass

    def __repr__(self) -> str:
        return (
            f"<FileSlice offset={self._offset} "
            f"length={self._length} pos={self._pos}>"
        )


class ZipLayer:
    """Wrapper que mantém um ``zipfile.ZipFile`` aberto sobre uma fonte.

    Modos possíveis:

    - ``disk``      — camada raiz, lê do arquivo em disco.
    - ``zero-copy`` — ``FileSlice``, entrada ``STORED``.
    """

    def __init__(
        self,
        zf: zipfile.ZipFile,
        source: BinaryIO,
        *,
        parent: ZipLayer | None = None,
        mode: str = "zero-copy",
    ) -> None:
        self._zf = zf
        self._source = source
        self._parent = parent
        self.mode = mode

    def namelist(self) -> list[str]:
        """Retorna os nomes dos arquivos contidos nesta camada ZIP."""
        return self._zf.namelist()

    def infolist(self) -> list[zipfile.ZipInfo]:
        """Retorna a lista de objetos ZipInfo desta camada."""
        return self._zf.infolist()

    def read(self, name: str) -> bytes:
        """Lê os bytes de um arquivo contido nesta camada."""
        return self._zf.read(name)

    def open(self, name: str, mode: str = "r", **kwargs) -> io.BufferedIOBase:
        """Abre um arquivo dentro desta camada como um objeto de IO binário."""
        return self._zf.open(name, mode, **kwargs)

    def _compute_data_offset(self, info: zipfile.ZipInfo) -> int:
        """Calcula o offset onde os dados brutos de uma entrada começam."""
        self._source.seek(info.header_offset + 26)
        header = self._source.read(4)
        fname_len, extra_len = struct.unpack("<HH", header)
        return info.header_offset + 30 + fname_len + extra_len

    def enter(self, inner_name: str) -> ZipLayer:
        """Abre um zip interno e devolve um novo ``ZipLayer`` filho.

        Suporta apenas entradas com compressão STORED.
        """
        info = self._zf.getinfo(inner_name)

        if info.compress_type == zipfile.ZIP_STORED:
            data_offset = self._compute_data_offset(info)
            slc = FileSlice(self._source, data_offset, info.file_size)
            child_zf = zipfile.ZipFile(slc)
            return ZipLayer(
                child_zf,
                source=slc,
                parent=self,
                mode="zero-copy",
            )

        raise NotImplementedError(
            f"Não foi possível iterar sobre o zip '{inner_name}'. "
            f"Apenas compressão STORED é suportada. (Encontrado: {info.compress_type})"
        )

    def close(self) -> None:
        self._zf.close()
        if self._parent is not None:
            self._parent.close()

    def __enter__(self) -> ZipLayer:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<ZipLayer mode={self.mode!r} entries={len(self.namelist())}>"


class NestedZipReader:
    """Leitor de alto nível que resolve um caminho com zips aninhados.

    O *path* pode conter qualquer número de camadas ``.zip``.  Detecta
    automaticamente onde cada camada termina e abre wrappers encadeados.

    Parameters
    ----------
    path:
        Aceita ``str`` ou ``pathlib.Path``.  Exemplo::

            Path(r"D:/data/outer.zip") / "subdir" / "inner.zip" / "file.csv"

    encoding:
        Encoding padrão para ``read_text`` e ``iter_lines``.
    """

    def __init__(
        self,
        path: PathLike,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self._encoding = encoding
        self._layers: list[ZipLayer] = []
        self._leaf_name: str | None = None
        self._file_handle: BinaryIO | None = None
        self._closed = False

        self._resolve(Path(path))

    def _resolve(self, path: Path) -> None:
        parts = path.parts

        fs_path: Path | None = None
        rest_idx = 0

        for i in range(1, len(parts) + 1):
            candidate = Path(*parts[:i])
            if candidate.is_file():
                fs_path = candidate
                rest_idx = i
                break

        if fs_path is None:
            raise FileNotFoundError(f"Nenhum arquivo encontrado no caminho: {path}")

        fh = open(fs_path, "rb")
        self._file_handle = fh
        root_zf = zipfile.ZipFile(fh)
        root_layer = ZipLayer(
            root_zf,
            source=fh,
            mode="disk",
        )
        self._layers.append(root_layer)

        remaining = list(parts[rest_idx:])
        if remaining:
            self._walk_segments(remaining)

    def _walk_segments(self, segments: list[str]) -> None:
        current_layer = self._layers[-1]
        entries = set(current_layer.namelist())
        accumulated: list[str] = []

        i = 0
        while i < len(segments):
            accumulated.append(segments[i])
            candidate = "/".join(accumulated)

            if candidate.lower().endswith(".zip") and candidate in entries:
                new_layer = current_layer.enter(candidate)
                self._layers.append(new_layer)
                current_layer = new_layer
                entries = set(current_layer.namelist())
                accumulated = []
            elif candidate in entries:
                self._leaf_name = candidate
                accumulated = []
                if i + 1 < len(segments):
                    raise ValueError(
                        f"Segmentos restantes após arquivo final "
                        f"'{candidate}': {'/'.join(segments[i + 1:])}"
                    )
            elif (candidate + "/") in entries:
                pass
            i += 1

        if accumulated:
            candidate = "/".join(accumulated)
            if candidate in entries:
                if candidate.lower().endswith(".zip"):
                    new_layer = current_layer.enter(candidate)
                    self._layers.append(new_layer)
                else:
                    self._leaf_name = candidate
            elif (candidate + "/") in entries:
                self._leaf_name = candidate + "/"
            else:
                available = sorted(entries)[:20]
                raise FileNotFoundError(
                    f"Entrada '{candidate}' não encontrada no zip. "
                    f"Entradas disponíveis: {available}..."
                )

    @property
    def is_leaf_file(self) -> bool:
        """``True`` se o caminho resolve para um arquivo final (não zip)."""
        return self._leaf_name is not None and not self._leaf_name.endswith("/")

    @property
    def is_dir(self) -> bool:
        """``True`` se o caminho resolve para um diretório dentro do zip."""
        return self._leaf_name is not None and self._leaf_name.endswith("/")

    @property
    def is_zip(self) -> bool:
        """``True`` se o caminho resolve para uma camada zip (aberta)."""
        return self._leaf_name is None

    @property
    def current_layer(self) -> ZipLayer:
        """Retorna a camada Zip mais interna que está atualmente em foco."""
        return self._layers[-1]

    @property
    def depth(self) -> int:
        """Retorna o nível de profundidade atual de aninhamento dos zips."""
        return len(self._layers)

    @property
    def layers(self) -> list[ZipLayer]:
        """Retorna a lista de todas as camadas abertas, em ordem."""
        return list(self._layers)

    def namelist(self) -> list[str]:
        """Retorna a lista de nomes e arquivos visíveis na camada mais interna."""
        names = self.current_layer.namelist()
        if self._leaf_name and self._leaf_name.endswith("/"):
            prefix = self._leaf_name
            return [n for n in names if n.startswith(prefix) and n != prefix]
        return names

    def read_bytes(self, entry: str | None = None) -> bytes:
        """Retorna o conteúdo binário de um arquivo resolvido ou passado por `entry`."""
        if entry is not None:
            return self.current_layer.read(entry)
        if self.is_leaf_file:
            return self.current_layer.read(self._leaf_name)
        raise ValueError(
            "O caminho aponta para um zip ou diretório. "
            "Use namelist() ou passe 'entry'."
        )

    def read_text(self, entry: str | None = None, encoding: str | None = None) -> str:
        """Retorna o conteúdo em texto plano, decodificando os bytes do alvo."""
        return self.read_bytes(entry).decode(encoding or self._encoding)

    def readlines(
        self, entry: str | None = None, encoding: str | None = None
    ) -> list[str]:
        """Lê todo o conteúdo e retorna uma lista de strings divididas pelas quebras de linha."""
        return self.read_text(entry, encoding).splitlines()

    def iter_lines(
        self, entry: str | None = None, encoding: str | None = None
    ) -> Iterator[str]:
        """Retorna um iterador preguiçoso que realiza a leitura linha a linha."""
        target = entry if entry is not None else self._leaf_name
        if target is None:
            raise ValueError("Nenhum arquivo final para iterar.")
        enc = encoding or self._encoding
        with self.current_layer.open(target) as f:
            wrapper = io.TextIOWrapper(f, encoding=enc)
            yield from wrapper

    def open_entry(self, entry: str) -> io.BufferedIOBase:
        """Abre o stream para a leitura binária bruta de um arquivo dentro do zip final."""
        return self.current_layer.open(entry)

    def walk(self) -> Iterator[str]:
        """Itera recursivamente por todos os caminhos alcançáveis.

        Entra automaticamente em sub-zips e prefixa o caminho completo.
        Entradas que não são ``.zip`` são yielded como estão.  Entradas
        ``.zip`` são yielded E seus conteúdos internos também.

        Yields
        ------
        str
            Caminho completo relativo ao zip raiz.  Exemplo::

                "2023-05/"
                "2023-05/Cnaes.zip"
                "2023-05/Cnaes.zip/F.K03200$Z.D30513.CNAECSV"
                "2023-05/Empresas0.zip"
                "2023-05/Empresas0.zip/K3241.K03200Y0.D30513.EMPREam"
                ...
        """
        yield from self._walk_layer(self.current_layer, prefix="")

    @staticmethod
    def is_path_dir(path: str) -> bool:
        """Verifica se um caminho retornado por walk() é um diretório."""
        return path.endswith("/")

    @staticmethod
    def is_path_zip(path: str) -> bool:
        """Verifica se um caminho retornado por walk() é um zip."""
        return path.lower().endswith(".zip") and not path.endswith("/")

    @staticmethod
    def is_path_leaf(path: str) -> bool:
        """Verifica se um caminho retornado por walk() é um arquivo final."""
        return not path.endswith("/") and not path.lower().endswith(".zip")

    @staticmethod
    def _walk_layer(layer: ZipLayer, prefix: str) -> Iterator[str]:
        for entry in layer.namelist():
            full = prefix + entry
            yield full

            if entry.lower().endswith(".zip") and not entry.endswith("/"):
                try:
                    child = layer.enter(entry)
                    try:
                        yield from NestedZipReader._walk_layer(child, full + "/")
                    finally:
                        child._zf.close()
                        child._source.close()
                except Exception:
                    pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for layer in reversed(self._layers):
            try:
                layer._zf.close()
            except Exception:
                pass
            try:
                layer._source.close()
            except Exception:
                pass
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except Exception:
                pass

    def __enter__(self) -> NestedZipReader:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        modes = [layer.mode for layer in self._layers]
        leaf = self._leaf_name or "(zip layer)"
        return f"<NestedZipReader depth={self.depth} modes={modes} leaf={leaf!r}>"
