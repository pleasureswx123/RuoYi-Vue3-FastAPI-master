import asyncio
import hashlib
import inspect
import io
import re
import zipfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, TypeVar
from xml.parsers import expat

from module_shot_grid.config import SHOT_GRID_IMPORT_CONFIG, ShotGridImportConfig
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error

T = TypeVar('T')

_SPREADSHEET_NAMESPACES = {
    'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'http://purl.oclc.org/ooxml/spreadsheetml/main',
}
_CELL_REFERENCE_PATTERN = re.compile(r'^\$?([A-Z]{1,3})\$?([1-9]\d*)$')
_XML_READ_CHUNK_SIZE = 64 * 1024
_MAX_SHARED_STRING_INDEX_LENGTH = 20


@dataclass
class _OoxmlCounters:
    xml_elements: int = 0
    rows: int = 0
    cells: int = 0
    merge_ranges: int = 0
    merged_cells: int = 0
    text_characters: int = 0


@dataclass
class _XmlPartState:
    root_kind: str | None = None
    depth: int = 0
    last_row: int = 0
    current_row: int | None = None
    current_cell_type: str | None = None
    current_cell_characters: int = 0
    current_text_element: str | None = None
    shared_value_seen: bool = False
    shared_value_parts: list[str] = field(default_factory=list)
    in_shared_item: bool = False
    shared_item_characters: int = 0


class _OoxmlPreflight:
    """以恒定 XML 树内存扫描 OOXML，阻断 openpyxl 前的资源放大。"""

    def __init__(self, config: ShotGridImportConfig) -> None:
        self.config = config
        self.counters = _OoxmlCounters()
        self.state = _XmlPartState()
        self.shared_string_lengths: list[int] = []
        self.shared_string_references: dict[int, int] = defaultdict(int)

    def inspect(self, archive: zipfile.ZipFile) -> None:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.casefold().endswith('.xml'):
                continue
            self._scan_xml_part(archive, entry)
        self._validate_shared_string_references()

    def _scan_xml_part(self, archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> None:
        self.state = _XmlPartState()
        parser = expat.ParserCreate(namespace_separator='}')
        parser.StartElementHandler = self._start_element
        parser.EndElementHandler = self._end_element
        parser.CharacterDataHandler = self._characters
        parser.StartDoctypeDeclHandler = self._reject_unsafe_xml
        parser.EntityDeclHandler = self._reject_unsafe_xml
        parser.ExternalEntityRefHandler = self._reject_external_entity

        try:
            with archive.open(entry) as source:
                while chunk := source.read(_XML_READ_CHUNK_SIZE):
                    parser.Parse(chunk, False)
                parser.Parse(b'', True)
        except ShotGridDomainException:
            raise
        except (expat.ExpatError, OSError, RuntimeError, ValueError) as exc:
            raise shot_grid_error(422, 'SG_IMPORT_FILE_INVALID', '工作簿包含无效的 OOXML 内容') from exc

    def _start_element(self, name: str, attributes: dict[str, str]) -> None:
        self.counters.xml_elements += 1
        if self.counters.xml_elements > self.config.max_ooxml_xml_elements:
            self._raise_complexity_limit('工作簿 XML 元素数量超过安全限制')

        namespace, local_name = self._split_name(name)
        if self.state.depth == 0 and namespace in _SPREADSHEET_NAMESPACES and local_name in {'worksheet', 'sst'}:
            self.state.root_kind = local_name
        self.state.depth += 1

        if self.state.root_kind == 'sst':
            if namespace not in _SPREADSHEET_NAMESPACES:
                return
            if local_name == 'si':
                self.state.in_shared_item = True
                self.state.shared_item_characters = 0
            elif local_name == 't' and self.state.in_shared_item:
                self.state.current_text_element = local_name
            return

        if self.state.root_kind != 'worksheet' or namespace not in _SPREADSHEET_NAMESPACES:
            return
        if local_name == 'row':
            self._start_row(attributes)
        elif local_name == 'c':
            self._start_cell(attributes)
        elif local_name == 'dimension':
            self._validate_range_reference(attributes.get('ref'), merge=False)
        elif local_name == 'mergeCell':
            self._validate_range_reference(attributes.get('ref'), merge=True)
        elif local_name in {'v', 'f', 't'} and self.state.current_cell_type is not None:
            self.state.current_text_element = local_name

    def _end_element(self, name: str) -> None:
        namespace, local_name = self._split_name(name)
        if self.state.root_kind == 'sst' and namespace in _SPREADSHEET_NAMESPACES:
            if local_name == 't':
                self.state.current_text_element = None
            elif local_name == 'si' and self.state.in_shared_item:
                self.shared_string_lengths.append(self.state.shared_item_characters)
                if len(self.shared_string_lengths) > self.config.max_ooxml_cells_per_workbook:
                    self._raise_complexity_limit('工作簿共享字符串数量超过安全限制')
                self.state.in_shared_item = False
        elif self.state.root_kind == 'worksheet' and namespace in _SPREADSHEET_NAMESPACES:
            if local_name in {'v', 'f', 't'}:
                self.state.current_text_element = None
            elif local_name == 'c':
                self._end_cell()
            elif local_name == 'row':
                self.state.current_row = None
        self.state.depth -= 1

    def _characters(self, value: str) -> None:
        if not value or self.state.current_text_element is None:
            return
        if self.state.root_kind == 'sst' and self.state.in_shared_item:
            self.state.shared_item_characters += len(value)
            self._check_cell_text_length(self.state.shared_item_characters)
            self._add_text_characters(len(value))
            return
        if self.state.root_kind != 'worksheet' or self.state.current_cell_type is None:
            return
        if self.state.current_cell_type == 's' and self.state.current_text_element == 'v':
            self.state.shared_value_seen = True
            if sum(map(len, self.state.shared_value_parts)) + len(value) > _MAX_SHARED_STRING_INDEX_LENGTH:
                self._raise_invalid('共享字符串索引无效')
            self.state.shared_value_parts.append(value)
            return
        self.state.current_cell_characters += len(value)
        self._check_cell_text_length(self.state.current_cell_characters)
        self._add_text_characters(len(value))

    def _start_row(self, attributes: dict[str, str]) -> None:
        self.counters.rows += 1
        if self.counters.rows > self.config.max_ooxml_rows_per_workbook:
            self._raise_row_limit('工作簿物理行数超过安全限制')
        raw_row = attributes.get('r')
        if raw_row is None:
            row_number = self.state.last_row + 1
        elif not raw_row.isdecimal():
            self._raise_invalid('工作表行号无效')
        else:
            row_number = int(raw_row)
        if row_number <= self.state.last_row or row_number > self.config.max_rows_per_workbook + 1:
            self._raise_row_limit('工作表行号超过安全限制或顺序无效')
        self.state.last_row = row_number
        self.state.current_row = row_number

    def _start_cell(self, attributes: dict[str, str]) -> None:
        if self.state.current_row is None:
            self._raise_invalid('工作表单元格未包含在有效行中')
        _, row_number = self._parse_cell_reference(attributes.get('r'))
        if row_number != self.state.current_row:
            self._raise_invalid('工作表单元格坐标与所在行不一致')
        self.counters.cells += 1
        if self.counters.cells > self.config.max_ooxml_cells_per_workbook:
            self._raise_complexity_limit('工作簿物理单元格数量超过安全限制')
        self.state.current_cell_type = attributes.get('t', 'n')
        self.state.current_cell_characters = 0
        self.state.shared_value_seen = False
        self.state.shared_value_parts.clear()

    def _end_cell(self) -> None:
        if self.state.current_cell_type == 's' and self.state.shared_value_seen:
            raw_index = ''.join(self.state.shared_value_parts).strip()
            if not raw_index.isdecimal():
                self._raise_invalid('共享字符串索引无效')
            self.shared_string_references[int(raw_index)] += 1
        self.state.current_cell_type = None
        self.state.current_cell_characters = 0
        self.state.current_text_element = None
        self.state.shared_value_seen = False
        self.state.shared_value_parts.clear()

    def _validate_range_reference(self, value: str | None, *, merge: bool) -> None:
        if not value:
            self._raise_invalid('工作表范围坐标无效')
        parts = value.split(':')
        if len(parts) not in {1, 2}:
            self._raise_invalid('工作表范围坐标无效')
        start_column, start_row = self._parse_cell_reference(parts[0])
        end_column, end_row = self._parse_cell_reference(parts[-1])
        if start_column > end_column or start_row > end_row:
            self._raise_invalid('工作表范围坐标顺序无效')
        if not merge:
            return
        self.counters.merge_ranges += 1
        if self.counters.merge_ranges > self.config.max_ooxml_merge_ranges:
            self._raise_complexity_limit('工作簿合并单元格范围数量超过安全限制')
        self.counters.merged_cells += (end_column - start_column + 1) * (end_row - start_row + 1)
        if self.counters.merged_cells > self.config.max_ooxml_merged_cells:
            self._raise_complexity_limit('工作簿合并单元格展开量超过安全限制')

    def _parse_cell_reference(self, value: str | None) -> tuple[int, int]:
        if not value:
            self._raise_invalid('工作表单元格坐标无效')
        match = _CELL_REFERENCE_PATTERN.fullmatch(value)
        if match is None:
            self._raise_invalid('工作表单元格坐标无效')
        column = 0
        for character in match.group(1):
            column = column * 26 + ord(character) - ord('A') + 1
        row = int(match.group(2))
        if row > self.config.max_rows_per_workbook + 1:
            self._raise_row_limit('工作表行号超过安全限制')
        if column > self.config.max_ooxml_columns_per_sheet:
            self._raise_complexity_limit('工作表列号超过安全限制')
        return column, row

    def _validate_shared_string_references(self) -> None:
        for index, reference_count in self.shared_string_references.items():
            if index >= len(self.shared_string_lengths):
                self._raise_invalid('共享字符串索引越界')
            self._add_text_characters(self.shared_string_lengths[index] * reference_count)

    def _add_text_characters(self, count: int) -> None:
        self.counters.text_characters += count
        if self.counters.text_characters > self.config.max_ooxml_text_characters:
            self._raise_complexity_limit('工作簿单元格文本总量超过安全限制')

    def _check_cell_text_length(self, length: int) -> None:
        if length > self.config.max_cell_text_length:
            raise shot_grid_error(422, 'SG_IMPORT_CELL_TEXT_TOO_LONG', '工作簿包含超过长度限制的单元格文本')

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        namespace, separator, local_name = name.rpartition('}')
        if not separator:
            return '', name
        return namespace, local_name

    @staticmethod
    def _reject_unsafe_xml(*_args: Any) -> None:
        raise shot_grid_error(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿 OOXML 不允许包含 DTD 或实体声明')

    @staticmethod
    def _reject_external_entity(*_args: Any) -> int:
        raise shot_grid_error(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿 OOXML 不允许包含外部实体')

    @staticmethod
    def _raise_invalid(message: str) -> None:
        raise shot_grid_error(422, 'SG_IMPORT_FILE_INVALID', message)

    @staticmethod
    def _raise_row_limit(message: str) -> None:
        raise shot_grid_error(422, 'SG_IMPORT_ROW_LIMIT_EXCEEDED', message)

    @staticmethod
    def _raise_complexity_limit(message: str) -> None:
        raise shot_grid_error(413, 'SG_IMPORT_WORKBOOK_TOO_COMPLEX', message)


class ExcelSecurityService:
    """在解析 XLSX 前执行文件、ZIP 容器和 OOXML 资源安全门禁。"""

    @classmethod
    def validate_and_hash(
        cls,
        file_name: str,
        contents: bytes,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> str:
        if not file_name or not file_name.lower().endswith('.xlsx'):
            cls._raise(422, 'SG_IMPORT_FILE_TYPE_INVALID', '仅支持 .xlsx 格式')
        if not contents:
            cls._raise(422, 'SG_IMPORT_FILE_EMPTY', '导入文件不能为空')
        if len(contents) > config.max_file_size_bytes:
            cls._raise(413, 'SG_IMPORT_FILE_TOO_LARGE', '导入文件超过大小限制')

        try:
            with zipfile.ZipFile(io.BytesIO(contents)) as archive:
                entries = archive.infolist()
                if len(entries) > config.max_archive_entries:
                    cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿内部文件数量超过限制')
                cls._validate_raw_central_directory_names(contents, archive.start_dir, len(entries))
                cls._validate_entry_names(entries)
                names = {entry.filename for entry in entries}
                if '[Content_Types].xml' not in names or 'xl/workbook.xml' not in names:
                    cls._raise(422, 'SG_IMPORT_FILE_INVALID', '文件不是有效的 XLSX 工作簿')

                total_uncompressed = 0
                for entry in entries:
                    total_uncompressed += entry.file_size
                    if total_uncompressed > config.max_uncompressed_bytes:
                        cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿解压后超过安全限制')
                    compressed_size = max(entry.compress_size, 1)
                    if entry.file_size > compressed_size * config.max_compression_ratio:
                        cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿包含异常压缩内容')
                _OoxmlPreflight(config).inspect(archive)
        except zipfile.BadZipFile as exc:
            raise shot_grid_error(422, 'SG_IMPORT_FILE_INVALID', '文件不是有效的 XLSX 工作簿') from exc

        return hashlib.sha256(contents).hexdigest()

    @classmethod
    async def validate_and_hash_in_thread(
        cls,
        file_name: str,
        contents: bytes,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> str:
        """在线程中执行 ZIP 与 OOXML 流式门禁，避免阻塞异步请求循环。"""
        return await asyncio.to_thread(cls.validate_and_hash, file_name, contents, config)

    @staticmethod
    async def parse_in_thread(parser: Callable[[bytes], T], contents: bytes) -> T:
        """隔离 openpyxl 等同步 CPU/文件解析，避免阻塞事件循环。"""
        result = await asyncio.to_thread(parser, contents)
        if inspect.isawaitable(result):
            raise TypeError('Excel parser 必须是同步 callable')
        return result

    @classmethod
    def _validate_entry_names(cls, entries: list[zipfile.ZipInfo]) -> None:
        seen_names: set[str] = set()
        for entry in entries:
            name = entry.filename
            normalized_lower = name.casefold()
            path = PurePosixPath(name)
            if (
                not name
                or '\\' in name
                or name.startswith('/')
                or re.match(r'^[A-Za-z]:', name)
                or any(part in {'.', '..'} for part in path.parts)
                or '\x00' in name
            ):
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿包含不安全的 ZIP 路径')
            if normalized_lower.startswith('xl/externallinks/'):
                cls._raise(422, 'SG_IMPORT_EXTERNAL_LINK_NOT_ALLOWED', '工作簿不允许包含外部链接')
            if entry.flag_bits & 0x1:
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿不允许包含加密 ZIP 条目')
            if normalized_lower in seen_names:
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿包含重复 ZIP 条目')
            seen_names.add(normalized_lower)

    @classmethod
    def _validate_raw_central_directory_names(cls, contents: bytes, start_offset: int, entry_count: int) -> None:
        """绕过 Windows zipfile 的反斜线规范化，检查中央目录原始文件名。"""
        central_header_size = 46
        central_signature = b'PK\x01\x02'
        offset = start_offset
        for _ in range(entry_count):
            if offset < 0 or contents[offset : offset + 4] != central_signature:
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿 ZIP 中央目录结构异常')
            header_end = offset + central_header_size
            if header_end > len(contents):
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿 ZIP 中央目录越界')
            name_length = int.from_bytes(contents[offset + 28 : offset + 30], 'little')
            extra_length = int.from_bytes(contents[offset + 30 : offset + 32], 'little')
            comment_length = int.from_bytes(contents[offset + 32 : offset + 34], 'little')
            entry_end = header_end + name_length + extra_length + comment_length
            if entry_end > len(contents):
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿 ZIP 中央目录条目越界')
            if b'\\' in contents[header_end : header_end + name_length]:
                cls._raise(422, 'SG_IMPORT_ARCHIVE_UNSAFE', '工作簿包含不安全的 ZIP 路径')
            offset = entry_end

    @staticmethod
    def _raise(http_status: int, error_key: str, message: str) -> Any:
        raise shot_grid_error(http_status, error_key, message)
