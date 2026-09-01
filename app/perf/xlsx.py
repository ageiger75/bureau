"""A minimal read-only XLSX reader, standard library only.

`AGENTS.md` settled this before the need arose: spreadsheet extraction uses `zipfile` and
the standard XML parser rather than a third-party package, because every dependency that
parses externally-supplied files is a surface this product does not need.

Read-only and deliberately narrow: sheet names, cell values, nothing else. No formulas are
evaluated — a workbook saved by Excel carries the last computed value, which is what a
budget file is for.
"""

from __future__ import annotations

import re
import zipfile
from typing import Dict, Iterator, List, Optional, Sequence
from xml.etree import ElementTree

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DOC_RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

#: Refuse a workbook that would expand absurdly. A budget file is small; anything else is
#: either a mistake or something this reader has no business unpacking.
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class WorkbookError(RuntimeError):
    """The file is not a workbook this reader can serve."""


def _column_index(reference: str) -> int:
    """`C7` -> 2. Column letters are base-26 with no zero."""
    letters = re.match(r"([A-Z]+)", reference or "")
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


class Workbook:
    """One workbook, opened for reading."""

    def __init__(self, path) -> None:
        try:
            self._zip = zipfile.ZipFile(str(path))
        except (zipfile.BadZipFile, OSError) as exc:
            raise WorkbookError("%s is not a readable .xlsx file." % path) from exc

        total = sum(info.file_size for info in self._zip.infolist())
        if total > MAX_UNCOMPRESSED_BYTES:
            self._zip.close()
            raise WorkbookError("Workbook expands to %d bytes; refusing to read." % total)

        self._shared: Optional[List[str]] = None
        self._sheets = self._read_sheet_index()

    # ------------------------------------------------------------------ lifecycle

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "Workbook":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------ structure

    def _read_sheet_index(self) -> Dict[str, str]:
        """Sheet name -> path inside the archive, resolved through the relationships."""
        try:
            book = ElementTree.fromstring(self._zip.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        except KeyError as exc:
            raise WorkbookError("Workbook is missing its index.") from exc

        targets = {
            node.get("Id"): node.get("Target", "")
            for node in rels.findall("%sRelationship" % RELS)
        }

        sheets: Dict[str, str] = {}
        for node in book.iter("%ssheet" % MAIN):
            name = node.get("name") or ""
            target = targets.get(node.get("%sid" % DOC_RELS), "")
            if not name or not target:
                continue
            # Two conventions live in the wild for this attribute: a path relative to
            # the part that declares it — "worksheets/sheet1.xml", what Excel writes —
            # and one absolute from the package root, "/xl/worksheets/sheet1.xml", which
            # some writers emit instead. Prefixing both alike produced "xl/xl/…" and a
            # workbook that read as missing its only sheet.
            target = target.replace("\\", "/")
            if target.startswith("/"):
                path = target.lstrip("/")
            elif target.startswith("xl/"):
                path = target
            else:
                path = "xl/" + target
            sheets[name] = path
        return sheets

    @property
    def sheet_names(self) -> List[str]:
        return list(self._sheets)

    # ------------------------------------------------------------------ values

    def _shared_strings(self) -> List[str]:
        if self._shared is not None:
            return self._shared
        values: List[str] = []
        try:
            raw = self._zip.read("xl/sharedStrings.xml")
        except KeyError:
            self._shared = values
            return values
        for item in ElementTree.fromstring(raw).iter("%ssi" % MAIN):
            # A string may be split across runs when part of it is styled differently.
            values.append("".join(node.text or "" for node in item.iter("%st" % MAIN)))
        self._shared = values
        return values

    def rows(self, sheet_name: str) -> Iterator[List[object]]:
        """Yield each row as a list of values, padded so column positions line up.

        Empty cells are `None`. Numbers come back as floats, text as strings — enough for
        a budget file, and nothing more.
        """
        if sheet_name not in self._sheets:
            raise WorkbookError(
                "No sheet named %r. Available: %s"
                % (sheet_name, ", ".join(self.sheet_names))
            )
        shared = self._shared_strings()
        root = ElementTree.fromstring(self._zip.read(self._sheets[sheet_name]))

        for row in root.iter("%srow" % MAIN):
            cells: List[object] = []
            for cell in row.findall("%sc" % MAIN):
                position = _column_index(cell.get("r", ""))
                while len(cells) < position:
                    cells.append(None)
                cells.append(self._cell_value(cell, shared))
            yield cells

    def _cell_value(self, cell, shared: Sequence[str]):
        kind = cell.get("t")

        if kind == "inlineStr":
            return "".join(node.text or "" for node in cell.iter("%st" % MAIN)) or None

        value = cell.find("%sv" % MAIN)
        if value is None or value.text is None:
            return None
        text = value.text

        if kind == "s":
            try:
                return shared[int(text)]
            except (ValueError, IndexError):
                return None
        if kind in ("str", "e"):
            return text
        if kind == "b":
            return text == "1"
        try:
            return float(text)
        except ValueError:
            return text


def read_sheet(path, sheet_name: str) -> List[List[object]]:
    with Workbook(path) as workbook:
        return list(workbook.rows(sheet_name))
