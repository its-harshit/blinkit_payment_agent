#!/usr/bin/env node
// Demo script: buy a few Blinkit items and pay via the payment MCP (UPI).
import { spawn } from "node:child_process";
import * as readline from "node:readline";
import crypto from "node:crypto";

class McpClient {
  constructor(name, command, args) {
    this.name = name;
    this.child = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"] });
    this.pending = new Map();
    this.nextId = 1;

    const rl = readline.createInterface({ input: this.child.stdout });
    rl.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let msg;
      try {
        msg = JSON.parse(trimmed);
      } catch {
        return;
      }
      if (msg.jsonrpc !== "2.0") return;
      if (msg.id === null || msg.id === undefined) return;
      const handler = this.pending.get(msg.id);
      if (handler) {
        this.pending.delete(msg.id);
        handler.resolve(msg);
      }
    });

    this.child.stderr.on("data", (buf) => {
      // surface stderr for visibility
      process.stderr.write(`[${this.name} stderr] ${buf}`);
    });
  }

  async request(method, params) {
    const id = this.nextId++;
    const req = { jsonrpc: "2.0", id, method, params };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.child.stdin.write(JSON.stringify(req) + "\n");
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`Request ${id} timed out`));
        }
      }, 5000);
    }).then((msg) => {
      if (msg.error) throw new Error(msg.error.message);
      return msg.result;
    });
  }

  async initialize() {
    await this.request("initialize", { clientInfo: { name: "buyer-script", version: "0.1.0" }, capabilities: {} });
  }

  async listTools() {
    return this.request("tools/list");
  }

  async callTool(name, args) {
    return this.request("tools/call", { name, arguments: args });
  }

  close() {
    this.child.kill();
  }
}

async function buyFromBlinkit() {
  const blinkit = new McpClient("blinkit", "node", ["dist/blinkit-server.js"]);
  try {
    await blinkit.initialize();
    await blinkit.listTools();

    // Choose a small cart
    const cartItems = [
      { id: "blk-001", quantity: 2 }, // milk
      { id: "blk-029", quantity: 1 }, // basmati rice 1kg
      { id: "blk-035", quantity: 1 }, // cumin seeds
      { id: "blk-071", quantity: 2 } // Kurkure
    ];

    for (const item of cartItems) {
      await blinkit.callTool("blinkit.add_to_cart", item);
    }

    const cartResp = await blinkit.callTool("blinkit.cart", {});
    const cart = JSON.parse(cartResp.content[0].text);
    return { blinkit, cart };
  } catch (err) {
    blinkit.close();
    throw err;
  }
}

async function payForOrder(total, orderId) {
  const payment = new McpClient("payment", "node", ["dist/payment-server.js"]);
  try {
    await payment.initialize();
    await payment.listTools();

    const initResp = await payment.callTool("payment.init", {
      orderId,
      amount: total
    });
    const init = JSON.parse(initResp.content[0].text);

    const statusResp = await payment.callTool("payment.status", { paymentId: init.paymentId });
    const status = JSON.parse(statusResp.content[0].text);
    return { payment, init, status };
  } catch (err) {
    payment.close();
    throw err;
  }
}

async function main() {
  console.log("🛒 Building cart on Blinkit MCP...");
  const { blinkit, cart } = await buyFromBlinkit();
  console.log("Cart items:", cart.items);
  console.log("Cart total: ₹" + cart.total);

  const orderId = "ord_" + crypto.randomUUID().slice(0, 8);
  console.log("\n💳 Paying via Payment MCP (UPI)...");
  const { payment, init, status } = await payForOrder(cart.total, orderId);

  console.log("\nPayment intent:");
  console.log(init);
  console.log("\nPayment final status:");
  console.log(status);

  blinkit.close();
  payment.close();
  console.log("\n✅ Purchase flow completed");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});

