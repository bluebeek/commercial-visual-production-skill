# Commercial Visual Production Skill V3.1.0

[简体中文](README.md) · [Validation](VALIDATION.md) · [Release notes](CHANGELOG.md)

A traceable workflow connecting reference analysis, project brand translation, creative blueprints, image production, review, targeted repairs, and PNG/ORA delivery. It is designed for assistant environments with local Skills, file access, Python, and the built-in image-generation tool. Project files retain active requirements, assets, version ancestry, issues, and user decisions. A resumed conversation reloads that state instead of relying on the model to remember the entire chat.

Skill name: `commercial-visual-production-v3-1-0`. Package version: **3.1.0**. The package combines assistant instructions, project-state programs, verification tools, and a local review workbench. Visual interpretation and image-tool execution require an assistant.

V3.1 adds PhotoCraft bounded rectangle editing and mandatory candidate-bound engine roundtrip checks for new projects. Image generation remains separate; this development stage uses zero real image-generation calls. See [the versioned report](validation/v3.1/REPORT.md) and [PhotoCraft contract](skills/commercial-visual-production-v3-1-0/references/photocraft.md). GUI, live text and broader editor behavior remain unverified.

## Scope

Use it for individual commercial posters, brand campaign visuals, e-commerce or social graphics, and successive revisions that must preserve earlier accepted changes. Choose whole-image candidates or layered production per project. Where fidelity matters, preserve real product, person, or logo originals and exact copy through source compositing or separate rasterized text layers.

Capabilities include:

- Nine-module reference analysis with evidence, estimates, and unknowns kept distinct.
- Adoption, adaptation, or rejection of reference features against actual brand assets, use, and guidelines. Unadopted reference content must not enter production.
- Text, sketch, or mixed creative input translated into a blueprint, layout, final copy, protected objects, and a structural preview.
- Four image-task types: background, standalone asset, whole image, and local edit. Applicable negative constraints are included in the actual prompt.
- Successive revisions based on current requirements, an explicitly selected baseline, and the present change, with provenance, ordered attachments, hashes, and parent versions.
- RGBA pixel protection outside local edit regions, separate seam and goal reviews, defect tracking, and acceptance tied to a specific candidate.
- Export and independent readback of PNG/ORA with layer order, transparency, and recomposition checks.

This is not an unattended design service, native PSD/vector/live-text editor, automatic identity-recognition or OCR system, or a print-proofing/spot-color certification tool. Raw model output may make unintended changes. Source originals, selections, compositing, and verification control the adopted result. See [VALIDATION.md](VALIDATION.md) for measured coverage and limits.

## Requirements and installation

Scripts require Python 3.10+ with Pillow and NumPy. SciPy is optional; inner feathering has a Pillow fallback. Image generation requires the current conversation to expose the built-in `image_gen.imagegen` tool. This preferred path does not require an external API key. Installing the repository into an ordinary Python or web environment does not provide that tool.

1. Download or clone this repository.
2. Copy the entire `skills/commercial-visual-production-v3-1-0` directory into `$CODEX_HOME/skills/`. If that variable is unset, the usual location is `~/.codex/skills/`.
3. Install runtime dependencies into the Python environment used for this Skill: `python -m pip install -r requirements.txt`.
4. Start a new conversation and invoke `$commercial-visual-production-v3-1-0`. Archive older production skills outside the install directory after validating the new copy; keep the separate QC skill unchanged.

A compatible Skill installer can also install the repository path `skills/commercial-visual-production-v3-1-0`. Script CI coverage and actual PhotoCraft engine coverage are reported separately.

Suggested first request:

> Use $commercial-visual-production-v3-1-0 to take this project through reference analysis, brand translation, a blueprint, and visual production. Read the supplied references and brand assets first, and ask only for missing essentials. Have me confirm the blueprint before generation, restrict revisions to the requested scope, and deliver PNG and ORA.

Users do not need to author internal JSON. The assistant builds project records from actual supplied materials and instructions, asking only about gaps that affect execution.

## What to provide

- Reference images and each image role: style, layout, material, or another specific purpose.
- Logos, product or person originals, brand visual files, and assets whose use rights the project owner has established.
- Intended use, canvas ratio or dimensions, brand guidelines, exact copy, required content, and prohibitions.
- Creative text, a sketch, or both. Before R3, provide asset descriptions and poster-specific considerations; information already supplied is inherited.
- For revisions, an identifiable baseline. Clarification is needed only when multiple candidates make the reference ambiguous.

## Production and delivery workflow

| Stage | Inputs and execution | Outputs and gate |
| --- | --- | --- |
| R0 Reference analysis | Inspect actual reference images across visual style, composition/layout, asset treatment, color, typography/text, lighting/material, spatial relationships, graphics/decoration, and the integrated visual mechanism | Evidence-based observations, estimates, and unknowns; no project blueprint is produced here |
| R1 Brand translation | Read R0, actual brand assets, intended use, and guidelines; adopt, adapt, or reject each observation with source, scope, and replacement records | Current project brand requirements; reference brands, people, and copy do not automatically become project content |
| R2 Creative blueprint | Receive text, sketch, or mixed input; define layout, hierarchy, copy, originals, protected content, and a structural preview | An executable blueprint; resolve critical conflicts and obtain user confirmation for that specific blueprint version |
| R3 Production | Consume valid R1/R2, asset descriptions, and project notes; select whole-image or layered production, compile the task, and verify actual inputs | Actual raw output, an adopted candidate, invocation evidence, layer updates, and hashes; compilation or queuing is not generation |
| R4 Verification | Inspect the actual candidate against current requirements, originals, and blueprint; run applicable checks and record assistant visual observations | A version-bound report and P0/P1/P2 defects; unknown is not a pass |
| R5 Repair and freeze | Create a minimal task from an explicit baseline, return to R3, then R4; check the current goal, prior changes, and non-target regions | A verified and user-accepted candidate can become the frozen master; no artificial repair round is required when no defect exists |
| R6 Delivery acceptance | Export from a valid frozen master; reread PNG/ORA and check dimensions, layer order, transparency, hashes, and recomposition | PNG, raster ORA, source layers, and reports; final user acceptance identifies the actual delivery version |

User decisions normally occur at three checkpoints: **blueprint confirmation, candidate acceptance, and delivery acceptance**. An explicit new revision request already authorizes that scope. Ask again only for actual conflicts, missing essentials, or ambiguous version references. Machine results, assistant observations, and user decisions remain separate records. Local decision records are declarations, not authenticated signatures.

## How R3 preserves intent

Every invocation reconstructs the information needed now: task and purpose → actual image roles → hierarchy and relative placement → active requirements and exact content → current change and prior results to preserve → project considerations and built-in negative constraints → output and acceptance conditions. The image model does not need to understand internal R0–R6 identifiers.

Execution checks block relevant tasks with stale rules, an unclear baseline, missing or misordered attachments, an unconfirmed blueprint, unresolved critical conflicts, or undefined local scope. The assistant handles semantic interpretation, deduplication, and real visual judgment. Structural validation is not semantic understanding. Persistent requirements live in project records, not temporary task notes.

The actual AI entry point is built-in `image_gen.imagegen`. Users may call it ChatGPT Image 2.5, but the public tool does not expose backend model selection, so this package cannot verify that particular model version. Negative constraints are included in the real `prompt`; no invented `negative_prompt`, seed, CFG, steps, or mask API is used. Generic prohibitions must not erase explicitly requested grain, brushwork, or other intentional effects.

## Successive revisions and minimal changes

Each round binds a parent version, active requirements, requested differences, editable regions, transition regions, protected regions, and actual inputs/outputs. Working and accepted versions are distinct. New candidates do not silently replace accepted versions; continuing from an older version preserves other branches. New requirements replace only the affected scope/property, and rejected requirements cannot re-enter production.

Prefer deterministic fixes to source raster text, original layers, or compositing parameters before making another image call. Local hard locking requires matching dimensions and alignment; RGBA pixels outside the edit region must equal the baseline exactly. Mismatches stop the operation rather than being silently resized. Goal completion, natural seams, and retention of earlier changes still require separate review.

Repair layers are traceable raster patches, not reconstructed semantic backgrounds or native editable objects. Detailed coordinates stay in the composition plan, while prompts use concise spatial language. Full evidence remains in project files; resumed sessions reload authoritative state. Fewer prompt characters are not a measured equivalent reduction in billed tokens.

## Review buttons and defect loop

The local workbench exposes inherited requirements and sources, real check execution, report reading, user decisions, issue submission, targeted repair tasks, repair review submission, version comparison, and selection of an older baseline. Running checks creates a report; viewing a report reads it and checks freshness. Production buttons only register `waiting_execution`; the assistant in the current conversation must invoke the image tool.

Defects progress from open → fixing → ready for review → verified closed. Failed checks or invalidated evidence require renewed handling. P0/P1 defects, critical unknowns, and missing mandatory evidence block freezing. A specific noncritical P2 may remain only through explicit user acceptance for that version; acceptance does not mean fixed.

## Deliverables and acceptance

| Deliverable | Meaning |
| --- | --- |
| `merged_preview.png` | Final raster composite exported from the accepted master |
| `layout_layers.ora` | A flat src-over layer stack preserving raster sources and patches; not an editable PSD |
| Source layers and composition specification | Actual files, placement, and layer provenance required for recomposition |
| Verification and difference reports | Checks actually run, non-target/protected-region comparisons, and known limits |
| Project state and version evidence | Active requirements, ancestry, tasks, issues, and acceptance/delivery decisions |

Project material remains in the project directory. The project owner chooses whether to share history, originals, or internal evidence with a client. The displayed final candidate, reviewed image, and exported master must identify the same valid version. Opening compatibility in a target design application must be tested separately; untested software is not declared compatible.

## Scripts, workbench, and tests

The assistant normally runs these commands. From `skills/commercial-visual-production-v3-1-0`:

```sh
python scripts/workflow.py init --project <project-directory> --project-id <project-id> --call-budget 4
python scripts/stage_context.py build --project <project-directory> --stage R3
python scripts/start_review.py --project <project-directory> --port 8765
python -m unittest discover -s tests -q
```

Run compatibility tests in a separate process and directory to avoid importing old modules into the new workflow:

```sh
cd compat/v2
python -m unittest discover -s tests -q
```

The detailed internal contracts currently remain in Chinese: [stage rules](skills/commercial-visual-production-v3-1-0/references/stages.md), [production rules](skills/commercial-visual-production-v3-1-0/references/execution.md), and [review/delivery rules](skills/commercial-visual-production-v3-1-0/references/review-delivery.md). The assistant can explain them in the user language. The workbench UI is not advertised as fully localized.

## Versions and migration

V3 project state uses `cvisual.workflow.v3`. Reused audit tools retain `cvisual.audit.v2` and `tool_version=2.2.0`; these independent report-protocol versions do not indicate an old package installation.

Legacy reference decoding maps to R0; brand assets/use to R1; blueprint/preview to R2; production/protection to R3/R5; quality review to R4; delivery checks to R6. Migration defaults to a preview and writes an applied migration into a new directory, leaving the original untouched. Old approvals are not imported as new user approvals, and a submitted repair is not a verified closure.

## Validation overview and license

The release passed 54 V3 tests and a separate 70-test legacy compatibility suite. One controlled layered poster completed four real image invocations and three successive revisions. Final protected regions and the last edit non-target region had zero pixel changes, and the eight-layer PNG/ORA recomposition matched the test master. See [VALIDATION.md](VALIDATION.md) for boundaries and untested scenarios.

This repository is distributed under the [MIT License](LICENSE), allowing use, modification, redistribution, and commercial use while retaining the copyright and license notice. Third-party dependencies and user-provided assets retain their own licenses.
