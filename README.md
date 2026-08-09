# ThermoChemX
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.txt)

ThermoChemX is a cross-platform desktop application that converts whole-rock oxide analyses into molar amounts (mol/kg) for thermodynamic phase-equilibrium modelling, with full iron, carbon, and sulfur redox speciation, and exports Perple_X-ready input.

> **v1.0.0** — iron (Fe²⁺/Fe³⁺), carbon (graphite C⁰ / carbonate C⁴⁺), and sulfur (sulfate S⁶⁺ / disulfide S¹⁻ / monosulfide S²⁻) each carry a user-configurable redox model, with an automatic phantom-oxygen correction for sulfide-bound metals and a runtime mass-closure check.

---

## Features

- **Redox-aware conversion** of oxide wt% to mol/kg, with user-set Fe³⁺/ΣFe, C⁴⁺/ΣC, and S⁶⁺/ΣS + S¹⁻/ΣS(reduced) speciation.
- **Phantom-oxygen correction** and a runtime **mass-closure check** (Σ nᵢMᵢ = 1000 g/kg).
- **Automatic volatile handling** (H₂O / LOI coupling; no mode selection needed).
- **Two Perple_X export targets** — element basis and oxide basis.
- **Import / export**: CSV and Excel (single- or multi-sample), plus exact re-import of the application's own `.dat` snapshot.
- **Interactive GUI** with live totals, redox species, and O₂ balance; a preview that switches between export targets.

---

## Installation

**Requirements:** Python ≥ 3.10 (any standard distribution, including Anaconda/Miniconda — see note below); PySide6 and openpyxl (see `requirements.txt`).

> **Installing Python via Anaconda/Miniconda?** The Anaconda installer's *"Add Anaconda to my PATH"* option is unchecked by default. If it's unchecked, `python` and `pip` won't be recognized in a regular Command Prompt / Terminal. This is **not** fixed by opening the Python interactive shell (the `>>>` prompt) — that can't run the commands below. Instead, use the **Anaconda Prompt** (installed alongside Anaconda on Windows), or on macOS/Linux run `conda init` once and reopen your terminal — then proceed with the commands below in that same window.

### Option 1 — One-click launcher (recommended)

#### Windows — `Run_ChemX.bat`

Double-click `Run_ChemX.bat` in the project folder.

#### macOS — `Run_ChemX.command`

The `.command` file is a shell script. On first use, macOS may block it because it was downloaded from the internet or is unsigned. There are two ways to allow it:

**Option A — Terminal (recommended):**
```bash
chmod +x Run_ChemX.command
```
Then double-click the file normally.

**Option B — System Settings:**
1. Try to open `Run_ChemX.command` (it will be blocked).
2. Go to **System Settings → Privacy & Security → Security**.
3. Click **Open Anyway** next to the blocked file entry.
4. Confirm in the dialog that appears.

Either way, the launcher auto-detects Python, creates an isolated virtual environment, installs dependencies, and adds a desktop shortcut — no manual setup.

### Option 2 — Manual install

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

```cmd
:: Windows
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

On later runs, activate the environment and run the same launch command:

```bash
# Windows
venv\Scripts\activate
python app.py

# macOS / Linux
source venv/bin/activate
python3 app.py
```

> **For developers:** the source lives under `src/` and the project is pip-installable.
> From the project root, `python -m pip install -e .` installs it in editable mode, after
> which the application can also be launched as `python -m thermochemx` from any directory.
> This is not required for normal use — `python app.py` works from a plain source checkout.

---

## Usage

The essentials:

### Input

Enter a composition **manually**, or fill the template ([`import_example.csv`](examples/input/import_example.csv)) and import it. Each row is one variable, identified by its key; an optional first column may hold a free-text description, which the importer ignores. The full key list is in [`docs/data_dictionary.md`](docs/data_dictionary.md).

- **Oxides and volatiles:** `SiO2_wt`, `TiO2_wt`, `Al2O3_wt`, … plus `H2O_wt` and `LOI_wt`.
- **Redox systems (Fe, C, S):** provide each system **one route**; redundant inputs are cross-checked, and conflicts are resolved by a documented priority order with a warning.
  - **total + ratio** — a total (as oxide or element) plus the molar ratio(s) that split it into oxidation states; or
  - **explicit speciation** — the amount of each oxidation state directly.

Both routes resolve to the same internal state. Representative keys:

| System | Total + ratio | Explicit speciation |
|---|---|---|
| Iron | `Fe2O3_total_wt` or `FeO_total_wt` + `Fe3plus_Fetotal_ratio` | `Fe2O3_wt` / `FeO_wt` (or `Fe2plus_wt` / `Fe3plus_wt`) |
| Carbon | `CO2_total_wt` or `C_total_wt` + `C4plus_Ctotal_ratio` | `C0_wt` / `C4plus_wt` |
| Sulfur | `SO3_total_wt` or `S_total_wt` + `S6plus_Stotal_ratio` + `S1minus_Ssulfides_ratio` | `S6plus_wt` / `S1minus_wt` / `S2minus_wt` |

Each element amount is also accepted in µg/g (`_ugg`). See the crosswalk for the complete list.

### Output

The preview shows, for the selected target:

- **mol/kg** for each component, and the **redox species** (Fe²⁺/Fe³⁺, C⁰/C⁴⁺, S⁶⁺/S¹⁻/S²⁻).
- **O₂ balance** from the redox budget.
- **Totals:** raw calculated total; redox-partitioned model total; and the redox-corrected model total — the actual mol/kg denominator, which satisfies Σ nᵢMᵢ = 1000 g/kg.

### Export

Open **Settings…** to choose the target(s) (`Perple_X element`, `Perple_X oxide`) and, optionally, a per-target `.dat` template. **Export** writes the current sample; **Export All** (after a multi-sample import) writes one `.dat` per sample per target. Each file carries a re-importable composition snapshot.

For a full step-by-step walkthrough with worked examples, see [`docs/manual.md`](docs/manual.md).

---

## Compatible thermodynamic databases

ThermoChemX exports bulk compositions in two component conventions, so a database is
compatible with whichever export target matches its component notation:

- **Element basis** — components are elements (Si, Ti, Al, Fe, Mg, …, C, S₂, O₂, H₂). Carries the full redox budget, including reduced (graphite/sulfide) systems.
- **Oxide basis** — components are oxides plus S₂ and excess O₂ (SiO₂, TiO₂, Al₂O₃, FeO, …, CO₂, S₂, O₂, H₂O). Suitable for oxidised and non-redox workflows; for strongly reduced compositions the excess-O₂ component is capped at zero (see note), and the element basis should be used instead.

| Thermodynamic database | Component notation | Notes |
|---|---|---|
| `b89ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, NiO, P₂O₅ & S₂ |
| `b92ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, NiO, P₂O₅ & S₂ |
| `ba96ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, NiO, P₂O₅ & S₂ |
| `cr_hp02ver.dat` | oxide | Uppercase; Missing: P₂O₅ & S₂; Extra oxides |
| `DEW13BA96ver_oxides.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `DEW13HP02ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `DEW13HP02ver_oxides.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `DEW13HP622ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `DEW13HP622ver_oxides.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `DEW17HP622ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `DEW17HP622ver_oxides.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `DEW17HP62ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `DEW19HP622ver_elements.dat` | elemental | Lowercase; Extra elements |
| `DEW19HP62ver_elements.dat` | elemental | Lowercase; Extra elements |
| `DEW19HP633ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `DEW24HP622ver_elements.dat` | elemental | Lowercase; Extra elements |
| `DEW24HP62ver_elements.dat` | elemental | Lowercase; Extra elements |
| `DEW24HP633ver_elements.dat` | elemental | Lowercase; Missing: P; Extra elements |
| `hhph2013ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hp02ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, P₂O₅ & S₂; Extra oxides |
| `hp02ver_with_salt.dat` | oxide | Uppercase; Missing: Cr₂O₃, P₂O₅ & S₂; Extra oxides |
| `hp04ver.dat` | oxide | Uppercase; Missing: Cr₂O₃ & S₂; Extra oxides |
| `hp11ver_salt.dat` | oxide | Uppercase; Missing: P₂O₅; Extra oxides |
| `hp622ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hp62ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hp62ver_salt_ab_w.dat` | oxide | Lowercase; Missing: Na₂O & P₂O₅; Extra oxides |
| `hp633ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hp633ver_fsp.dat` | oxide | Lowercase; Missing: CaO, Na₂O, K₂O & P₂O₅; Extra oxides |
| `hp634ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hp636ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `hpha02ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, P₂O₅ & S₂; Extra oxides |
| `hpha622ver.dat` | oxide | Lowercase; Missing: P₂O₅; Extra oxides |
| `kel04ver.dat` | oxide | Uppercase; Missing: Cr₂O₃, P₂O₅ & S₂; Extra oxides |
| `koma06ver.dat` | oxide | Uppercase; Missing: TiO₂, Al₂O₃, Cr₂O₃, FeO, MnO, NiO, CaO, Na₂O, K₂O, P₂O₅, CO₂, S₂ & O₂ |
| `SE15ver.dat` | elemental | Lowercase; Missing: Si, Ti, Al, Cr, Mn, Mg, Ca, Ni, Na, K, P, H₂, C, S₂ & O₂; Extra elements |
| `stx11ver.dat` | oxide | Uppercase; Missing: TiO₂, Cr₂O₃, MnO, NiO, K₂O, P₂O₅, H₂O, CO₂, S₂ & O₂ |
| `stx21ver.dat` | oxide | Uppercase; Missing: TiO₂, Cr₂O₃, MnO, NiO, K₂O, P₂O₅, H₂O, CO₂ & S₂ |
| `sup92ver.dat` | oxide | Uppercase; Missing: Cr₂O₃ & P₂O₅; Extra oxides |

> **Note on reduced compositions.** In the oxide basis, strongly reduced systems (e.g. graphite- or
> sulfide-bearing) can require a negative excess-O₂ component, which Perple_X does not accept. In these
> cases ThermoChemX caps the value at zero, records the event in the composition snapshot, and issues a
> warning; the composition should then be exported in the **element basis**, which preserves the full
> reduction state.

**Tested with Perple_X:** version 7.2.1, released 3 March 2026 ([perplex.ethz.ch](https://github.com/jadconnolly/Perple_X/releases/)). The compatibility table above corresponds to the `datafiles/` directory of the Windows release archive (SHA-256 `dd053bc3c3726ee14bc4f6262c731a379aa5664b4343d48ae8f9a079d5e0cda3`). The `datafiles/` contents are the same across Windows, macOS, and Linux distributions — the archive hash differs only because of platform binaries.

> Compatibility depends on the database's component convention, not on a specific release. The output
> conforms to the standard element- and oxide-component conventions of the Holland–Powell-family and
> DEW databases; other databases using the same conventions should also work. Later Perple_X releases
> may add, remove, or modify database files — when using a different snapshot, verify from the
> database's component notation rather than by filename.


## Project structure

```
ThermoChemX/
├── Run_ChemX.bat              # one-click launcher (Windows)
├── Run_ChemX.command          # one-click launcher (macOS)
├── app.py                     # entry point (used by Run_ChemX.* and manual install)
├── pyproject.toml             # project metadata, packaging and test configuration
├── requirements.txt           # Python dependencies
├── LICENSE.txt                # GNU General Public License v3
├── README.md
├── src/
│   └── thermochemx/
│       ├── __init__.py
│       ├── __main__.py        # main() — application entry point
│       ├── core/
│       │   ├── composition.py         # central stateful composition model
│       │   ├── composition_schema.py  # snapshot schema (input / derived)
│       │   ├── model.py               # stateless mol/kg + O₂ engine
│       │   ├── importer.py            # CSV / Excel input
│       │   ├── dat_importer.py        # .dat snapshot re-import
│       │   ├── exporter.py            # .dat writer + template injection
│       │   ├── recalc/                # neutral core + normalization
│       │   │   ├── core.py            # build_recalc_result → RecalcResult
│       │   │   ├── result.py          # frozen result dataclass
│       │   │   ├── normalization.py   # normalization strategy
│       │   │   └── representation.py  # oxide-basis transform
│       │   ├── targets/               # export adapters
│       │   │   ├── base.py            # adapter base class
│       │   │   ├── perplex_element.py # element-basis adapter
│       │   │   ├── perplex_oxide.py   # oxide-basis adapter
│       │   │   └── registry.py        # target registry (drives GUI lists)
│       │   └── systems/
│       │       ├── iron.py            # iron redox system
│       │       ├── carbon.py          # carbon redox system
│       │       └── sulfur.py          # sulfur redox system
│       ├── ui/
│       │   ├── main_window.py         # Qt main window
│       │   └── settings_dialog.py     # export target + template selection
│       ├── utils/
│       │   ├── constants.py           # atomic / molecular masses
│       │   └── aliases.py             # input alias registry
│       └── assets/                    # default template + GUI icons (packaged data)
├── docs/
│   ├── calculations.md        # mathematical reference
│   ├── data_dictionary.md     # full input-key reference
│   └── manual.md              # worked example / user manual
├── examples/                  # example inputs and expected outputs
└── tests/                     # unit + golden-fixture regression tests
```

---

## Governing equations

Equations and methodology: [`docs/calculations.md`](docs/calculations.md).

---

## License

ThermoChemX — Copyright (C) 2026 Michał Bukała

Released under the GNU General Public License, version 3 or later — see
[`LICENSE.txt`](LICENSE.txt). This program is distributed in the hope that it will be
useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
