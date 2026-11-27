#!/usr/bin/env node
// Focused checks of the v2 function nodes. usage: node tests.js <flow.json>
"use strict";
const fs = require("fs");
const assert = require("assert");
const nodes = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
const tabEnv = Object.fromEntries((byId.mqtt_bridge_tab.env || []).map(e => [e.name, e.value]));

function harness(extraEnv = {}) {
    let T = Date.UTC(2026, 10, 27);
    const RealDate = Date;
    class FakeDate extends RealDate { constructor(...a) { if (a.length === 0) super(T); else super(...a); } static now() { return T; } }
    const envMap = Object.assign({}, tabEnv, { ENERGYID_PROVISIONING_KEY: "K", ENERGYID_PROVISIONING_SECRET: "S" }, extraEnv);
    const store = {};
    const g = { get: k => store[k], set: (k, v) => { store[k] = v; } };
    const warns = [];
    const fn = id => {
        const f = new Function("msg", "node", "global", "env", "Date", "Buffer", byId[id].func);
        return msg => {
            const out = [];
            const ret = f(msg, { warn: w => warns.push(String(w)), status: () => {}, error: e => { throw new Error(e); }, send: m => out.push(m) }, g, { get: k => envMap[k] }, FakeDate, Buffer);
            if (ret) out.push(ret);
            return out;
        };
    };
    return {
        store, warns,
        advance: s => { T += s * 1000; },
        now: () => T,
        router: fn("mqtt_bridge_func_router_t"),
        pop: fn("mqtt_bridge_func_hello_pop_t"),
        store_: fn("mqtt_bridge_func_hello_store_t"),
        fanout: fn("mqtt_bridge_func_batch_fanout_t"),
        resp: fn("mqtt_bridge_func_batch_resp_t"),
        report: fn("mqtt_bridge_func_report_t"),
    };
}
const jwt = exp => `${Buffer.from('{"alg":"HS256"}').toString("base64url")}.${Buffer.from(JSON.stringify({ exp })).toString("base64url")}.s`;
function claimDevice(h, id, url, auth) {
    h.store_({ deviceId: id, statusCode: 200, payload: { webhookUrl: url, headers: { authorization: auth, "x-twin-id": "t-" + id }, recordName: "R", webhookPolicy: { uploadInterval: 900 } } });
}
function publish(h, id, wh) { h.router({ topic: `xky/${id}/tele/SENSOR`, payload: { TIC: { BASE: wh } } }); }
let passed = 0;
function test(name, f) { f(); passed++; console.log("ok -", name); }

test("compaction merges samples per 60 s bucket and keeps the latest value; incremental equals full", () => {
    const h = harness();
    const start = Math.floor(h.now() / 1000);
    for (let i = 0; i < 600; i++) { publish(h, "A", 1000 + i); h.advance(1); if (i % 37 === 0) h.fanout({}); }
    h.fanout({});
    const buf = h.store["eid.buffers"]["teleinfo-A"];
    const buckets = new Set(buf.map(p => Math.floor(p.ts / 60)));
    assert.strictEqual(buckets.size, buf.length, "one point per bucket");
    assert.ok(buf.length >= 10 && buf.length <= 11, `~10 minutes -> ${buf.length}`);
    assert.strictEqual(buf[buf.length - 1].el, (1000 + 599) / 1000, "latest value kept");
    for (const p of buf) {
        const i = Math.round(p.el * 1000 - 1000);
        assert.strictEqual(Math.floor(p.ts / 60), Math.floor((start + i) / 60), "value belongs to its own bucket");
        assert.strictEqual(p.ts, start + i, "ts and value come from the same sample");
    }
});

test("SAS and JWT expiry are read from /hello headers", () => {
    const h = harness();
    publish(h, "A", 1); publish(h, "B", 1);
    claimDevice(h, "teleinfo-A", "https://x.servicebus.windows.net/q/messages", "SharedAccessSignature sr=a&sig=b%3D&se=1800000000&skn=DeviceAccessKey");
    claimDevice(h, "teleinfo-B", "https://hooks.energyid.eu/webhook-in", "Bearer " + jwt(1800000123));
    const r = h.store["eid.registry"];
    assert.strictEqual(r["teleinfo-A"].credentialExpiresAt, 1800000000 * 1000);
    assert.strictEqual(r["teleinfo-A"].endpoint, "servicebus");
    assert.strictEqual(r["teleinfo-B"].credentialExpiresAt, 1800000123 * 1000);
    assert.strictEqual(r["teleinfo-B"].endpoint, "webhook");
});

test("an expiring credential refresh goes before a queue of unclaimed devices", () => {
    const h = harness({ EID_HELLO_PER_TICK: "1" });
    for (let i = 0; i < 50; i++) publish(h, "U" + i, 1);
    publish(h, "C", 1);
    claimDevice(h, "teleinfo-C", "https://hooks.energyid.eu/webhook-in", "Bearer " + jwt(Math.floor(h.now() / 1000) + 3 * 3600));
    h.advance(400);
    const sent = h.pop({ payload: "" });
    assert.strictEqual(sent.length, 1);
    assert.strictEqual(sent[0].deviceId, "teleinfo-C");
    assert.strictEqual(sent[0].helloReason, "expiring-refresh");
});

test("auto /hello rate clears a restart backlog quickly", () => {
    const h = harness();
    for (let i = 0; i < 600; i++) publish(h, "U" + i, 1);
    assert.strictEqual(h.pop({ payload: "" }).length, 10);
    const h2 = harness();
    for (let i = 0; i < 20; i++) publish(h2, "U" + i, 1);
    assert.strictEqual(h2.pop({ payload: "" }).length, 2);
});

test("a refused point is isolated by halving and dropped; all other points are delivered", () => {
    const h = harness();
    publish(h, "A", 1);
    claimDevice(h, "teleinfo-A", "https://hooks.energyid.eu/webhook-in", "Bearer " + jwt(2e9));
    const buf = h.store["eid.buffers"]["teleinfo-A"];
    buf.length = 0;
    const base = Math.floor(h.now() / 1000) - 400 * 60;
    for (let i = 0; i < 400; i++) buf.push({ ts: base + i * 60, el: i });
    const poisonTs = base + 123 * 60;
    const got = new Set();
    for (let round = 0; round < 200 && (h.store["eid.buffers"]["teleinfo-A"].length || h.store["eid.registry"]["teleinfo-A"].inflight); round++) {
        h.advance(61);
        for (const m of h.fanout({})) {
            const bad = m.payload.some(p => p.ts === poisonTs);
            if (!bad) m.payload.forEach(p => got.add(p.ts));
            h.resp(Object.assign({}, m, bad ? { statusCode: 400, payload: { error: "invalid_model" }, headers: {} } : { statusCode: 200, payload: "", headers: {} }));
        }
    }
    const d = h.store["eid.registry"]["teleinfo-A"];
    assert.strictEqual(d.droppedPoints, 1);
    assert.strictEqual(d.lastDroppedPoint.ts, poisonTs);
    for (let i = 0; i < 400; i++) if (i !== 123) assert.ok(got.has(base + i * 60), `point ${i} delivered`);
    assert.ok(!d.batchLimit || d.batchLimit >= 1);
});

test("429 pauses the whole host, honours Retry-After up to the doubling step, success resets", () => {
    const h = harness();
    for (const id of ["A", "B", "C"]) { publish(h, id, 1); claimDevice(h, "teleinfo-" + id, "https://hooks.energyid.eu/webhook-in", "Bearer " + jwt(2e9)); }
    h.advance(61);
    const sent = h.fanout({});
    assert.strictEqual(sent.length, 3);
    h.resp(Object.assign({}, sent[0], { statusCode: 429, payload: "x", headers: { "retry-after": "534.25" } }));
    const host = h.store["eid.hosts"]["hooks.energyid.eu"];
    assert.strictEqual(host.pausedUntil, h.now() + 30000, "first pause = 30 s step");
    h.resp(Object.assign({}, sent[1], { statusCode: 429, payload: "x", headers: { "retry-after": "534.25" } }));
    assert.strictEqual(host.pausedUntil, h.now() + 60000, "second consecutive 429 doubles");
    h.resp(Object.assign({}, sent[2], { statusCode: 200, payload: "", headers: {} }));
    assert.strictEqual(host.consecutive429, 0);
    publish(h, "C", 2);
    h.advance(10);
    assert.strictEqual(h.fanout({}).length, 0, "nothing sent to a paused host");
    h.advance(60);
    const again = h.fanout({}).map(m => m.deviceId).sort();
    assert.deepStrictEqual(again, ["teleinfo-A", "teleinfo-B"], "throttled devices retry after the pause; C waits for its interval");
    assert.ok(h.store["eid.buffers"]["teleinfo-A"].length === 0);
});

test("fair order: the device that waited longest is sent first when slots are limited", () => {
    const h = harness({ EID_MAX_SENDS_PER_TICK: "1" });
    for (const id of ["A", "B", "C"]) { publish(h, id, 1); claimDevice(h, "teleinfo-" + id, "https://x.servicebus.windows.net/q/messages", "SharedAccessSignature se=2000000000"); }
    const r = h.store["eid.registry"];
    r["teleinfo-A"].lastUploadAt = h.now() - 1000;
    r["teleinfo-B"].lastUploadAt = h.now() - 90000;
    r["teleinfo-C"].lastUploadAt = h.now() - 5000;
    h.advance(1);
    assert.deepStrictEqual(h.fanout({}).map(m => m.deviceId), ["teleinfo-B"]);
});

test("Service Bus batches stay under the byte limit", () => {
    const h = harness({ EID_MAX_BATCH_BYTES: "5000", EID_MIN_POINT_SPACING_S: "0" });
    publish(h, "A", 1);
    claimDevice(h, "teleinfo-A", "https://x.servicebus.windows.net/q/messages", "SharedAccessSignature se=2000000000");
    const buf = h.store["eid.buffers"]["teleinfo-A"];
    for (let i = 0; i < 900; i++) buf.push({ ts: 1795000000 + i, el: 1234.5678 + i, pwr: 0.123 });
    h.advance(1);
    const [m] = h.fanout({});
    assert.ok(JSON.stringify(m.payload).length <= 5000, `${JSON.stringify(m.payload).length} bytes`);
    assert.ok(m.payload.length > 50);
});

test("report flags a fleet on /webhook-in and counts endpoints", () => {
    const h = harness();
    for (let i = 0; i < 30; i++) { publish(h, "W" + i, 1); claimDevice(h, "teleinfo-W" + i, "https://hooks.energyid.eu/webhook-in", "Bearer " + jwt(2e9)); }
    publish(h, "S", 1); claimDevice(h, "teleinfo-S", "https://x.servicebus.windows.net/q/messages", "SharedAccessSignature se=2000000000");
    const p = h.report({})[0].payload;
    assert.deepStrictEqual(p.endpoints, { webhook: 30, servicebus: 1 });
    assert.ok(p.problems[0].startsWith("fleet: 30 devices upload to /webhook-in"));
});

console.log(`${passed} passed`);
