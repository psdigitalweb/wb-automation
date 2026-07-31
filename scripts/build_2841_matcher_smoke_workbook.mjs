import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repoRoot = "D:/Work/EcomCore";
const outputDir = path.join(repoRoot, "outputs", "seo_phase1_2841");
const outputPath = path.join(outputDir, "matcher_smoke_2841_queries.xlsx");
const smokePath = path.join(repoRoot, "tests/seo/phase1/category_2841/matcher_smoke_summary.json");

const smoke = JSON.parse(await fs.readFile(smokePath, "utf8"));
const runToSku = new Map(smoke.runs_brief.map((run) => [Number(run.matcher_run_id), Number(run.nm_id)]));
const selectedRuns = smoke.runs_brief.map((run) => Number(run.matcher_run_id));

const sql = `
select coalesce(json_agg(row_to_json(t)), '[]'::json)
from (
  select
    run_id,
    bucket,
    query_display,
    normalized_query_text,
    score::float as score,
    ranking_value_used::float as ranking_value_used
  from seo_matcher_results
  where run_id in (${selectedRuns.join(",")})
  order by
    run_id,
    case bucket
      when 'primary' then 1
      when 'secondary' then 2
      when 'broad' then 3
      when 'rejected' then 4
      else 5
    end,
    score desc,
    ranking_value_used desc nulls last,
    id
) t;
`;

const stdout = execFileSync(
  "docker",
  ["exec", "ecomcore-postgres-1", "psql", "-U", "wb", "-d", "wb", "-t", "-A", "-c", sql],
  { encoding: "utf8", cwd: repoRoot, maxBuffer: 64 * 1024 * 1024 },
);
const rows = JSON.parse(stdout.trim());

const buckets = ["primary", "secondary", "broad", "rejected"];
const bucketTitles = {
  primary: "Primary",
  secondary: "Secondary",
  broad: "Broad",
  rejected: "Rejected",
};

const grouped = new Map();
for (const runId of selectedRuns) {
  grouped.set(runId, { primary: [], secondary: [], broad: [], rejected: [] });
}
for (const row of rows) {
  const bucket = String(row.bucket || "");
  if (!grouped.has(Number(row.run_id)) || !buckets.includes(bucket)) continue;
  grouped.get(Number(row.run_id))[bucket].push(row.query_display || row.normalized_query_text || "");
}

const workbook = Workbook.create();

for (const [idx, runId] of selectedRuns.entries()) {
  const sku = runToSku.get(runId);
  const sheet = workbook.worksheets.add(`SKU_${sku}`);

  const data = grouped.get(runId);
  const maxRows = Math.max(...buckets.map((bucket) => data[bucket].length));
  const smokeRun = smoke.runs_brief.find((run) => Number(run.matcher_run_id) === runId);
  const counts = smokeRun.bucket_counts;

  sheet.getRange("A1:D1").values = [[`SKU ${sku} / matcher run ${runId}`, "", "", ""]];
  sheet.getRange("A2:D2").values = [[`Profile: ${smokeRun.category_profile_version}`, "", "", ""]];
  sheet.getRange("A3:D3").values = [[`Total results: ${smokeRun.result_count}`, "", "", ""]];
  sheet.getRange("A5:D5").values = [[
    `${bucketTitles.primary} (${counts.primary})`,
    `${bucketTitles.secondary} (${counts.secondary})`,
    `${bucketTitles.broad} (${counts.broad})`,
    `${bucketTitles.rejected} (${counts.rejected})`,
  ]];

  const matrix = [];
  for (let rowIndex = 0; rowIndex < maxRows; rowIndex += 1) {
    matrix.push(buckets.map((bucket) => data[bucket][rowIndex] || ""));
  }
  if (matrix.length > 0) {
    sheet.getRange(`A6:D${5 + matrix.length}`).values = matrix;
  }

  sheet.getRange("A1:D1").format = { font: { bold: true, size: 14 }, fill: { color: "#EAF2F8" } };
  sheet.getRange("A5:D5").format = { font: { bold: true }, fill: { color: "#D9EAD3" } };
  sheet.getRange(`A1:D${Math.max(6, 5 + matrix.length)}`).format = {
    wrapText: true,
    verticalAlignment: "top",
  };
  sheet.getRange("A:D").format.autofitColumns();
  sheet.getRange(`A1:D${Math.max(6, 5 + matrix.length)}`).format.autofitRows();
}

await fs.mkdir(outputDir, { recursive: true });

for (const runId of selectedRuns) {
  const sku = runToSku.get(runId);
  const sheetName = `SKU_${sku}`;
  await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:D12`,
    include: "values",
    tableMaxRows: 12,
    tableMaxCols: 4,
  });
}

await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
