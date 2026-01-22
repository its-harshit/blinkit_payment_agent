import { spawn } from "node:child_process";
import * as readline from "node:readline";
import { isJsonRpcResponse } from "./jsonrpc.js";
export class McpStdioClient {
    nextId = 1;
    pending = new Map();
    child;
    constructor(cfg) {
        this.child = spawn(cfg.command, cfg.args ?? [], {
            stdio: ["pipe", "pipe", "pipe"],
            env: { ...process.env, ...(cfg.env ?? {}) }
        });
        const rl = readline.createInterface({ input: this.child.stdout });
        rl.on("line", (line) => {
            const trimmed = line.trim();
            if (!trimmed)
                return;
            let msg;
            try {
                msg = JSON.parse(trimmed);
            }
            catch {
                return; // ignore non-JSON output
            }
            if (!isJsonRpcResponse(msg))
                return;
            if (msg.id === null)
                return;
            const handler = this.pending.get(msg.id);
            if (!handler)
                return;
            this.pending.delete(msg.id);
            handler.resolve(msg);
        });
        this.child.stderr.on("data", (buf) => {
            // eslint-disable-next-line no-console
            console.error(String(buf));
        });
        this.child.on("exit", (code, signal) => {
            const err = new Error(`MCP server exited (code=${code}, signal=${signal ?? "none"})`);
            for (const [, handler] of this.pending)
                handler.reject(err);
            this.pending.clear();
        });
    }
    async request(method, params) {
        const id = this.nextId++;
        const req = { jsonrpc: "2.0", id, method, params };
        const raw = await new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.child.stdin.write(JSON.stringify(req) + "\n");
        });
        if ("error" in raw) {
            throw new Error(`RPC error ${raw.error.code}: ${raw.error.message}`);
        }
        return raw.result;
    }
    async initialize(clientName = "agentic-commerce-starter", clientVersion = "0.1.0") {
        // MCP servers generally support initialize with capabilities; we keep it minimal.
        await this.request("initialize", {
            clientInfo: { name: clientName, version: clientVersion },
            capabilities: {}
        });
    }
    async listTools() {
        return await this.request("tools/list");
    }
    async callTool(name, argumentsObj) {
        return await this.request("tools/call", { name, arguments: argumentsObj });
    }
    close() {
        this.child.kill();
    }
}
