import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = fileURLToPath(new URL("../", import.meta.url));
const brand = path.join(root, "public/brand");
await fs.mkdir(brand, { recursive: true });
const icon = await fs.readFile(path.join(brand, "radar-mark.svg"));

await sharp(icon).resize(96, 96).png().toFile(path.join(root, "public/favicon-96.png"));
await sharp(icon).resize(96, 96).png().toFile(path.join(brand, "radar-mark-96.png"));
await sharp(icon).resize(180, 180).png().toFile(path.join(brand, "radar-touch-icon.png"));

const sizes = [16, 32, 48, 256];
const frames = await Promise.all(sizes.map((size) => sharp(icon).resize(size, size).png().toBuffer()));
const header = Buffer.alloc(6 + sizes.length * 16);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
for (let i = 0; i < sizes.length; i += 1) {
  const entry = 6 + i * 16;
  header[entry] = sizes[i] === 256 ? 0 : sizes[i];
  header[entry + 1] = sizes[i] === 256 ? 0 : sizes[i];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(frames[i].length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += frames[i].length;
}
await fs.writeFile(path.join(root, "public/favicon.ico"), Buffer.concat([header, ...frames]));
await fs.writeFile(path.join(brand, "radar-mark.ico"), Buffer.concat([header, ...frames]));

const city = await sharp(path.join(root, "public/milano-hero.webp"))
  .resize(650, 630, { fit: "cover", position: "centre" })
  .toBuffer();
const mark = await sharp(icon).resize(60, 60).toBuffer();
const overlay = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="blend"><stop offset="0" stop-color="#17241e"/><stop offset=".4" stop-color="#17241e" stop-opacity=".9"/><stop offset="1" stop-color="#17241e" stop-opacity="0"/></linearGradient>
  </defs>
  <path fill="url(#blend)" d="M430 0h340v630H430z"/>
  <path d="M64 548h1072" stroke="#ffffff" stroke-opacity=".17"/>
  <text x="138" y="83" fill="#f5f4ee" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="bold" letter-spacing="-1">hackathon milano.</text>
  <text x="66" y="182" fill="#d9bc79" font-family="Arial, Helvetica, sans-serif" font-size="16" letter-spacing="3">TROVA LA TUA PROSSIMA SFIDA</text>
  <text x="60" y="284" fill="#f5f4ee" font-family="Arial, Helvetica, sans-serif" font-size="76" font-weight="bold" letter-spacing="-4">Le grandi idee</text>
  <text x="60" y="371" fill="#f5f4ee" font-family="Arial, Helvetica, sans-serif" font-size="76" font-weight="bold" letter-spacing="-4">iniziano <tspan fill="#ee9977" font-family="Georgia, serif" font-style="italic" font-weight="normal">qui.</tspan></text>
  <text x="65" y="441" fill="#c4cec6" font-family="Arial, Helvetica, sans-serif" font-size="23">Il radar degli hackathon a Milano e dintorni.</text>
  <text x="65" y="585" fill="#d8ded8" font-family="Arial, Helvetica, sans-serif" font-size="17">Esplora. Incontra. Costruisci.</text>
  <circle cx="1072" cy="579" r="5" fill="#f36a3d"/>
  <text x="1091" y="585" fill="#d8ded8" font-family="Arial, Helvetica, sans-serif" font-size="17">MILANO</text>
</svg>`);

await sharp({ create: { width: 1200, height: 630, channels: 4, background: "#17241e" } })
  .composite([{ input: city, top: 0, left: 550 }, { input: overlay }, { input: mark, top: 44, left: 63 }])
  .png({ palette: true, quality: 95 })
  .toFile(path.join(root, "app/opengraph-image.png"));

console.log("Brand assets generated: favicon, Apple icon and 1200×630 social card.");
