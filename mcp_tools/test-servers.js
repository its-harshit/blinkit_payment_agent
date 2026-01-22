#!/usr/bin/env node
// Test script to verify both Blinkit and Payment MCP servers
import { spawn } from "node:child_process";
import * as readline from "node:readline";

class TestClient {
  constructor(serverName, command, args) {
    this.serverName = serverName;
    this.child = spawn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: process.env
    });
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
      if (msg.jsonrpc === "2.0" && msg.id !== null && msg.id !== undefined) {
        const handler = this.pending.get(msg.id);
        if (handler) {
          this.pending.delete(msg.id);
          handler.resolve(msg);
        }
      }
    });
    this.child.stderr.on("data", (buf) => {
      // Ignore stderr for now
    });
  }

  async request(method, params) {
    const id = this.nextId++;
    const req = { jsonrpc: "2.0", id, method, params };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.child.stdin.write(JSON.stringify(req) + "\n");
      setTimeout(() => reject(new Error("Timeout")), 5000);
    }).then((msg) => {
      if (msg.error) {
        throw new Error(`RPC error: ${msg.error.message}`);
      }
      return msg.result;
    });
  }

  async initialize() {
    await this.request("initialize", {
      clientInfo: { name: "test-client", version: "0.1.0" },
      capabilities: {}
    });
  }

  async listTools() {
    return await this.request("tools/list");
  }

  async callTool(name, args) {
    return await this.request("tools/call", { name, arguments: args });
  }

  close() {
    this.child.kill();
  }
}

async function testBlinkit() {
  console.log("\n=== Testing Blinkit Server ===\n");
  const client = new TestClient("blinkit", "node", ["mcp_tools/dist/blinkit-server.js"]);
  
  try {
    await client.initialize();
    console.log("✓ Initialized");

    const tools = await client.listTools();
    console.log("✓ Tools listed:", tools.tools.map(t => t.name).join(", "));

    // Test search
    const searchResult = await client.callTool("blinkit.search", { query: "milk", limit: 3 });
    const searchData = JSON.parse(searchResult.content[0].text);
    console.log("✓ Search works:", searchData.length, "items found");

    // Test get item
    const itemResult = await client.callTool("blinkit.item", { id: "blk-001" });
    const itemData = JSON.parse(itemResult.content[0].text);
    console.log("✓ Get item works:", itemData.name);

    // Test add to cart
    const addResult = await client.callTool("blinkit.add_to_cart", { id: "blk-001", quantity: 2 });
    const addData = JSON.parse(addResult.content[0].text);
    console.log("✓ Add to cart works:", addData.quantity, "units");

    // Test cart view
    const cartResult = await client.callTool("blinkit.cart", {});
    const cartData = JSON.parse(cartResult.content[0].text);
    console.log("✓ Cart view works: Total = ₹" + cartData.total);

    console.log("\n✅ Blinkit server: ALL TESTS PASSED\n");
    return true;
  } catch (err) {
    console.error("❌ Blinkit server test failed:", err.message);
    return false;
  } finally {
    client.close();
  }
}

async function testPayment() {
  console.log("\n=== Testing Payment Server ===\n");
  const client = new TestClient("payment", "node", ["mcp_tools/dist/payment-server.js"]);
  
  try {
    await client.initialize();
    console.log("✓ Initialized");

    const tools = await client.listTools();
    console.log("✓ Tools listed:", tools.tools.map(t => t.name).join(", "));

    // Test list methods
    const methodsResult = await client.callTool("payment.methods", {});
    const methodsData = JSON.parse(methodsResult.content[0].text);
    console.log("✓ Payment methods listed:", methodsData.length, "method(s)");
    if (methodsData[0].merchantVpa) {
      console.log("  → Merchant VPA:", methodsData[0].merchantVpa);
    }

    // Test init payment
    const initResult = await client.callTool("payment.init", { 
      orderId: "test-order-123", 
      amount: 499 
    });
    const initData = JSON.parse(initResult.content[0].text);
    console.log("✓ Payment init works:");
    console.log("  → Payment ID:", initData.paymentId);
    console.log("  → Amount: ₹" + initData.amount);
    console.log("  → Total: ₹" + initData.total);
    console.log("  → Merchant VPA:", initData.merchantVpa);
    console.log("  → Status:", initData.status);

    // Test payment status
    const statusResult = await client.callTool("payment.status", { 
      paymentId: initData.paymentId 
    });
    const statusData = JSON.parse(statusResult.content[0].text);
    console.log("✓ Payment status works:");
    console.log("  → Status:", statusData.status);
    if (statusData.txnId) {
      console.log("  → Transaction ID:", statusData.txnId);
    }

    console.log("\n✅ Payment server: ALL TESTS PASSED\n");
    return true;
  } catch (err) {
    console.error("❌ Payment server test failed:", err.message);
    return false;
  } finally {
    client.close();
  }
}

async function main() {
  console.log("🧪 Testing MCP Servers...\n");
  
  const blinkitOk = await testBlinkit();
  const paymentOk = await testPayment();

  console.log("\n" + "=".repeat(50));
  if (blinkitOk && paymentOk) {
    console.log("✅ ALL SERVERS WORKING PERFECTLY!");
  } else {
    console.log("❌ SOME TESTS FAILED");
    process.exit(1);
  }
  console.log("=".repeat(50) + "\n");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});

