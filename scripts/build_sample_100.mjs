import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const sourcePath = path.join(root, "templates", "sample_100_records.json");
const outputPath = path.join(root, "templates", "przykladowy_plik_100_rekordow_leadseason.xlsx");
const previewPath = path.join(root, "templates", "przykladowy_plik_100_rekordow_leadseason.png");

const rows = JSON.parse(await fs.readFile(sourcePath, "utf8"));

const columns = [
  "id",
  "detail_id",
  "nip",
  "domain",
  "company",
  "service",
  "account_owner",
  "publication_code",
  "seo_basket",
  "access_type",
  "start_date",
  "end_date",
  "monthly_value",
];

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("leadseason_upload");
sheet.showGridLines = false;

sheet.getRange("A1:M1").values = [columns];
sheet.getRange("A2:M101").values = rows.map((row) =>
  columns.map((column) => {
    const value = row[column] ?? "";
    if (["id", "detail_id", "nip"].includes(column)) return String(value);
    return value;
  }),
);

sheet.getRange("A1:M1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRange("A1:M101").format.borders = {
  insideHorizontal: { style: "thin", color: "#D8DEE9" },
  bottom: { style: "thin", color: "#94A3B8" },
};
sheet.getRange("A1:M101").format.autofitColumns();
sheet.getRange("A1:M1").format.rowHeight = 24;
sheet.getRange("A2:M101").format.rowHeight = 20;
sheet.getRange("A:C").format.numberFormat = "@";
sheet.getRange("K:L").format.numberFormat = "yyyy-mm-dd";
sheet.freezePanes.freezeRows(1);

const guide = workbook.worksheets.add("instrukcja");
guide.showGridLines = false;
guide.getRange("A1:D1").merge();
guide.getRange("A1").values = [["LeadSeason - przykładowy plik 100 rekordów"]];
guide.getRange("A1").format = {
  fill: "#0F172A",
  font: { bold: true, color: "#FFFFFF", size: 14 },
};
guide.getRange("A3:D8").values = [
  ["Pole", "Wymagane", "Opis", "Przykład"],
  ["id", "tak", "ID klienta z CRM/źródła", "748024411"],
  ["detail_id", "tak", "ID umowy / druk / detal", "7106139"],
  ["nip", "tak", "NIP bez spacji i myślników; traktowany jako tekst", "1111111111"],
  ["domain", "tak", "Domena lub adres URL; aplikacja sama normalizuje zapis", "example-hvac.pl"],
  ["company", "nie", "Nazwa firmy, jeżeli jest dostępna", "AP-Pol Porcelana24"],
];
guide.getRange("A3:D3").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
guide.getRange("A3:D8").format.borders = {
  insideHorizontal: { style: "thin", color: "#CBD5E1" },
  bottom: { style: "thin", color: "#94A3B8" },
};
guide.getRange("A:D").format.autofitColumns();
guide.freezePanes.freezeRows(3);

const preview = await workbook.render({
  sheetName: "leadseason_upload",
  range: "A1:M18",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(outputPath);
