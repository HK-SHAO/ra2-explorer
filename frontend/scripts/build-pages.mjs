import { existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { build } from "vite";

const output = resolve("dist-pages");
const data = resolve(output, "data");
const preserved = resolve(
  "..",
  ".runtime",
  "RA2MD-Ext",
  "pages",
  ".frontend-data-preserved",
);

let restoreData = false;
if (existsSync(preserved)) {
  if (existsSync(data)) {
    throw new Error(`Pages 数据同时存在于输出和暂存目录：${preserved}`);
  }
  restoreData = true;
  console.log("[pages] 恢复上次中断前暂存的静态数据");
} else if (existsSync(data)) {
  mkdirSync(dirname(preserved), { recursive: true });
  renameSync(data, preserved);
  restoreData = true;
  console.log("[pages] 暂存静态数据，跳过大量小文件清理");
}

try {
  await build({ mode: "pages" });
} finally {
  if (restoreData && existsSync(preserved)) {
    if (existsSync(data)) rmSync(data, { recursive: true, force: true });
    mkdirSync(output, { recursive: true });
    renameSync(preserved, data);
    console.log("[pages] 已恢复静态数据");
  }
}
