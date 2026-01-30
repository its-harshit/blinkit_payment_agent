export function isJsonRpcResponse(v) {
    if (!v || typeof v !== "object")
        return false;
    const o = v;
    if (o.jsonrpc !== "2.0")
        return false;
    if (!("id" in o))
        return false;
    return ("result" in o) || ("error" in o);
}
