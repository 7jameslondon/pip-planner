# PIP Planner

PIP Planner is a local CLI and web UI for turning a DNA target sequence into a pyrrole-imidazole polyamide design candidate. It writes SVG and 3D model files for every design:

- `*-schematic.svg`: a planning schematic with the DNA target, complement, recognition pairs, and chain code.
- `*-chemical.svg`: an RDKit-generated 2D chemical structure drawing from a molecular graph with Py/Im/Hp monomers, amide linkages, hairpin turns, and terminal groups.
- `*-complex-model.pdb`: an initial modeled DNA duplex plus polyamide pose.
- `*-complex-viewer.html`: a standalone local 3D viewer for the modeled complex.
- `*-md-protocol.md`: MD setup notes and local engine status.

The web UI calls the CLI for every design request. The CLI is the source of truth.

## Dependency

Chemical SVG rendering uses [RDKit](https://www.rdkit.org/), and aqueous solubility estimates use ADMET-AI v2 and SolTranNet. Install the project dependencies with:

```powershell
python -m pip install -e .
```

These model outputs are planning estimates for the RDKit-generated SMILES, not experimentally validated PIP solubility.

The 3D complex output is an initial modeled pose and MD setup artifact. It is not a production MD trajectory unless you separately run and validate a supported Amber/OpenMM workflow.

## Recognition Code

Input DNA is read as the 5' to 3' target strand. The default A/T mode uses Hp to distinguish A-T from T-A:

| DNA base pair | PIP pair |
| --- | --- |
| G-C | Im/Py |
| C-G | Py/Im |
| A-T | Py/Hp |
| T-A | Hp/Py |

This follows the common Dervan-style PIP recognition code described in White et al., *Nature* 1998, DOI: [10.1038/35106](https://doi.org/10.1038/35106).

## Quick Start

Install Node/Electron dependencies:

```powershell
pnpm install
```

Run a CLI design:

```powershell
python -m pip_planner design GTAC --out output/demo
```

The `design` subcommand is optional for quick use:

```powershell
python -m pip_planner GTAC --out output/demo
```

Generate machine-readable JSON:

```powershell
python -m pip_planner design GTAC --out output/demo --format json
```

Count exact occurrences in a local reference genome:

```powershell
python -m pip_planner design ATGC --genome human-grch38 --out output/demo --format json
```

List genome references and install/import local FASTA files:

```powershell
python -m pip_planner genomes list
python -m pip_planner genomes download ce11
python -m pip_planner genomes import C:\path\to\reference.fa.gz --label "My reference"
```

Run the local web UI:

```powershell
python -m pip_planner.web --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

The UI updates automatically when the DNA sequence or design options change. It requests generated products separately: the schematic starts first, then the chemical structure, then solubility, genome occurrence search, and the 3D model. Fast updates replace the output directly; slower pending products show a loading state after a short threshold. Genome search defaults to bundled `sacCer3`; use the settings button inside the Genome search tab to select, download, or import references.

Run the native Windows desktop UI:

```powershell
pnpm desktop
```

The Electron desktop app starts the same local Python UI server internally, then opens it in a native window.

For day-to-day development on Windows, use the root development launcher:

```powershell
pnpm dev:launcher
```

That creates `PIP Planner Dev.exe` in the project root. Double-click it to run the current source tree through Electron without packaging or rebuilding the app. You only need to regenerate this launcher if the launcher source changes.

## Local Genome Occurrence Search

PIP Planner can count exact occurrences of the input DNA sequence against a real local reference FASTA and, when there are fewer than 100 occurrences, list the matching locations with overlaps from local annotation files. It searches the target sequence and its reverse complement, except palindromic targets are counted once per physical genomic site.

PIP Planner bundles the small Saccharomyces cerevisiae `sacCer3` FASTA so genome search works immediately and the test harness has a real reference. Larger public references are listed in the UI with a download button, then become selectable after download. Custom FASTA files can be added with the UI's `Other...` button or with `python -m pip_planner genomes import`.

Human and mouse references are not bundled because they are hundreds of megabytes to nearly a gigabyte each. HeLa is not listed as a built-in reference because whole-genome datasets are controlled-access and users need to supply their own authorized local FASTA if they have one.

Downloaded and imported genome files are stored under `data/genomes` in a source checkout, under the configured `PIP_PLANNER_GENOME_DIR` when that environment variable is set, or under the app's writable user-data genome directory in packaged desktop builds.

Default layout:

```text
data/genomes/
  sacCer3/
    genome.fa.gz
  human-grch38/
    genome.fa.gz
    annotations.gff3.gz
  custom-reference/
    genome.fa.gz
```

You can also create `data/genomes/genomes.json` to define the selectable genomes:

```json
{
  "genomes": [
    {
      "id": "human-grch38",
      "label": "Human GRCh38.p14",
      "fasta": "human-grch38/genome.fa.gz",
      "annotations": [
        "human-grch38/gencode.gff3.gz",
        "human-grch38/regulatory-elements.bed.gz",
        "human-grch38/repeats.bed.gz"
      ]
    },
    {
      "id": "custom-reference",
      "label": "Custom local reference",
      "fasta": "custom-reference/genome.fa.gz"
    }
  ]
}
```

Annotations may be GFF3, GTF, BED, or gzipped versions of those formats. Any overlapping annotation record can appear in the location table, so gene annotations, exons, regulatory tracks, repeats, CpG islands, and other DNA feature tracks can be included by adding them to the manifest.

Useful data sources:

- Bundled yeast reference: UCSC `sacCer3`.
- Optional public downloads: UCSC `ce11`, `dm6`, `hg38`, and `mm39` FASTA files.
- Human gene annotations: GENCODE GFF3/GTF for GRCh38.
- HeLa and other controlled/private references: import a local FASTA that you are authorized to use.

## 3D Complex And MD Artifacts

Every design also writes a local initial 3D model of a B-DNA duplex and the designed polyamide positioned in the minor groove. The web UI shows this in the `3D model` tab and offers a PDB download.

Generated model files:

```text
*-complex-model.pdb
*-complex-model.json
*-complex-viewer.html
*-md-protocol.md
```

The PDB/viewer are useful for planning and visual inspection, but the model is not a validated MD result. The JSON includes `model_3d.md_simulation.status`; it will report `not_run` when Amber/OpenMM tooling is not detected. The protocol notes follow this intended production setup:

- DNA force field: AMBER DNA.OL24.
- Binder force field: GAFF2 with reviewed Py/Im polyamide atom types, protonation/tautomer state, total charge, and torsions.
- Charges: RESP-style QM charges or a validated AmberTools GAFF2 charge workflow for final work.
- Water/ions: OPC or a carefully matched TIP4P-Ew/TIP3P water and ion parameter set.
- Engine: Amber `pmemd.cuda` preferred; OpenMM or GROMACS are acceptable only with careful AMBER topology conversion.
- Sampling: multiple independent replicas, hundreds of ns each, ideally microsecond-scale for groove adaptation, pose stability, or selectivity claims.
- Affinity: use alchemical free energy or restrained PMF/umbrella sampling for quantitative binding. MM-PBSA is only a rough screen.

## Building The Windows Executable

Build the desktop app:

```powershell
pnpm build
```

The build workflow does two things:

- `python scripts/build_backend.py` bundles the Python/RDKit server into `dist/backend/pip-planner-web/pip-planner-web.exe`.
- `python scripts/build_desktop.py` packages Electron and the backend into `release/`.

Each build is copied into a timestamped folder under `release/`, and `release/LATEST.txt` points to the newest one. The build produces a single-file portable executable plus an unpacked development copy:

- `release/build-YYYYMMDD-HHMMSS/PIP Planner.exe`: single-file portable executable. It contains the native splash and an embedded Electron app payload, so it can be copied and run by itself. The splash target is under 0.5 seconds.
- `release/build-YYYYMMDD-HHMMSS/win-unpacked/PIP Planner.exe`: direct Electron executable, useful for development and debugging.

On first launch, the portable executable shows the native splash first, then extracts its embedded app payload to a per-build cache under the user profile and opens the real UI. Later launches reuse that cache. The `win-unpacked` folder is kept only so development smoke tests and debugging can run the Electron app directly.

Build outputs are generated artifacts and are ignored by git.

## CLI Options

```powershell
python -m pip_planner design <DNA> `
  --architecture hairpin `
  --at-mode distinguish `
  --tail dp `
  --turn gamma `
  --out output/designs
```

Useful options:

- `--architecture hairpin|linear`: render a hairpin or linear planning structure.
- `--at-mode distinguish|py-py`: use Hp for A/T orientation or use Py/Py for degenerate A/T recognition.
- `--tail dp|none`: include or omit the Dp terminal group.
- `--turn gamma|beta|none`: label the hairpin turn.
- `--genome <id>`: scan a configured local reference genome for exact occurrences. Use `python -m pip_planner genomes list` to see ids.
- `--genome-location-threshold 100`: list locations only when the occurrence count is below this value.
- `--product all|schematic|chemical|solubility|genome|model`: generate everything or one product for incremental UI updates.
- `--format text|json`: choose human-readable output or JSON.

Example:

```powershell
python -m pip_planner design ATGC --architecture linear --at-mode py-py --tail none --out output/linear-demo
```

## Testing

Run the unit/API suite:

```powershell
python -m unittest discover
```

Run the CLI as a user would:

```powershell
python scripts/run_cli_harness.py
```

Run the real browser UI harness:

```powershell
python scripts/run_ui_browser_harness.py
```

The browser harness starts the local UI, drives Chrome/Chromium with Playwright when available, types DNA into the form, switches options, verifies the rendered SVG, and writes a screenshot to `output/playwright/pip-planner-ui.png`.

Run the Electron server harness:

```powershell
pnpm test:electron-server
```

Run the native Electron smoke harness:

```powershell
pnpm test:electron-smoke
```

Run the splash startup timing harness:

```powershell
pnpm test:splash-timing
```

After building, test the packaged executable:

```powershell
pnpm test:packaged
```

## Notes And Limits

PIP Planner generates design candidates. It does not predict binding affinity, selectivity, synthesis feasibility, uptake, toxicity, or biological effect.

The chemical SVG is generated by RDKit from a constructed molecular graph, and the CLI JSON includes `chemical_renderer` and `chemical_smiles`. Use it for planning and communication, then confirm final cap/linker choices with a chemist or synthesis provider before ordering material.
