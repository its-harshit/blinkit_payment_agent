import "dotenv/config";
import * as readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { loadMcpConfig } from "./config.js";
import { McpStdioClient } from "./mcp/stdioClient.js";
function printHelp() {
    // eslint-disable-next-line no-console
    console.log([
        "",
        "Commands:",
        "  help                     Show this help",
        "  tools                    List tools",
        "  call <toolName> <json>    Call a tool with JSON args",
        "  exit                     Quit",
        "",
        "Examples:",
        '  tools',
        '  call blinkit.search {"query":"milk"}',
        ""
    ].join("\n"));
}
async function main() {
    const cfg = await loadMcpConfig();
    const serverName = Object.keys(cfg.servers)[0];
    if (!serverName)
        throw new Error("No servers configured in mcp.config.json");
    const server = cfg.servers[serverName];
    // eslint-disable-next-line no-console
    console.log(`Connecting to MCP server "${serverName}" via stdio: ${server.command} ${(server.args ?? []).join(" ")}`);
    const client = new McpStdioClient(server);
    await client.initialize();
    const rl = readline.createInterface({ input, output });
    printHelp();
    while (true) {
        const line = (await rl.question("> ")).trim();
        if (!line)
            continue;
        if (line === "exit" || line === "quit")
            break;
        if (line === "help") {
            printHelp();
            continue;
        }
        if (line === "tools") {
            const tools = await client.listTools();
            // eslint-disable-next-line no-console
            console.log(JSON.stringify(tools, null, 2));
            continue;
        }
        if (line.startsWith("call ")) {
            const rest = line.slice("call ".length).trim();
            const firstSpace = rest.indexOf(" ");
            if (firstSpace === -1) {
                // eslint-disable-next-line no-console
                console.log('Usage: call <toolName> <json>');
                continue;
            }
            const toolName = rest.slice(0, firstSpace).trim();
            const jsonStr = rest.slice(firstSpace + 1).trim();
            let args = {};
            try {
                args = jsonStr ? JSON.parse(jsonStr) : {};
            }
            catch (e) {
                // eslint-disable-next-line no-console
                console.log(`Invalid JSON: ${e.message}`);
                continue;
            }
            const result = await client.callTool(toolName, args);
            // eslint-disable-next-line no-console
            console.log(JSON.stringify(result, null, 2));
            continue;
        }
        // eslint-disable-next-line no-console
        console.log('Unknown command. Type "help".');
    }
    rl.close();
    client.close();
}
main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exitCode = 1;
});
