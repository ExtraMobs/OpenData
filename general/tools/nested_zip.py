"""
Módulo `nested_zip`
===================

Este módulo fornece uma interface transparente e de alto desempenho para leitura
de arquivos ZIP aninhados (ZIPs dentro de ZIPs) sem a necessidade de extração
prévia no disco.

Estratégias de Leitura Automáticas:
1. STORED (Sem compressão): Usa `FileSlice` para mapear os bytes diretamente do
   disco com abstração zero-copy. Consome praticamente 0 RAM e suporta `seek()` livre.
2. DEFLATED (Compressão padrão): Usa `IndexedCompressedSlice` que indexa checkpoints
   da descompressão na RAM (a cada 16MB) para simular `seek()` sem carregar tudo.
3. Outros (Fallback): Carrega em `io.BytesIO` na memória (buffer completo).

Classes Principais:
- `NestedZipReader`: A API principal que você deve usar. Recebe um Path e navega pelos zips aninhados.
- `FileSlice`: Cria uma visão virtual (read-only) de um pedaço do arquivo original.
- `ZipLayer`: Encapsula a lógica de gerenciar uma sub-camada ZIP.
"""

from __future__ import annotations

import bisect
import io
import struct
import zipfile
import zlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Union

PathLike = Union[str, Path]

_CHECKPOINT_INTERVAL = 16 * 1024 * 1024


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


class IndexedDecompressor(ABC):
    """Interface para algoritmos de descompressão com suporte a checkpoints.

    Para adicionar um novo algoritmo (BZIP2, LZMA, etc.), basta criar uma
    subclasse e registrar em ``_DECOMPRESSORS``.
    """

    @abstractmethod
    def create(self) -> Any:
        """Cria uma instância nova do descompressor."""

    @abstractmethod
    def decompress(self, state: Any, data: bytes) -> bytes:
        """Alimenta dados comprimidos e retorna output descomprimido."""

    @abstractmethod
    def flush(self, state: Any) -> bytes:
        """Finaliza a descompressão e retorna bytes restantes."""

    @abstractmethod
    def save_checkpoint(self, state: Any) -> Any:
        """Salva o estado atual do descompressor para restauração futura."""

    @abstractmethod
    def restore_checkpoint(self, checkpoint: Any) -> Any:
        """Restaura um descompressor a partir de um checkpoint salvo.

        Deve retornar uma **cópia independente** — o checkpoint original
        não pode ser mutado.
        """


class DeflateDecompressor(IndexedDecompressor):
    """DEFLATE (RFC 1951) com checkpoints via ``zlib.Decompress.copy()``.

    Cada checkpoint custa ~42 KB (32 KB sliding window + 8 KB Huffman
    tables + overhead).
    """

    def __init__(self, wbits: int = -15) -> None:
        self._wbits = wbits

    def create(self) -> zlib._Decompress:
        return zlib.decompressobj(self._wbits)

    def decompress(self, state: zlib._Decompress, data: bytes) -> bytes:
        return state.decompress(data)

    def flush(self, state: zlib._Decompress) -> bytes:
        try:
            return state.flush()
        except zlib.error:
            return b""

    def save_checkpoint(self, state: zlib._Decompress) -> zlib._Decompress:
        return state.copy()

    def restore_checkpoint(self, checkpoint: zlib._Decompress) -> zlib._Decompress:
        return checkpoint.copy()


_DECOMPRESSORS: dict[int, IndexedDecompressor] = {
    zipfile.ZIP_DEFLATED: DeflateDecompressor(),
}


class IndexedCompressedSlice:
    """View seekable sobre dados comprimidos com checkpoints indexados.

    Na primeira leitura, constrói um índice descomprimindo o stream inteiro
    uma vez (salvando checkpoints a cada ``checkpoint_interval`` bytes de
    output).  Seeks posteriores localizam o checkpoint mais próximo e
    descomprimem apenas o trecho restante.

    Parâmetros
    ----------
    source:
        File-like de onde ler os dados comprimidos.
    offset:
        Posição em ``source`` onde os dados comprimidos começam.
    compressed_size:
        Tamanho total dos dados comprimidos (bytes).
    uncompressed_size:
        Tamanho total dos dados descomprimidos (bytes).
    decompressor:
        Instância de ``IndexedDecompressor`` para o algoritmo usado.
    checkpoint_interval:
        Intervalo entre checkpoints em bytes de output descomprimido.
    """

    _READ_CHUNK = 65536

    def __init__(
        self,
        source: BinaryIO,
        offset: int,
        compressed_size: int,
        uncompressed_size: int,
        decompressor: IndexedDecompressor,
        checkpoint_interval: int = _CHECKPOINT_INTERVAL,
    ) -> None:
        self._source = source
        self._offset = offset
        self._comp_size = compressed_size
        self._decomp_size = uncompressed_size
        self._algo = decompressor
        self._interval = checkpoint_interval

        self._pos = 0
        self._indexed = False

        self._checkpoints: list[tuple[int, int, Any]] = []
        self._checkpoint_offsets: list[int] = []

        self._cache_state: Any = None
        self._cache_decomp_pos: int = -1
        self._cache_comp_pos: int = -1
        self._cache_overflow: bytes = b""
        self._cache_flushed: bool = False

    def _build_index(self) -> None:
        """Primeira passada: descomprime o stream inteiro salvando checkpoints."""
        if self._comp_size == 0:
            self._checkpoints = [
                (0, 0, self._algo.save_checkpoint(self._algo.create()))
            ]
            self._checkpoint_offsets = [0]
            self._indexed = True
            return

        d = self._algo.create()
        comp_fed = 0
        decomp_produced = 0

        self._checkpoints = [(0, 0, self._algo.save_checkpoint(d))]
        next_cp = self._interval

        while comp_fed < self._comp_size:
            to_read = min(self._READ_CHUNK, self._comp_size - comp_fed)
            self._source.seek(self._offset + comp_fed)
            chunk = self._source.read(to_read)
            if not chunk:
                break

            output = self._algo.decompress(d, chunk)
            comp_fed += len(chunk)
            decomp_produced += len(output)

            if decomp_produced >= next_cp:
                self._checkpoints.append(
                    (decomp_produced, comp_fed, self._algo.save_checkpoint(d))
                )
                next_cp = decomp_produced + self._interval

        remaining = self._algo.flush(d)
        if remaining:
            decomp_produced += len(remaining)

        if decomp_produced != self._decomp_size:
            self._decomp_size = decomp_produced

        self._checkpoint_offsets = [cp[0] for cp in self._checkpoints]
        self._indexed = True

    def _find_checkpoint(self, pos: int) -> int:
        """Retorna o índice do checkpoint mais recente em ou antes de ``pos``."""
        idx = bisect.bisect_right(self._checkpoint_offsets, pos) - 1
        return max(0, idx)

    def _setup_at(self, pos: int) -> None:
        """Configura o descompressor para produzir bytes a partir de ``pos``."""
        idx = self._find_checkpoint(pos)
        cp_decomp, cp_comp, cp_state = self._checkpoints[idx]

        if (
            self._cache_state is not None
            and self._cache_decomp_pos <= pos
            and self._cache_decomp_pos >= cp_decomp
        ):
            skip = pos - self._cache_decomp_pos
        else:
            self._cache_state = self._algo.restore_checkpoint(cp_state)
            self._cache_decomp_pos = cp_decomp
            self._cache_comp_pos = cp_comp
            self._cache_overflow = b""
            self._cache_flushed = False
            skip = pos - cp_decomp

        if skip > 0:
            self._skip(skip)

    def _read_comp_chunk(self) -> bytes:
        """Lê o próximo chunk de dados comprimidos da source."""
        to_read = min(self._READ_CHUNK, self._comp_size - self._cache_comp_pos)
        if to_read <= 0:
            return b""
        self._source.seek(self._offset + self._cache_comp_pos)
        return self._source.read(to_read)

    def _skip(self, count: int) -> None:
        """Descomprime e descarta ``count`` bytes."""
        skipped = 0
        while skipped < count:
            if self._cache_overflow:
                take = min(len(self._cache_overflow), count - skipped)
                self._cache_overflow = self._cache_overflow[take:]
                self._cache_decomp_pos += take
                skipped += take
                continue

            chunk = self._read_comp_chunk()
            if not chunk:
                if not self._cache_flushed:
                    remaining = self._algo.flush(self._cache_state)
                    self._cache_flushed = True
                    if remaining:
                        take = min(len(remaining), count - skipped)
                        if take < len(remaining):
                            self._cache_overflow = remaining[take:]
                        self._cache_decomp_pos += take
                        skipped += take
                break

            output = self._algo.decompress(self._cache_state, chunk)
            self._cache_comp_pos += len(chunk)

            take = min(len(output), count - skipped)
            if take < len(output):
                self._cache_overflow = output[take:]
            self._cache_decomp_pos += take
            skipped += take

    def _decompress_forward(self, size: int) -> bytes:
        """Descomprime ``size`` bytes para frente a partir da posição do cache."""
        result = bytearray()

        if self._cache_overflow:
            take = min(len(self._cache_overflow), size)
            result.extend(self._cache_overflow[:take])
            self._cache_overflow = self._cache_overflow[take:]
            self._cache_decomp_pos += take

        while len(result) < size:
            chunk = self._read_comp_chunk()
            if not chunk:
                if not self._cache_flushed:
                    remaining = self._algo.flush(self._cache_state)
                    self._cache_flushed = True
                    if remaining:
                        take = min(len(remaining), size - len(result))
                        result.extend(remaining[:take])
                        if take < len(remaining):
                            self._cache_overflow = remaining[take:]
                        self._cache_decomp_pos += take
                break

            output = self._algo.decompress(self._cache_state, chunk)
            self._cache_comp_pos += len(chunk)

            take = min(len(output), size - len(result))
            result.extend(output[:take])
            if take < len(output):
                self._cache_overflow = output[take:]
            self._cache_decomp_pos += take

        return bytes(result)

    def read(self, size: int = -1) -> bytes:
        """Lê os próximos bytes descomprimidos. Descomprime sob demanda a partir do último checkpoint."""
        if not self._indexed:
            self._build_index()

        if self._pos >= self._decomp_size:
            return b""
        if size < 0:
            size = self._decomp_size - self._pos
        size = min(size, self._decomp_size - self._pos)
        if size == 0:
            return b""

        if self._cache_decomp_pos != self._pos:
            self._setup_at(self._pos)

        result = self._decompress_forward(size)
        self._pos += len(result)
        return result

    def readinto(self, b: bytearray) -> int:
        """Lê bytes pré-alocados para o buffer `b`."""
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        """Simula seek alterando o ponteiro virtual de bytes descomprimidos."""
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._decomp_size + offset
        self._pos = max(0, min(self._pos, self._decomp_size))
        return self._pos

    def tell(self) -> int:
        """Posição virtual atual (bytes descomprimidos) em relação ao início."""
        return self._pos

    def seekable(self) -> bool:
        """Indica suporte a navegação por checkpoints."""
        return True

    def readable(self) -> bool:
        """Indica que o arquivo é legível."""
        return True

    def writable(self) -> bool:
        """Indica que o Stream não é gravável."""
        return False

    def close(self) -> None:
        self._checkpoints.clear()
        self._checkpoint_offsets.clear()
        self._cache_state = None
        self._cache_overflow = b""

    def __enter__(self) -> IndexedCompressedSlice:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        n = len(self._checkpoints)
        return (
            f"<IndexedCompressedSlice "
            f"decomp_size={self._decomp_size} "
            f"checkpoints={n} "
            f"interval={self._interval // (1024*1024)}MB>"
        )


class ZipLayer:
    """Wrapper que mantém um ``zipfile.ZipFile`` aberto sobre uma fonte.

    Modos possíveis:

    - ``disk``      — camada raiz, lê do arquivo em disco.
    - ``zero-copy`` — ``FileSlice``, entrada ``STORED``.
    - ``indexed``   — ``IndexedCompressedSlice``, entrada ``DEFLATED``.
    - ``buffered``  — ``BytesIO``, fallback para compressões sem suporte.
    """

    def __init__(
        self,
        zf: zipfile.ZipFile,
        source: BinaryIO,
        *,
        parent: ZipLayer | None = None,
        mode: str = "zero-copy",
        checkpoint_interval: int = _CHECKPOINT_INTERVAL,
    ) -> None:
        self._zf = zf
        self._source = source
        self._parent = parent
        self.mode = mode
        self._checkpoint_interval = checkpoint_interval

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

        Seleciona automaticamente a melhor estratégia:
        - ``STORED``  → ``FileSlice`` (zero-copy)
        - ``DEFLATED`` → ``IndexedCompressedSlice`` (checkpoints)
        - Outros      → ``BytesIO`` (fallback)
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
                checkpoint_interval=self._checkpoint_interval,
            )

        if info.compress_type in _DECOMPRESSORS:
            data_offset = self._compute_data_offset(info)
            algo = _DECOMPRESSORS[info.compress_type]
            ics = IndexedCompressedSlice(
                source=self._source,
                offset=data_offset,
                compressed_size=info.compress_size,
                uncompressed_size=info.file_size,
                decompressor=algo,
                checkpoint_interval=self._checkpoint_interval,
            )
            child_zf = zipfile.ZipFile(ics)
            return ZipLayer(
                child_zf,
                source=ics,
                parent=self,
                mode="indexed",
                checkpoint_interval=self._checkpoint_interval,
            )

        raw = self._zf.read(inner_name)
        buf = io.BytesIO(raw)
        child_zf = zipfile.ZipFile(buf)
        return ZipLayer(
            child_zf,
            source=buf,
            parent=self,
            mode="buffered",
            checkpoint_interval=self._checkpoint_interval,
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
    checkpoint_interval:
        Intervalo entre checkpoints para camadas ``DEFLATED`` (em bytes
        de output descomprimido).  Padrão: 16 MB.
    """

    def __init__(
        self,
        path: PathLike,
        *,
        encoding: str = "utf-8",
        checkpoint_interval: int = _CHECKPOINT_INTERVAL,
    ) -> None:
        self._encoding = encoding
        self._checkpoint_interval = checkpoint_interval
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
            checkpoint_interval=self._checkpoint_interval,
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
        return f"<NestedZipReader depth={self.depth} " f"modes={modes} leaf={leaf!r}>"
