# ThermoChemX — data dictionary

Single reference for every name of the same quantity. The **canonical name**
(the `BulkComposition` / subsystem attribute) is the source of truth; all input
spellings resolve to it, all outputs derive from it.

**CSV/XLSX key (v1.0)** is the primary input spelling used in the
example files. The **Description** column is the comment text intended for
the optional first (comment) column of the three-column import layout (see bottom).
**Snapshot key**: `in.*` = authoritative
(read on re-import), `der.*` = derived (ignored on import). **Perple_X component**
names are fixed externally — not ours to rename.

## Simple oxides and volatiles

| CSV/XLSX key (v1.0) | Description (comment column) | Canonical (code) | Snapshot key | Perple_X |
|---|---|---|---|---|
| `SiO2_wt` … `P2O5_wt` | e.g. "SiO₂ (wt%)" | `simple_oxides["SiO2"]` … | `in.SiO2` … `in.P2O5` | `SiO2` … `P2O5` |
| `H2O_wt` | "H₂O (wt%)" | `simple_oxides["H2O"]` (raw) | `in.H2O` | `H2O` |
| `LOI_wt` | "loss on ignition (wt%)" | `loi_measured` | `in.LOI` | — |
| — | (inferred from fields present) | `_volatile_mode` | `in.volatile_mode` | — |
| `sample_name` | "sample label" | `sample_name` | `in.sample_name` | — |

## Iron system

| CSV/XLSX key (v1.0) | Description (comment column) | Canonical (code) | Snapshot key | Perple_X |
|---|---|---|---|---|
| `Fe2O3_total_wt` | "total iron as Fe₂O₃ (wt%)" | `iron.fe2o3_tot_wt` **(SSoT)** | `in.fe_tot_as_fe2o3_wt` | — |
| `FeO_total_wt` | "total iron as FeO (wt%)" | `iron.feo_tot_wt` | `der.feo_tot_wt` | `FeO` |
| `Fe3plus_Fetotal_ratio` | "Fe³⁺/ΣFe molar ratio" | `iron.fe3_fetot_ratio` **(SSoT)** | `in.fe3_fetot_ratio` | — |
| `Fe2O3_wt` | "ferric iron as Fe₂O₃ (wt%)" | `iron.fe3_oxide_wt` | `der.fe3_oxide_wt` | — |
| `FeO_wt` | "ferrous iron as FeO (wt%)" | `iron.fe2_oxide_wt` | `der.fe2_oxide_wt` | → `FeO` |
| `Fe2plus_wt` | "ferrous iron as element (wt%)" | `iron.fe2_wt` | `der.fe2_wt` | — |
| `Fe3plus_wt` | "ferric iron as element (wt%)" | `iron.fe3_wt` | `der.fe3_wt` | — |
| `Fe2plus_ugg` | "ferrous iron (µg/g)" | `iron.fe2_ugg` | `der.fe2_ugg` | — |
| `Fe3plus_ugg` | "ferric iron (µg/g)" | `iron.fe3_ugg` | `der.fe3_ugg` | — |

## Carbon system

| CSV/XLSX key (v1.0) | Description (comment column) | Canonical (code) | Snapshot key | Perple_X |
|---|---|---|---|---|
| `C_total_wt` | "total carbon as element (wt%)" | `carbon.c_wt` **(SSoT)** | `in.c_tot_wt` | `CO2` |
| `CO2_total_wt` | "total carbon as CO₂ (wt%)" | `carbon.co2_wt` | `der.co2_wt` | `CO2` |
| `C_total_ugg` | "total carbon (µg/g)" | `carbon.total_c_ugg` | — | — |
| `C4plus_Ctotal_ratio` | "C⁴⁺/ΣC (carbonate fraction) molar ratio" | `carbon.co2_ctot_ratio` **(SSoT)** | `in.co2_ctot_ratio` | — |
| `C0_wt` | "graphitic carbon C⁰ as element (wt%)" | `carbon.c0_wt` | `der.c0_wt` | — |
| `C4plus_wt` | "carbonate carbon C⁴⁺ as element (wt%)" | `carbon.c4_wt` | `der.c4_wt` | — |
| `C0_ugg` | "graphitic carbon (µg/g)" | `carbon.c0_ugg` | `der.c0_ugg` | — |
| `C4plus_ugg` | "carbonate carbon (µg/g)" | `carbon.c4_ugg` | `der.c4_ugg` | — |

## Sulfur system

| CSV/XLSX key (v1.0) | Description (comment column) | Canonical (code) | Snapshot key | Perple_X |
|---|---|---|---|---|
| `S_total_wt` | "total sulfur as element (wt%)" | `sulfur.s_wt` **(SSoT)** | `in.s_tot_wt` | `S2` |
| `SO3_total_wt` | "total sulfur as SO₃ (wt%)" | `sulfur.so3_wt` | `der.so3_wt` | — |
| `S_total_ugg` | "total sulfur (µg/g)" | `sulfur.total_s_ugg` | — | — |
| `S6plus_Stotal_ratio` | "S⁶⁺/ΣS (sulfate fraction) molar ratio" | `sulfur.so3_stot_ratio` **(SSoT)** | `in.so3_stot_ratio` | — |
| `S1minus_Ssulfides_ratio` | "S¹⁻/ΣS(reduced) molar ratio" | `sulfur.s1_sred_ratio` **(SSoT)** | `in.s1_sred_ratio` | — |
| `S6plus_wt` | "sulfate sulfur S⁶⁺ as element (wt%)" | `sulfur.s6_wt` | `der.s6_wt` | — |
| `S1minus_wt` | "disulfide sulfur S¹⁻ as element (wt%)" | `sulfur.s1_wt` | `der.s1_wt` | — |
| `S2minus_wt` | "monosulfide sulfur S²⁻ as element (wt%)" | `sulfur.s2_wt` | `der.s2_wt` | — |
| `S6plus_ugg` | "sulfate sulfur (µg/g)" | `sulfur.s6_ugg` | `der.s6_ugg` | — |
| `S1minus_ugg` | "disulfide sulfur (µg/g)" | `sulfur.s1_ugg` | `der.s1_ugg` | — |
| `S2minus_ugg` | "monosulfide sulfur (µg/g)" | `sulfur.s2_ugg` | `der.s2_ugg` | — |

## Three-column import layout (optional comment column)

Example files may use a self-documenting layout:

| column 0 (comment, ignored) | column 1 (key) | column 2 … N (data) |
|---|---|---|
| the amount of C (wt%) in carbonates | `C4plus_wt` | 0.20 |

- **Column 0** is free-text description, **ignored by the importer**.
- **Column 1** is the recognized key.
- **Columns 2+** are per-sample values.

The comment column is **optional**. The importer auto-detects layout: if column 0 holds
recognized keys, it is the legacy two-column form (key in col 0).

## Why the vocabularies differ
- **CSV keys** are explicit about oxidation state, form, and unit (`C4plus_wt`, not `C_carbonate`) to remove ambiguity (e.g. carbonate C as element vs as CO₂).
- **Canonical code names** use oxidation state (`c0`, `c4`, `s6`) and unambiguous SSoT ratios.
- **Snapshot keys** mirror canonical names so re-import is exact.
- **Perple_X components** are an external output convention.

All three input vocabularies resolve through **one alias registry** keyed to the canonical names.
