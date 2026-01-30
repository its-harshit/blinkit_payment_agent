"""MCP client for communicating with MCP servers via stdio."""
import asyncio
import json
import subprocess
import threading
from queue import Queue
from typing import Any, Dict, Optional


class McpClient:
    """Client for communicating with MCP servers via stdio JSON-RPC."""

    def __init__(self, name: str, command: list[str], cwd: Optional[str] = None, timeout: float = 30.0):
        """Initialize MCP client.

        Args:
            name: Name of the client (for logging)
            command: Command to run the MCP server (e.g., ["node", "dist/blinkit-server.js"])
            cwd: Working directory for the subprocess
            timeout: Per-request timeout in seconds
        """
        self.name = name
        self.timeout = timeout
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=cwd
        )
        self.pending = {}
        self.next_id = 1
        self.response_queue: Queue[Dict[str, Any]] = Queue()
        self._start_reader()

    def _start_reader(self):
        """Start reading responses from the server."""
        def reader():
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("jsonrpc") == "2.0" and msg.get("id") is not None:
                        self.response_queue.put(msg)
                except json.JSONDecodeError:
                    continue

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

    async def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        request_id = self.next_id
        self.next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }

        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        # Wait for response asynchronously
        timeout = self.timeout
        elapsed = 0
        while elapsed < timeout:
            try:
                # Use asyncio to wait for queue item
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.response_queue.get(timeout=0.1)
                )
                if response.get("id") == request_id:
                    if "error" in response:
                        raise Exception(f"RPC error: {response['error'].get('message')}")
                    return response.get("result", {})
            except:
                await asyncio.sleep(0.1)
                elapsed += 0.1
                continue
        raise TimeoutError(f"Request {request_id} timed out")

    async def initialize(self):
        """Initialize the MCP server."""
        await self._request("initialize", {
            "clientInfo": {"name": self.name, "version": "0.1.0"},
            "capabilities": {}
        })

    async def list_tools(self) -> list[Dict[str, Any]]:
        """List available tools."""
        result = await self._request("tools/list")
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool with arguments."""
        result = await self._request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result

    def close(self):
        """Close the client and terminate the process."""
        if self.process:
            self.process.terminate()
            self.process.wait()
