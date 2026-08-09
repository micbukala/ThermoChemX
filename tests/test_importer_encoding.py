# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Encoding + delimiter hardening tests for the CSV import path.

Covers:
- UTF-8 (with and without BOM) imports cleanly and BOM never leaks into keys.
- cp1252-encoded files import via fallback with exactly one encoding warning.
- Delimiter auto-detection works for comma / semicolon / tab, including a
  Sniffer-defeating string handled by the deterministic fallback rule.
- Random binary content produces a clean error, never a raw traceback.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from thermochemx.core.importer import (
    parse_file_multi,
    _decode_file,
    _detect_delimiter,
    ENCODING_FALLBACK_WARNING,
    UNREADABLE_FILE_MESSAGE,
)

TOL = 1e-6

# ---------------------------------------------------------------------------
# Shared reference content: same composition rendered in 3 encodings/delimiters
# ---------------------------------------------------------------------------
#
# Column layout is the three-column (comment + key + value) form so we can
# exercise BOM-leak scenarios (BOM must NOT attach to the key column even if
# the Description column is dropped in a variant).
#
# Description cells contain "³" and "µ" — both encodable in cp1252.
# (The full Excel example also has "⁺" and "Σ" which cp1252 CANNOT
# represent; those live only in the BOM/UTF-8 fixture below.)

_ROWS = [
    ("SiO2 (wt%)",                    "SiO2_wt",                50.0),
    ("H2O (wt%)",                     "H2O_wt",                 2.0),
    ("total iron as Fe2O3 (wt%)",     "Fe2O3_total_wt",         10.0),
    ("Fe³ ratio (Fe3/Fetotal)",       "Fe3plus_Fetotal_ratio",  0.25),
    ("total S (µg/g equivalent)",     "S_total_wt",             0.5),
]

# Extra rows used ONLY in the BOM/UTF-8 fixture where "⁺" and "Σ" are
# legitimately representable — mirrors the shipped example file.
_ROWS_UTF8_EXTRAS = [
    ("Fe³⁺/ΣFe molar ratio",          "Fe3plus_Fetotal_ratio",  0.25),
]


def _content(delimiter: str) -> str:
    return "\n".join(delimiter.join(str(c) for c in row) for row in _ROWS) + "\n"


def _write(bytes_content: bytes, suffix: str = ".csv") -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(bytes_content)
    f.close()
    return f.name


def _import(path: str):
    """Small wrapper returning (samples, file_warnings)."""
    return parse_file_multi(path)


# ---------------------------------------------------------------------------
# 1. UTF-8 with BOM + semicolon
# ---------------------------------------------------------------------------

class TestUtf8BomSemicolon:

    def test_zero_warnings_with_bom_and_description(self):
        text = _content(";")
        path = _write(("\ufeff" + text).encode("utf-8"))
        try:
            samples, warnings = _import(path)
            assert warnings == []
            assert len(samples) == 1
            assert abs(samples[0].data["SiO2_wt"] - 50.0) < TOL
        finally:
            os.unlink(path)

    def test_bom_does_not_leak_when_description_column_absent(self):
        """When the description column is removed the BOM lands directly on the
        key header — utf-8-sig must strip it before csv sees it."""
        no_desc = "\n".join(
            ";".join([row[1], str(row[2])]) for row in _ROWS
        ) + "\n"
        path = _write(("\ufeff" + no_desc).encode("utf-8"))
        try:
            samples, warnings = _import(path)
            assert warnings == []
            # Key must be recognisable — BOM would have prevented aliasing.
            assert "SiO2_wt" in samples[0].data
            assert abs(samples[0].data["SiO2_wt"] - 50.0) < TOL
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2. cp1252 (Excel ANSI re-save) + tab
# ---------------------------------------------------------------------------

class TestCp1252Tab:

    def test_imports_with_exactly_one_encoding_warning(self):
        text = _content("\t")
        path = _write(text.encode("cp1252"))
        try:
            samples, warnings = _import(path)
            assert warnings == [ENCODING_FALLBACK_WARNING]
            assert len(samples) == 1
            assert abs(samples[0].data["SiO2_wt"] - 50.0) < TOL
        finally:
            os.unlink(path)

    def test_values_match_utf8_variant(self):
        text_tab = _content("\t")
        text_semi = _content(";")
        path_ansi = _write(text_tab.encode("cp1252"))
        path_utf8 = _write(text_semi.encode("utf-8"))
        try:
            samples_ansi, _ = _import(path_ansi)
            samples_utf8, _ = _import(path_utf8)
            # Every numeric key present in the utf-8 sample must match.
            for k, v in samples_utf8[0].data.items():
                assert abs(samples_ansi[0].data[k] - v) < TOL, k
        finally:
            os.unlink(path_ansi)
            os.unlink(path_utf8)


# ---------------------------------------------------------------------------
# 3. Pure-ASCII + comma
# ---------------------------------------------------------------------------

class TestAsciiComma:

    def test_zero_warnings(self):
        # Strip the non-ASCII fields to keep the file truly ASCII.
        ascii_rows = [(desc.encode("ascii", "replace").decode(), key, val)
                       for desc, key, val in _ROWS]
        content = "\n".join(",".join(str(c) for c in row) for row in ascii_rows) + "\n"
        path = _write(content.encode("ascii"))
        try:
            samples, warnings = _import(path)
            assert warnings == []
            assert abs(samples[0].data["SiO2_wt"] - 50.0) < TOL
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 4. Garbage binary content
# ---------------------------------------------------------------------------

class TestGarbageBinary:

    def test_random_bytes_produce_clean_error_no_traceback(self):
        # Bytes chosen to be undecodable as UTF-8 AND, if decoded by cp1252,
        # to contain no alias-key canary. cp1252 accepts most byte values so
        # we can't rely on it raising; instead rely on the canary sanity check.
        garbage = bytes(range(256)) * 4  # every byte 0..255
        path = _write(garbage)
        try:
            with pytest.raises(ValueError) as excinfo:
                _import(path)
            # Message must be the user-facing string, not a codec exception.
            assert str(excinfo.value) == UNREADABLE_FILE_MESSAGE
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 5. Delimiter detection unit tests
# ---------------------------------------------------------------------------

class TestDetectDelimiter:

    def test_comma(self):
        assert _detect_delimiter("a,b,c\n1,2,3\n4,5,6\n") == ","

    def test_semicolon(self):
        assert _detect_delimiter("a;b;c\n1;2;3\n4;5;6\n") == ";"

    def test_tab(self):
        assert _detect_delimiter("a\tb\tc\n1\t2\t3\n4\t5\t6\n") == "\t"

    def test_sniffer_defeating_ambiguous_input(self):
        """Sniffer often mis-detects when non-delimiter commas appear in
        description columns. The deterministic scoring must still pick
        the delimiter that yields the most consistent >1 column split.
        """
        # 3 rows, tab-separated into 3 columns, with a stray comma in the
        # description column of each row (mimics free-text descriptions in
        # real composition files). Comma splitting produces at most 2
        # columns; tab produces 3 → tab should win.
        sample = (
            "Fe2O3, total\tFe2O3_total_wt\t8.0\n"
            "CO2 (µg/g), etc\tCO2_total_wt\t3.0\n"
            "S, sulfates only\tS_total_wt\t0.5\n"
        )
        assert _detect_delimiter(sample) == "\t"


# ---------------------------------------------------------------------------
# 6. Cross-encoding numerical equivalence (BOM + cp1252 + ASCII agree)
# ---------------------------------------------------------------------------

class TestCrossEncodingConsistency:

    def test_three_variants_yield_identical_numeric_data(self):
        # Three files, three encodings/delimiters, same composition.
        paths: list[str] = []
        try:
            # UTF-8 with BOM, semicolon
            paths.append(_write(("\ufeff" + _content(";")).encode("utf-8")))
            # cp1252, tab
            paths.append(_write(_content("\t").encode("cp1252")))
            # UTF-8 no BOM, comma
            paths.append(_write(_content(",").encode("utf-8")))

            samples_list = [_import(p)[0][0] for p in paths]
            ref = samples_list[0].data
            for other in samples_list[1:]:
                for k, v in ref.items():
                    assert abs(other.data[k] - v) < TOL, k
        finally:
            for p in paths:
                os.unlink(p)


# ---------------------------------------------------------------------------
# 7. _decode_file direct unit coverage
# ---------------------------------------------------------------------------

class TestDecodeFile:

    def test_utf8_no_bom(self):
        path = _write(_content(",").encode("utf-8"))
        try:
            text, warnings = _decode_file(path)
            assert warnings == []
            assert "SiO2_wt" in text
        finally:
            os.unlink(path)

    def test_cp1252_produces_warning(self):
        path = _write(_content(",").encode("cp1252"))
        try:
            text, warnings = _decode_file(path)
            assert warnings == [ENCODING_FALLBACK_WARNING]
            assert "SiO2_wt" in text
        finally:
            os.unlink(path)
