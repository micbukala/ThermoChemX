# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Perplex data exporter for ThermoChemX composition data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .composition import BulkComposition

__all__ = [
    "PerplexExporter", "ExportResult", "write_batch", "_get_template_dim_suffix",
    "_format_value", "_format_component_line", "_inject_component_block",
]


# ---------------------------------------------------------------------------
# Module-level formatting helpers — shared by all TargetAdapters so that the
# formatting conventions (5 decimals / scientific notation, column layout) are
# defined in exactly one place.
# ---------------------------------------------------------------------------

def _format_value(value: float) -> str:
    """Format a single mol/kg (or wt%) value for Perplex .dat output.

    >= 0.01  →  5 decimal places  (e.g. "12.50000")
    < 0.01   →  scientific notation  (e.g. "1.23000E-03")
    """
    if abs(value) >= 0.01:
        return f"{value:.5f}"
    return f"{value:.5E}"


def _format_component_line(key: str, value: float) -> str:
    """Format one component line for a Perplex thermodynamic component list."""
    return f"{key}    1  {_format_value(value)}      0.00000      0.00000     molar amount"


def _inject_component_block(template_text: str, component_block: str) -> str:
    """Splice *component_block* into a Perplex template, replacing the existing
    ``begin/end thermodynamic component list`` section.

    Args:
        template_text:   Full text of the Perplex template file.
        component_block: New block including both begin/end markers.

    Returns:
        Modified template text.

    Raises:
        ValueError: If either marker is absent from the template.
    """
    begin_marker = "begin thermodynamic component list"
    end_marker   = "end thermodynamic component list"

    begin_pos = template_text.find(begin_marker)
    if begin_pos == -1:
        raise ValueError(f"Template missing '{begin_marker}' marker")

    end_pos = template_text.find(end_marker, begin_pos)
    if end_pos == -1:
        raise ValueError(f"Template missing '{end_marker}' marker")

    end_line_end = template_text.find("\n", end_pos)
    end_line_end = len(template_text) if end_line_end == -1 else end_line_end + 1

    return template_text[:begin_pos] + component_block + template_text[end_line_end:]


def _sanitize_filename(text: str) -> str:
    """
    Sanitize text to create safe filename.
    Replaces forbidden filename characters with underscores.
    
    Args:
        text: Input text to sanitize
    
    Returns:
        Sanitized text safe for use in filenames
    """
    # Characters forbidden in Windows/Linux filenames
    forbidden_chars = r'[\\/:*?"<>|]'
    # Replace forbidden characters with underscore
    sanitized = re.sub(forbidden_chars, '_', text)
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip leading/trailing whitespace and underscores
    sanitized = sanitized.strip().strip('_')
    return sanitized


@dataclass
class ExportResult:
    """Result of exporting composition data to Perplex format."""

    exported_components: list[str] = field(default_factory=list)  # component names exported
    filepath: str = ""  # output file path
    warnings: list[str] = field(default_factory=list)  # non-fatal warnings
    companion_filepath: str = ""  # optional template-injected companion file


class PerplexExporter:
    """
    Stateless exporter for converting MolarModel data to Perplex-compatible .dat format.
    
    Follows same pattern as MolarModel — holds BulkComposition reference, no internal state.
    """

    def __init__(self, composition: BulkComposition) -> None:
        """
        Args:
            composition: Instance of BulkComposition (data source)
        """
        self._comp = composition

    def _format_value(self, value: float) -> str:
        """Format a mol/kg value — delegates to module-level ``_format_value``."""
        return _format_value(value)

    def _format_component_line(self, key: str, value: float) -> str:
        """Format one component line — delegates to module-level ``_format_component_line``."""
        return _format_component_line(key, value)

    def generate_component_block(self) -> str:
        """
        Generate ONLY the thermodynamic component list block (no snapshot).
        
        Returns:
            Multi-line string with begin/end markers and component lines.
        """
        # Get mol/kg data from model
        mol_kg_data = self._comp.model.all_mol_kg
        
        # Filter non-zero components and format lines
        component_lines = []
        
        for key, value in mol_kg_data.items():
            if value != 0.0:
                component_lines.append(self._format_component_line(key, value))
        
        # Build component block with markers
        output_lines = ["begin thermodynamic component list"]
        output_lines.extend(component_lines)
        output_lines.append("end thermodynamic component list")
        
        return "\n".join(output_lines)

    def generate_perplex_data(self) -> str:
        """
        Generate complete Perplex format data from composition model.
        
        Returns:
            Multi-line string with header, component lines, footer, and snapshot
        """
        # Generate component block
        component_block = self.generate_component_block()
        
        # Build output with component block and snapshot
        output_lines = [component_block]
        output_lines.append("")  # blank separator line
        output_lines.append(self.generate_snapshot())
        
        return "\n".join(output_lines)

    def generate_snapshot(
        self,
        source_file: str = "",
    ) -> str:
        """
        Generate composition snapshot section (format v1).

        Args:
            source_file:  Original import filename (informational).  If empty,
                          the ``tchx.source_file`` header line is omitted.

        Returns:
            Multi-line string beginning with ``begin composition snapshot``
            and ending with ``end composition snapshot``.
        """
        from .composition_schema import SNAPSHOT_SCHEMA

        KEY_W = 24  # key column width (longest key = der.total_model_o_corr = 22 chars)

        lines = [
            "begin composition snapshot",
            "# ThermoChemX composition snapshot",
            f"{'tchx.format_version':<{KEY_W}}1",
        ]
        if source_file:
            lines.append(f"{'tchx.source_file':<{KEY_W}}{source_file}")
        lines.append("")

        # === in.* section — lossless repr() so float(repr(x)) == x exactly ===
        lines.append("# === input (authoritative; re-import reads ONLY in.* keys) ===")
        for f in SNAPSHOT_SCHEMA:
            if f.section != "in":
                continue
            value = f.get(self._comp)
            if isinstance(value, str):
                lines.append(f"{f.file_key:<{KEY_W}}{value}".rstrip())
            else:
                comment = f"  # {f.unit}" if f.unit else ""
                lines.append(f"{f.file_key:<{KEY_W}}{repr(value)}{comment}")

        # === der.* section — 5-decimal pretty format for human readability ===
        lines.append("")
        lines.append("# === derived (informational only; ignored on import) ===")
        for f in SNAPSHOT_SCHEMA:
            if f.section != "der":
                continue
            value = f.get(self._comp)
            comment = f"  # {f.unit}" if f.unit else ""
            lines.append(f"{f.file_key:<{KEY_W}}{_format_value(value)}{comment}")

        lines.append("end composition snapshot")
        return "\n".join(lines)

    def generate_template_output(self, template_content: str) -> str:
        """
        Generate Perplex template file with injected component list.
        
        Finds the thermodynamic component list markers in the template and replaces
        everything between them with the current composition's component block.
        
        Args:
            template_content: Full text content of the template file
        
        Returns:
            Template text with injected component list
        
        Raises:
            ValueError: If template markers are not found
        """
        return _inject_component_block(template_content, self.generate_component_block())

    def write_to_template(
        self,
        template_path: str,
        output_path: str
    ) -> ExportResult:
        """
        Write composition data to a Perplex template file.
        
        Reads the template, injects the component list, and writes the result.
        
        Args:
            template_path: Path to the template file to read
            output_path: Path where output file should be written
        
        Returns:
            ExportResult with exported components, filepath, and any warnings
        
        Raises:
            IOError: If template cannot be read or output cannot be written
            ValueError: If template format is invalid
        """
        # Read template
        try:
            template_content = Path(template_path).read_text(encoding="utf-8")
        except IOError as e:
            raise IOError(f"Cannot read template file {template_path}: {e}") from e
        
        # Generate output with injected components
        try:
            output_data = self.generate_template_output(template_content)
        except ValueError as e:
            raise ValueError(f"Template format error: {e}") from e
        
        # Track what we're exporting
        mol_kg_data = self._comp.model.all_mol_kg
        exported_components = [key for key, value in mol_kg_data.items() if value != 0.0]
        
        warnings = []
        if not exported_components:
            warnings.append("No non-zero components to export")
        
        # Write to file
        try:
            path_obj = Path(output_path)
            path_obj.write_text(output_data, encoding="utf-8")
        except IOError as e:
            raise IOError(f"Cannot write to file {output_path}: {e}") from e
        except Exception as e:
            raise Exception(f"Unexpected error writing to {output_path}: {e}") from e
        
        return ExportResult(
            exported_components=exported_components,
            filepath=str(path_obj.absolute()),
            warnings=warnings
        )

    def write_to_file(self, output_path: str) -> ExportResult:
        """
        Write Perplex-formatted data to file.
        
        Args:
            output_path: Path where output file should be written
        
        Returns:
            ExportResult with exported components, filepath, and any warnings
        
        Raises:
            IOError: If file cannot be written
            Exception: For other file system errors
        """
        # Generate data
        data = self.generate_perplex_data()
        
        # Track what we're exporting
        mol_kg_data = self._comp.model.all_mol_kg
        exported_components = [key for key, value in mol_kg_data.items() if value != 0.0]
        
        warnings = []
        
        # Warn if no non-zero components
        if not exported_components:
            warnings.append("No non-zero components to export")
        
        # Write to file
        try:
            path_obj = Path(output_path)
            path_obj.write_text(data, encoding="utf-8")
        except IOError as e:
            raise IOError(f"Cannot write to file {output_path}: {e}") from e
        except Exception as e:
            raise Exception(f"Unexpected error writing to {output_path}: {e}") from e
        
        return ExportResult(
            exported_components=exported_components,
            filepath=str(path_obj.absolute()),
            warnings=warnings
        )


def _get_template_dim_suffix(template_path: str) -> str:
    """Determine filename suffix from Perplex template calculation type.

    Returns '_1d' for types 7/10, '_2d' for type 5, '_1d' as fallback.
    """
    try:
        content = Path(template_path).read_text(encoding="utf-8")
        for line in content.splitlines():
            if "calculation type" in line.lower():
                m = re.match(r"\s*(\d+)", line)
                if m:
                    calc_type = int(m.group(1))
                    if calc_type == 5:
                        return "_2d"
                    if calc_type in (7, 10):
                        return "_1d"
                break
    except Exception:
        pass
    return "_1d"


def write_batch(
    samples: list[tuple[str, "BulkComposition"]],
    output_dir: str,
    template_path: str | None = None
) -> list[ExportResult]:
    """
    Export multiple samples to separate Perplex .dat files.
    
    Args:
        samples: List of (sample_name, BulkComposition) tuples.
        output_dir: Directory where output files will be written.
        template_path: Optional path to Perplex template file. If provided,
            generates both {sample}_tchx.dat and {prefix}_{sample}.dat files
            where prefix is 1d_ (calc type 7/10) or 2d_ (calc type 5).
    
    Returns:
        List of ExportResult, one per sample (or two per sample if template
        is provided). Failed exports have warnings.
    """
    results = []
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for sample_name, composition in samples:
        # Sanitize sample name to prevent invalid filename characters
        safe_name = _sanitize_filename(sample_name)
        exporter = PerplexExporter(composition)
        
        # Always export standard elem.dat file
        filepath = str(output_path / f"{safe_name}_elem.dat")
        try:
            result = exporter.write_to_file(filepath)
        except Exception as e:
            result = ExportResult(
                exported_components=[],
                filepath=filepath,
                warnings=[f"Failed to export: {e}"]
            )
        results.append(result)
        
        # If template provided, also export template file
        if template_path:
            suffix = _get_template_dim_suffix(template_path)
            template_filepath = str(output_path / f"{safe_name}{suffix}.dat")
            try:
                template_result = exporter.write_to_template(template_path, template_filepath)
            except Exception as e:
                template_result = ExportResult(
                    exported_components=[],
                    filepath=template_filepath,
                    warnings=[f"Failed to export template: {e}"]
                )
            results.append(template_result)
    
    return results
