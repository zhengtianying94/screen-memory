// index.ts
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
var execFileAsync = promisify(execFile);
var dbPath;
var screenshotDir;
var CLI = "screen-memory";
async function runCli(args, timeout = 3e4) {
  const fullArgs = dbPath ? ["--db", dbPath, ...args] : [...args];
  const { stdout } = await execFileAsync(CLI, fullArgs, {
    timeout,
    windowsHide: true,
    encoding: "utf-8"
  });
  try {
    return JSON.parse(stdout);
  } catch {
    return { raw: stdout };
  }
}
var tools = {
  // ── Memory tools ────────────────────────────────────────────────
  memory_write: {
    name: "screen_memory_write",
    description: "Write a memory to the URI Graph. Creates the node if it doesn't exist. URIs use Nocturne format: core://topic, dynamic://2026/05/27, etc.",
    parameters: Type.Object({
      uri: Type.String({ description: "Nocturne URI (e.g. core://my/topic)" }),
      content: Type.String({ description: "Memory content to store" })
    }),
    async execute(_id, params) {
      const result = await runCli(["write", "--uri", params.uri, "--content", params.content]);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  memory_read: {
    name: "screen_memory_read",
    description: "Read the latest memory at a URI. Supports special system URIs: system://boot, system://index, system://recent/N",
    parameters: Type.Object({
      uri: Type.String({ description: "Nocturne URI to read" })
    }),
    async execute(_id, params) {
      const result = await runCli(["read", "--uri", params.uri]);
      if (!result || typeof result === "object" && Object.keys(result).length === 0) {
        return { content: [{ type: "text", text: `No memory found at ${params.uri}` }] };
      }
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  memory_search: {
    name: "screen_memory_search",
    description: "Full-text search across all memories in the URI Graph.",
    parameters: Type.Object({
      query: Type.String({ description: "FTS5 search query" }),
      limit: Type.Optional(Type.Number({ description: "Max results", default: 20 }))
    }),
    async execute(_id, params) {
      const args = ["search", "--query", params.query];
      if (params.limit) args.push("--limit", String(params.limit));
      const result = await runCli(args);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  memory_delete: {
    name: "screen_memory_delete",
    description: "Delete a node and all its memories from the URI Graph.",
    parameters: Type.Object({
      uri: Type.String({ description: "Nocturne URI to delete" })
    }),
    async execute(_id, params) {
      const result = await runCli(["delete", "--uri", params.uri]);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  // ── Graph tools ────────────────────────────────────────────────
  graph_query_subtree: {
    name: "screen_memory_subtree",
    description: "Query the subtree rooted at a URI. Returns all child nodes and their memories.",
    parameters: Type.Object({
      uri: Type.String({ description: "Root URI" }),
      max_depth: Type.Optional(Type.Number({ description: "Max depth to traverse" }))
    }),
    async execute(_id, params) {
      const args = ["subtree", "--uri", params.uri];
      if (params.max_depth) args.push("--max-depth", String(params.max_depth));
      const result = await runCli(args);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  // ── Signal tools ────────────────────────────────────────────────
  signal_ingest: {
    name: "screen_signal_ingest",
    description: "Ingest a signal for entity lifecycle tracking. Entities accumulate signals and are promoted to the graph when they reach activation threshold. Entity types: person, topic, location, event.",
    parameters: Type.Object({
      entity_type: Type.String({ description: "Entity type (person, topic, location, event)" }),
      entity_name: Type.String({ description: "Entity name or identifier" }),
      source: Type.String({ description: "Signal source (screenshot, chat, etc.)" }),
      evidence: Type.Optional(Type.Array(Type.String(), { description: "Evidence tags" }))
    }),
    async execute(_id, params) {
      const args = [
        "signal-ingest",
        "--type",
        params.entity_type,
        "--name",
        params.entity_name,
        "--source",
        params.source
      ];
      if (params.evidence?.length) {
        args.push("--evidence", ...params.evidence);
      }
      const result = await runCli(args);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  signal_activate: {
    name: "screen_signal_activate",
    description: "Manually activate an entity and materialize it into the URI Graph, bypassing the normal signal threshold.",
    parameters: Type.Object({
      entity_name: Type.String({ description: "Entity name to activate" })
    }),
    async execute(_id, params) {
      const result = await runCli(["signal-activate", "--name", params.entity_name]);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  // ── Screenshot tools ────────────────────────────────────────────
  screenshot_search: {
    name: "screen_screenshot_search",
    description: "Search screenshots by OCR text content.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query" }),
      limit: Type.Optional(Type.Number({ description: "Max results", default: 20 }))
    }),
    async execute(_id, params) {
      const args = ["screenshot-search", "--query", params.query];
      if (params.limit) args.push("--limit", String(params.limit));
      const result = await runCli(args);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  },
  screen_capture: {
    name: "screen_capture",
    description: "Capture a screenshot from the current device screen, run OCR, and save to DB. Returns screenshot metadata including OCR text preview.",
    parameters: Type.Object({
      quality: Type.Optional(Type.Number({ description: "JPEG quality 1-100 (default 85)", default: 85 })),
      no_ocr: Type.Optional(Type.Boolean({ description: "Skip OCR, save screenshot only", default: false }))
    }),
    async execute(_id, params) {
      const args = ["capture"];
      if (params.quality) args.push("--quality", String(params.quality));
      if (params.no_ocr) args.push("--no-ocr");
      if (screenshotDir) args.push("--screenshot-dir", screenshotDir);
      const result = await runCli(args, 6e4);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  }
};
var index_default = definePluginEntry({
  id: "screen-memory",
  name: "Screen Memory",
  description: "Screen capture, OCR, URI Graph memory, and signal accumulation for OpenClaw",
  register(api) {
    const config = api.config;
    if (config?.dbPath) dbPath = config.dbPath;
    if (config?.screenshotDir) screenshotDir = config.screenshotDir;
    for (const tool of Object.values(tools)) {
      api.registerTool({
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters,
        execute: tool.execute
      });
    }
  }
});
export {
  index_default as default
};
