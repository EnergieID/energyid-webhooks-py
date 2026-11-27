#!/usr/bin/env node
// Discrete-event simulation of the Node-RED MQTT bridge against mock EnergyID endpoints.
// Runs the real function-node code from a flow JSON with a fake clock.
// usage: node sim.js <flow.json> <mode> [devices] [claimed] [hours] [publishEveryS] [extraEnvJSON]
//   mode: webhook-ip       /webhook-in throttled 30/900 s per caller IP per instance (production today)
//         webhook-device   /webhook-in throttled 30/900 s per IP+x-twin-id (server fix 2)
//         servicebus       Service Bus queue endpoint, no throttle (server fix 1)
"use strict";
const fs = require("fs");

const [flowPath, mode = "webhook-ip", nDev = "338", nClaimed = "120", hours = "12", everyS = "25", extraEnv = "{}"] = process.argv.slice(2);
const N = parseInt(nDev, 10), CLAIMED = parseInt(nClaimed, 10), H = parseFloat(hours), EVERY = parseFloat(everyS);
const nodes = JSON.parse(fs.readFileSync(flowPath, "utf8"));
const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
const tab = byId.mqtt_bridge_tab;

// ---------- fake clock ----------
const T0 = Date.UTC(2026, 10, 27, 0, 0, 0);
let T = T0;
const RealDate = Date;
class FakeDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(T); else super(...a); }
    static now() { return T; }
}

// ---------- Node-RED shims ----------
const envMap = Object.fromEntries((tab.env || []).map(e => [e.name, e.value]));
Object.assign(envMap, { ENERGYID_PROVISIONING_KEY: "K", ENERGYID_PROVISIONING_SECRET: "S" }, JSON.parse(extraEnv));
const env = { get: k => (k in envMap ? envMap[k] : undefined) };
const store = {};
const global = { get: k => store[k], set: (k, v) => { store[k] = v; } };
let warnCount = 0;
const warnSamples = {};

function compile(id) {
    const n = byId[id];
    const fn = new Function("msg", "node", "global", "env", "Date", "Buffer", n.func);
    return function run(msg) {
        const out = [];
        const nodeObj = {
            warn: m => { warnCount++; const k = String(m).replace(/[A-Za-z0-9-]*\d[A-Za-z0-9-]*/g, "#").slice(0, 80); warnSamples[k] = (warnSamples[k] || 0) + 1; },
            error: m => { throw new Error(`${id}: ${m}`); },
            status: () => {},
            send: m => out.push(Array.isArray(m) ? m : [m]),
        };
        const ret = fn(msg, nodeObj, global, env, FakeDate, Buffer);
        if (ret !== null && ret !== undefined) out.push(Array.isArray(ret) ? ret : [ret]);
        return out; // list of per-output arrays
    };
}
const router = compile("mqtt_bridge_func_router_t");
const helloPop = compile("mqtt_bridge_func_hello_pop_t");
const helloStore = compile("mqtt_bridge_func_hello_store_t");
const fanout = compile("mqtt_bridge_func_batch_fanout_t");
const batchResp = compile("mqtt_bridge_func_batch_resp_t");
const report = compile("mqtt_bridge_func_report_t");

// ---------- event queue ----------
// binary heap
const heap = [];
let seq = 0;
function push(t, f) {
    heap.push({ t, f, s: seq++ });
    let i = heap.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (less(heap[i], heap[p])) { [heap[i], heap[p]] = [heap[p], heap[i]]; i = p; } else break; }
}
function less(a, b) { return a.t < b.t || (a.t === b.t && a.s < b.s); }
function popHeap() {
    const top = heap[0], last = heap.pop();
    if (heap.length) {
        heap[0] = last; let i = 0;
        for (;;) {
            const l = 2 * i + 1, r = l + 1; let m = i;
            if (l < heap.length && less(heap[l], heap[m])) m = l;
            if (r < heap.length && less(heap[r], heap[m])) m = r;
            if (m === i) break; [heap[i], heap[m]] = [heap[m], heap[i]]; i = m;
        }
    }
    return top;
}

// ---------- mock EnergyID ----------
const devIds = Array.from({ length: N }, (_, i) => "X" + String(i + 1).padStart(4, "0"));
const claimedSet = new Set(devIds.slice(0, CLAIMED));
const twinOf = id => "00000000-0000-0000-0000-" + id.replace(/\D/g, "").padStart(12, "0");
const stats = { hello: 0, uploads: 0, ok: 0, s429: 0, s400: 0, other: 0, points: 0, bytes: 0 };
const delivered = {}; // twin -> {count, maxTs}
const instances = [new Map(), new Map()];

function jwt(expSec) {
    const b64 = o => Buffer.from(JSON.stringify(o)).toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
    return `${b64({ alg: "HS256" })}.${b64({ exp: expSec, aud: "x" })}.sig`;
}
function helloResponse(body) {
    stats.hello++;
    const id = body.deviceId.replace(/^teleinfo-/, "");
    if (!claimedSet.has(id)) return { statusCode: 200, payload: { claimCode: body.claimCode, claimUrl: "https://app.energyid.eu/claim" } };
    const exp = Math.floor(T / 1000) + 4 * 24 * 3600;
    const twin = twinOf(id);
    if (mode === "servicebus") {
        return { statusCode: 200, payload: { webhookUrl: "https://sbns-energyid-prod.servicebus.windows.net/sbq-webhook-in/messages", headers: { authorization: `SharedAccessSignature sr=x&sig=abc&se=${exp}&skn=DeviceAccessKey`, "x-twin-id": twin }, recordName: "R", recordNumber: "EA-1", webhookPolicy: { uploadInterval: 900 } } };
    }
    return { statusCode: 200, payload: { webhookUrl: "https://hooks.energyid.eu/webhook-in", headers: { authorization: `Bearer ${jwt(exp)}`, "x-twin-id": twin }, recordName: "R", recordNumber: "EA-1", webhookPolicy: { uploadInterval: 900 } } };
}
function throttle(key, limit) {
    const inst = instances[Math.random() < 0.5 ? 0 : 1];
    let e = inst.get(key);
    if (e && T >= e.end) { inst.delete(key); e = null; }
    if (!e) { inst.set(key, { rem: limit - 1, end: T + 900e3 }); return null; }
    if (e.rem <= 0) return (e.end - T) / 1000;
    e.rem--;
    return null;
}
function uploadResponse(msg) {
    stats.uploads++;
    const twin = msg.headers["x-twin-id"];
    if (mode !== "servicebus") {
        const ra = throttle(mode === "webhook-device" ? "ip:" + twin : "ip", 30);
        if (ra !== null) { stats.s429++; return { statusCode: 429, payload: "You may only perform this action every 900 seconds.", headers: { "retry-after": String(ra) } }; }
        if (msg.payload.length > 1000) { stats.s400++; return { statusCode: 400, payload: { error: "too many" }, headers: {} }; }
    }
    const bytes = JSON.stringify(msg.payload).length;
    if (mode === "servicebus" && bytes > 256 * 1024) { stats.s400++; return { statusCode: 413, payload: "too large", headers: {} }; }
    stats.ok++; stats.points += msg.payload.length; stats.bytes += bytes;
    const d = delivered[twin] = delivered[twin] || { count: 0, maxTs: 0 };
    d.count += msg.payload.length;
    for (const p of msg.payload) if (p.ts > d.maxTs) d.maxTs = p.ts;
    return { statusCode: mode === "servicebus" ? 201 : 200, payload: "", headers: {} };
}

// ---------- wiring ----------
const LAT = 300;
function runHelloPop(msg) {
    for (const outs of helloPop(msg)) for (const m of outs) if (m) {
        const req = JSON.parse(JSON.stringify(m));
        push(T + LAT, () => { const r = helloResponse(req.payload); helloStore(Object.assign({}, m, r)); });
    }
}
function runFanout() {
    for (const outs of fanout({})) for (const m of outs) if (m) {
        const sentMsg = m;
        push(T + LAT, () => {
            const r = uploadResponse(sentMsg);
            const res = Object.assign({}, sentMsg, r);
            const outs2 = batchResp(res);
            for (const o of outs2) if (o && o[1]) runHelloPop(o[1]);
        });
    }
}

// ---------- traffic ----------
const counters = Object.fromEntries(devIds.map(id => [id, 1000 + Math.random() * 5000]));
let generated = 0;
devIds.forEach((id, i) => {
    const start = T0 + Math.random() * EVERY * 1000;
    const tick = () => {
        counters[id] += 0.002 + Math.random() * 0.01;
        generated++;
        router({ topic: `xky/${id}/tele/SENSOR`, payload: { TIC: { BASE: Math.round(counters[id] * 1000) } } });
        push(T + EVERY * 1000, tick);
    };
    push(start, tick);
});
const tickHello = () => { runHelloPop({ payload: "" }); push(T + 5000, tickHello); };
push(T0 + 3000, tickHello);
const tickBatch = () => { runFanout(); push(T + 10000, tickBatch); };
push(T0 + 10000, tickBatch);

// Freshness samples every 5 min after the first hour: minutes since the newest delivered reading per claimed device.
const lagSamples = [];
const sample = () => {
    if (T - T0 > 3600e3) {
        for (const id of claimedSet) {
            const d = delivered[twinOf(id)];
            lagSamples.push(d ? (T / 1000 - d.maxTs) / 60 : (T - T0) / 60000);
        }
    }
    push(T + 300e3, sample);
};
push(T0 + 300e3, sample);

const END = T0 + H * 3600e3;
const wall = RealDate.now();
while (heap.length) {
    const ev = popHeap();
    if (ev.t > END) break;
    T = ev.t;
    ev.f();
}

// ---------- results ----------
lagSamples.sort((a, b) => a - b);
const pctl = p => lagSamples.length ? lagSamples[Math.min(lagSamples.length - 1, Math.floor(p * lagSamples.length))].toFixed(1) : "-";
const finalLag = [...claimedSet].map(id => { const d = delivered[twinOf(id)]; return d ? (T / 1000 - d.maxTs) / 60 : Infinity; }).sort((a, b) => a - b);
const never = finalLag.filter(x => x === Infinity).length;
const bufs = store["eid.buffers"] || {};
const buffered = Object.values(bufs).reduce((s, b) => s + b.length, 0);
const rep = report({})[0][0].payload;
const out = {
    flow: flowPath.split("/").pop(), mode, devices: N, claimed: CLAIMED, hours: H, publishEveryS: EVERY,
    requests: stats.uploads, ok: stats.ok, http429: stats.s429, http4xx: stats.s400,
    requestsPerHour: Math.round(stats.uploads / H), okPerHour: Math.round(stats.ok / H),
    pointsDelivered: stats.points, avgPointsPerOkRequest: stats.ok ? Math.round(stats.points / stats.ok) : 0,
    helloCalls: stats.hello,
    freshnessMin: { p50: pctl(0.5), p95: pctl(0.95), max: pctl(0.99999) },
    finalLagMin: { p50: finalLag[Math.floor(finalLag.length / 2)].toFixed(1), max: finalLag[finalLag.length - 1 - never] !== undefined ? finalLag[finalLag.length - 1 - never].toFixed(1) : "-", neverDelivered: never },
    bufferedPointsAtEnd: buffered,
    reportProblems: rep.problems.length,
    warnings: warnCount,
    simWallMs: RealDate.now() - wall,
};
console.log(JSON.stringify(out));
if (process.env.SIM_VERBOSE) { console.log(Object.entries(warnSamples).sort((a, b) => b[1] - a[1]).slice(0, 8)); console.log(rep.problems.slice(0, 5), rep.minutesSinceLastUpload, rep.endpoints, rep.hosts); }
