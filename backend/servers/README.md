# MCP Servers (Node.js)

This directory contains all Node.js MCP servers and their build output.

- **dist/** – Compiled Blinkit and Payment servers (`blinkit-server.js`, `payment-server.js`)
- **travel-server.js** – Travel (flights/hotels) MCP server (source)
- **package.json** – Node project for this package
- **buy-blinkit.js**, **test-servers.js** – Scripts to run from this directory (`node buy-blinkit.js`, `node test-servers.js`)

The Python backend runs these servers with `cwd` set to this directory, so paths in commands are relative to here (e.g. `dist/blinkit-server.js`, `travel-server.js`).
