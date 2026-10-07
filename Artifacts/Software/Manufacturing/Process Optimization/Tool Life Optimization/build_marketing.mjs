import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const workspaceDir = path.resolve(process.cwd());
const skillDir = "C:/Users/arvasis/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations";
const runtimeNodeModules = "C:/Users/arvasis/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const runtimePython = "C:/Users/arvasis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe";
const { Presentation, PresentationFile } = await import(pathToFileURL(
  path.join(runtimeNodeModules, "@oai/artifact-tool/dist/artifact_tool.mjs"),
).href);
const tmpDir = path.join(workspaceDir, ".slide_build");
const outputDir = path.join(workspaceDir, "outputs");
const candidatePath = path.join(tmpDir, "candidate.pptx");
const finalPath = path.join(outputDir, "Tool_Life_Optimizer_Marketing.pptx");
await fs.mkdir(tmpDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });

const { resolvePresentationFont, applyPresentationChartFont, finalizePresentation } = await import(
  pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href,
);
const family = resolvePresentationFont({ availableFonts: ["Aptos", "Arial", "Segoe UI"] });
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const slide = presentation.slides.add();
slide.background.fill = "#F5F8FA";

function textbox({ left, top, width, height, text, size = 20, color = "#182C3D", bold = false, align = "left", italic = false }) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left, top, width, height },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = { typeface: family, fontSize: size, color, bold, italic, align, autoFit: "shrinkText" };
  return shape;
}

// Left editorial column
textbox({ left: 66, top: 48, width: 730, height: 25, text: "MACHINING ECONOMICS", size: 14, color: "#087F83", bold: true });
textbox({ left: 66, top: 82, width: 730, height: 100,
  text: "Cutting speed and tool life,\nplanned around demand", size: 36, color: "#182C3D", bold: true });
textbox({ left: 66, top: 198, width: 640, height: 60,
  text: "A focused decision aid for manufacturing teams balancing wear, capacity and finite-batch economics.", size: 18, color: "#4E6271" });

textbox({ left: 66, top: 306, width: 600, height: 30, text: "What planners can evaluate", size: 18, color: "#182C3D", bold: true });
textbox({ left: 66, top: 350, width: 640, height: 155,
  text: "TURNING + MILLING\nSeparate fixed-condition operating modes with independent tool-life calibration\n\nDEMAND + CAPACITY\nFinite-batch tooling, machine limits and available-time feasibility\n\nDECISION RECORD\nBaseline comparison, search trace and JSON / CSV export", size: 16, color: "#314B5B" });

textbox({ left: 66, top: 600, width: 650, height: 40,
  text: "Best feasible grid point found by deterministic multistart hill climbing", size: 14, color: "#087F83", bold: true });
textbox({ left: 66, top: 658, width: 640, height: 24,
  text: "Illustrative profile shown. Calibrate with measured or supplier-specific data before production use.", size: 11, color: "#657583", italic: true });

// Right native chart, intentionally illustrative and free of pricing.
const speeds = [60, 90, 120, 150, 180, 210, 240, 270, 300];
const life = speeds.map((v) => Number((30 * Math.pow(180 / v, 1 / 0.25)).toFixed(2)));
const chart = slide.charts.add("line", {
  position: { left: 760, top: 72, width: 450, height: 430 },
  categories: speeds.map(String),
  series: [{ name: "Illustrative tool life", values: life, fill: "#087F83" }],
  hasLegend: false,
  dataLabels: { showValue: false },
});
applyPresentationChartFont(chart, { fontFamily: family });

textbox({ left: 785, top: 528, width: 400, height: 25, text: "Illustrative tool-life profile", size: 15, color: "#182C3D", bold: true });
textbox({ left: 785, top: 558, width: 410, height: 68,
  text: "Higher cutting speed shortens modeled life. The optimizer weighs that trade-off against cycle time, edge / set changes and demand feasibility.", size: 14, color: "#4E6271" });
textbox({ left: 785, top: 646, width: 410, height: 22,
  text: "Turning and milling use separate calibration profiles.", size: 11, color: "#087F83", bold: true });

slide.speakerNotes.textFrame.setText(`Marketing slide for Tool Life Optimizer.\n\nFeature claims are limited to the implemented local Python application: turning and milling modes, fixed-condition Taylor life profiles, finite-batch integer tooling, machine and available-time constraints, deterministic bounded multistart hill climbing, baseline comparison, saved scenarios and JSON/CSV run exports. The result is the best feasible grid point found; it is not a global-optimum claim.\n\nThe chart is an illustrative synthetic turning profile from the app demonstration inputs (vref 180 m/min, life 30 cutting minutes, Taylor exponent 0.25). It is not a supplier recommendation or measured production result.\n\nResearch sources:\n- Sandvik Coromant turning formulas: https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/general-turning-formulas-definitions\n- Sandvik Coromant milling formulas: https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/milling-formulas-definitions\n- Sandvik workpiece materials: https://www.sandvik.coromant.com/en-gb/knowledge/materials/workpiece-materials\n- Autodesk Fusion Tool Library UI: https://help.autodesk.com/cloudhelp/ENU/Fusion-CAM/files/MFG-TOOL-LIBRARY-OVERVIEW.htm\n- Siemens NX manufacturing planning UI: https://blogs.sw.siemens.com/designcenter/whats-new-june-2024-manufacturing-planning/`);

await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const preview = await presentation.export({ slide, format: "png", scale: 1 });
await fs.writeFile(path.join(tmpDir, "slide-1.png"), new Uint8Array(await preview.arrayBuffer()));
const layout = await slide.export({ format: "layout" });
await fs.writeFile(path.join(tmpDir, "slide-1.layout.json"), await layout.text());

const result = await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable: runtimePython,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  requiredNativeTableOwnerSlides: [],
  fontPolicy: { basis: "design", families: [family] },
  verifyArtifactToolImport: true,
  materializeLiteralChartWorkbooks: true,
  receiptPath: path.join(tmpDir, "Tool_Life_Optimizer_Marketing.validation.json"),
  explicitTotalSlideCount: 1,
});
console.log(JSON.stringify({ finalPath, candidatePath, family, result }, null, 2));
