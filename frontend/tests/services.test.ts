import test from "node:test";
import assert from "node:assert/strict";
import { makeInitialGraph, allNodes } from "../src/data/langchain.ts";
import {
  expandMockGraph,
  exportGraph,
  graphService,
  mergeGraph,
  validateUrl,
} from "../src/services/graph.ts";
import { askMockGraph } from "../src/services/chat.ts";
import { loadNotes, saveNotes } from "../src/utils/storage.ts";
import { mapEvidence, mapExpansion } from "../src/services/backendAdapter.ts";

test("initial graph has 12 complete nodes and no dangling edges or source references", () => {
  const graph = makeInitialGraph();
  assert.equal(graph.nodes.length, 12);
  for (const n of allNodes) {
    assert.ok(n.summary && n.explanation && n.purpose);
    assert.ok(
      n.sourceIds.every((id) => graph.sources.some((s) => s.id === id)),
    );
    assert.ok(
      n.relatedNodeIds.every((id) => allNodes.some((node) => node.id === id)),
    );
  }
  assert.ok(
    graph.edges.every(
      (e) =>
        graph.nodes.some((n) => n.id === e.source) &&
        graph.nodes.some((n) => n.id === e.target),
    ),
  );
});

test("URL validation accepts HTTP(S), rejects malformed, credential and script URLs", () => {
  for (const url of [
    "https://docs.langchain.com",
    " http://localhost:8000/docs ",
  ])
    assert.equal(validateUrl(url), null);
  for (const url of [
    "",
    "not-a-url",
    "ftp://files.test",
    "javascript:alert(1)",
    "https://",
    "https://name:secret@example.com",
  ])
    assert.ok(validateUrl(url));
});

test("creating a graph records requestedUrl without rewriting reference URLs", async () => {
  const graph = await graphService.createGraphFromUrl(
    "https://example.com/my-docs",
  );
  assert.equal(graph.requestedUrl, "https://example.com/my-docs");
  assert.ok(graph.isMock);
  assert.ok(
    graph.sources.every((s) => s.url !== graph.requestedUrl && s.isMock),
  );
});

test("bounded expansion is idempotent and only adds direct neighbours", () => {
  const initial = makeInitialGraph();
  const expanded = expandMockGraph(initial, "retrieval");
  const again = expandMockGraph(expanded, "retrieval");
  assert.equal(expanded.nodes.length, 15);
  assert.deepEqual(again, expanded);
  assert.equal(new Set(again.edges.map((e) => e.id)).size, again.edges.length);
  assert.ok(
    expanded.nodes
      .filter((n) => !initial.nodes.some((old) => old.id === n.id))
      .every((n) => n.relatedNodeIds.includes("retrieval")),
  );
  assert.equal(initial.nodes.length, 12, "initial state is not mutated");
});

test("expanding different nodes deduplicates shared neighbours and edges", () => {
  let graph = expandMockGraph(makeInitialGraph(), "agents");
  graph = expandMockGraph(graph, "memory");
  assert.equal(graph.nodes.filter((n) => n.id === "agent-state").length, 1);
  assert.equal(graph.nodes.length, new Set(graph.nodes.map((n) => n.id)).size);
  assert.equal(graph.edges.length, new Set(graph.edges.map((n) => n.id)).size);
  assert.throws(() => expandMockGraph(graph, "missing"));
});

test("merge drops edges with absent endpoints", () => {
  const graph = makeInitialGraph();
  const next = mergeGraph(
    graph,
    [],
    [
      {
        id: "dangling",
        source: "langchain",
        target: "not-loaded",
        relation: "test",
      },
    ],
  );
  assert.ok(!next.edges.some((e) => e.id === "dangling"));
});

test("regeneration resets expansion and returns an independent copy", () => {
  const expanded = expandMockGraph(makeInitialGraph(), "agents");
  const fresh = makeInitialGraph();
  assert.equal(fresh.nodes.length, 12);
  expanded.nodes[0].summary = "changed";
  assert.notEqual(makeInitialGraph().nodes[0].summary, "changed");
});

test("chat uses named node ahead of selection and returns renderable links", () => {
  const graph = makeInitialGraph();
  const reply = askMockGraph({
    question: "Giải thích Retrieval",
    selectedNodeId: "agents",
    graph,
  });
  assert.ok(reply.content.startsWith("Retrieval:"));
  assert.ok(reply.isMock);
  assert.ok(reply.nodeIds.every((id) => graph.nodes.some((n) => n.id === id)));
});

test("chat follows contextual questions and admits out of scope questions", () => {
  const graph = makeInitialGraph();
  assert.ok(
    askMockGraph({
      question: "node này dùng thế nào?",
      selectedNodeId: "agents",
      graph,
    }).content.startsWith("Agents:"),
  );
  assert.match(
    askMockGraph({
      question: "Thời tiết Hà Nội ngày mai?",
      selectedNodeId: "agents",
      graph,
    }).content,
    /chưa có thông tin phù hợp/,
  );
});

test("export includes expanded graph and excludes private notes and chat", () => {
  const graph = expandMockGraph(
    makeInitialGraph("https://example.com/"),
    "retrieval",
  );
  const result = JSON.parse(
    exportGraph({
      ...graph,
      notes: "private",
      chat: ["private"],
    } as typeof graph),
  );
  assert.deepEqual(
    Object.keys(result).sort(),
    [
      "schemaVersion",
      "isMock",
      "requestedUrl",
      "nodes",
      "edges",
      "sources",
    ].sort(),
  );
  assert.equal(result.nodes.length, 15);
  assert.equal(result.schemaVersion, "1.0");
});

test("notes survive storage round trip with Vietnamese, newlines and empty content", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
  assert.deepEqual(loadNotes(storage), { text: "", error: null });
  const content = "Ghi chú của tôi\n\n## Retrieval\nMột kết nối mới.";
  assert.equal(saveNotes(content, storage), null);
  assert.deepEqual(loadNotes(storage), { text: content, error: null });
  assert.equal(saveNotes("", storage), null);
  assert.equal(loadNotes(storage).text, "");
});

test("unavailable or corrupt localStorage gives actionable errors", () => {
  const blocked = {
    getItem() {
      throw new Error("Blocked");
    },
    setItem() {
      throw new Error("Quota");
    },
  };
  assert.ok(loadNotes(blocked).error);
  assert.ok(saveNotes("keep in memory", blocked));
  assert.ok(loadNotes({ getItem: () => "{corrupted", setItem() {} }).error);
  assert.ok(loadNotes({ getItem: () => '{"text":5}', setItem() {} }).error);
});

test("backend adapter does not silently mix real and mock provenance", () => {
  const response = {
    center_node: { id: "a", label: "A", type: "Framework" },
    nodes: [],
    edges: [],
    pagination: { returned: 0, has_more: false, next_cursor: null },
  };
  assert.throws(() => mapExpansion(response, makeInitialGraph()), /Không trộn/);
  const graph = mapExpansion(response, {
    schemaVersion: "1.0",
    isMock: false,
    requestedUrl: null,
    nodes: [],
    edges: [],
    sources: [],
  });
  assert.equal(graph.nodes[0].type, "Framework");
  assert.equal(graph.nodes[0].sourceIds.length, 0);
  assert.ok(!graph.isMock);
  assert.equal(
    mapEvidence({
      evidence_id: "e",
      document_id: "doc",
      url: "https://example.com",
      text: "evidence",
    }).isMock,
    false,
  );
  assert.throws(() =>
    mapEvidence({
      evidence_id: "e",
      document_id: "doc",
      url: "javascript:alert(1)",
      text: "",
    }),
  );
});
