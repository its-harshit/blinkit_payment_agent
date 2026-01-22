import { z } from "zod";
import { readFile } from "node:fs/promises";
const ServerCfg = z.object({
    command: z.string().min(1),
    args: z.array(z.string()).optional(),
    env: z.record(z.string()).optional()
});
const McpConfig = z.object({
    servers: z.record(ServerCfg)
});
export async function loadMcpConfig(path = "mcp_tools/mcp.config.json") {
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw);
    return McpConfig.parse(parsed);
}
