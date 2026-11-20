import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const sourcePath = fileURLToPath(new URL("./entry.png", import.meta.url));
const outputDirectory = process.env.MAKEFUN_OUTPUT_DIR ?? "/output";

if (!existsSync(sourcePath)) {
  console.error("entry.png is missing next to main.ts");
  process.exit(1);
}

if (!existsSync(outputDirectory)) {
  mkdirSync(outputDirectory, { recursive: true });
}

copyFileSync(sourcePath, join(outputDirectory, "entry.png"));
