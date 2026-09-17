// Run from any directory after installing the optional renderer described in README.md.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const { Resvg } = require(path.join(root, ".tools/brand-render/node_modules/@resvg/resvg-js"));
const svg = fs.readFileSync(path.join(root, "web/public/icon.svg"), "utf8");
for (const [name, size] of [["favicon.png", 32], ["apple-touch-icon.png", 180], ["icon.png", 512]]) {
  const image = new Resvg(svg, {fitTo: {mode: "width", value: size}}).render().asPng();
  fs.writeFileSync(path.join(root, "web/public", name), image);
}
const preview = fs.readFileSync(path.join(__dirname, "social-preview.svg"), "utf8");
fs.writeFileSync(path.join(__dirname, "social-preview.png"), new Resvg(preview).render().asPng());
console.log("Rendered icon PNGs and 1280 × 640 social preview.");
