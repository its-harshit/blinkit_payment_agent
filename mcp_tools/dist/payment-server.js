#!/usr/bin/env node
// Minimal MCP-compatible stdio server emulating a Blinkit payment gateway.
import * as readline from "node:readline";
import crypto from "node:crypto";

const payments = new Map();

const tools = [
  {
    name: "payment.methods",
    description: "List supported payment methods for Blinkit",
    input_schema: {
      type: "object",
      properties: {},
      additionalProperties: false
    }
  },
  {
    name: "payment.init",
    description: "Create a payment intent for a Blinkit order (UPI only)",
    input_schema: {
      type: "object",
      properties: {
        orderId: { type: "string", description: "Blinkit order id" },
        amount: { type: "number", description: "Amount in INR" },
        currency: { type: "string", enum: ["INR"], default: "INR" },
        method: { type: "string", description: "Method id from payment.methods", default: "upi" }
      },
      required: ["orderId", "amount"]
    }
  },
  {
    name: "payment.status",
    description: "Check status of a payment intent",
    input_schema: {
      type: "object",
      properties: {
        paymentId: { type: "string", description: "Payment id returned by payment.init" }
      },
      required: ["paymentId"]
    }
  }
];

const merchantVpa = "blinkit@upi";

const methods = [
  {
    id: "upi",
    label: "UPI",
    merchantVpa,
    feePercent: 0,
    min: 1,
    max: 20000
  }
];

function respond(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function respondError(id, code, message) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
}

function createPayment(orderId, amount, method = "upi") {
  if (amount <= 0) throw new Error("Amount must be > 0");
  const methodDef = methods.find((m) => m.id === method);
  if (!methodDef) throw new Error("Unsupported payment method");
  if (amount < methodDef.min || amount > methodDef.max) {
    throw new Error(`Amount must be between ${methodDef.min} and ${methodDef.max} for ${method}`);
  }
  const id = "pay_" + crypto.randomUUID().replace(/-/g, "").slice(0, 18);
  const status = "requires_action";
  const fee = Math.round((amount * methodDef.feePercent) / 100);
  const total = amount + fee;
  const intent = {
    paymentId: id,
    orderId,
    amount,
    currency: "INR",
    method,
    fee,
    total,
    status,
    actionUrl: `https://payments.example.com/approve/${id}`,
    merchantVpa
  };
  payments.set(id, intent);
  return intent;
}

function getPayment(paymentId) {
  const p = payments.get(paymentId);
  if (!p) throw new Error("Payment not found");
  return p;
}

// Simulate action completion by toggling status if called again after creation
function maybeAutoComplete(intent) {
  if (intent.status === "requires_action") {
    intent.status = "succeeded";
    intent.txnId = "txn_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    payments.set(intent.paymentId, intent);
  }
  return intent;
}

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch (err) {
    respondError(null, -32700, `Invalid JSON: ${err.message}`);
    return;
  }

  const { id = null, method, params = {} } = msg;
  try {
    switch (method) {
      case "initialize": {
        respond(id, {
          serverInfo: { name: "payment-gateway-mcp", version: "0.1.0" },
          capabilities: { tools: { list: true, call: true } }
        });
        break;
      }
      case "tools/list": {
        respond(id, { tools });
        break;
      }
      case "tools/call": {
        const { name, arguments: args = {} } = params;
        if (!name) throw new Error("Missing tool name");
        let content;
        switch (name) {
          case "payment.methods": {
            content = [{ type: "text", text: JSON.stringify(methods, null, 2) }];
            break;
          }
          case "payment.init": {
            const intent = createPayment(args.orderId, Number(args.amount), args.method);
            content = [{ type: "text", text: JSON.stringify(intent, null, 2) }];
            break;
          }
          case "payment.status": {
            const intent = maybeAutoComplete(getPayment(args.paymentId));
            content = [{ type: "text", text: JSON.stringify(intent, null, 2) }];
            break;
          }
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
        respond(id, { content });
        break;
      }
      default:
        respondError(id, -32601, `Unknown method: ${method}`);
    }
  } catch (err) {
    respondError(id, -32000, err?.message ?? "Unexpected error");
  }
});

rl.on("close", () => process.exit(0));

