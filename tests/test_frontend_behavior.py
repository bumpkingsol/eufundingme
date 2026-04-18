from __future__ import annotations

import subprocess
from pathlib import Path


def run_frontend_script_test(script_source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module"],
        input=script_source,
        text=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )


def build_frontend_harness(test_body: str) -> str:
    app_js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").as_posix()
    return f"""
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync("{app_js}", "utf8");

class FakeElement {{
  constructor(id) {{
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.hidden = false;
    this.disabled = false;
    this.style = {{}};
    this.listeners = new Map();
  }}

  addEventListener(type, handler) {{
    if (!this.listeners.has(type)) {{
      this.listeners.set(type, []);
    }}
    this.listeners.get(type).push(handler);
  }}

  async dispatch(type, event = {{}}) {{
    const handlers = this.listeners.get(type) || [];
    for (const handler of handlers) {{
      const result = handler({{
        target: this,
        currentTarget: this,
        preventDefault() {{}},
        ...event,
      }});
      if (result && typeof result.then === "function") {{
        await result;
      }}
    }}
  }}

  focus() {{
    this.focused = true;
  }}
}}

const elements = new Map();
const selectorIds = [
  "match-form",
  "company-description",
  "match-button",
  "quick-fill-openai",
  "agent-handoff-copy",
  "agent-handoff-status",
  "agent-handoff-instructions",
  "submit-hint",
  "status-copy",
  "status-bar",
  "status-phase",
  "status-count",
  "status-prefixes",
  "status-failures",
  "status-coverage",
  "status-embeddings",
  "status-source",
  "status-refresh",
  "status-progress",
  "status-updated",
  "status-degraded",
  "resolution-banner",
  "results-empty",
  "results-list",
  "results-meta",
];

for (const id of selectorIds) {{
  elements.set(id, new FakeElement(id));
}}

const document = {{
  title: "EU Grant Matcher",
  querySelector(selector) {{
    if (!selector.startsWith("#")) {{
      throw new Error(`Unsupported selector: ${{selector}}`);
    }}
    return elements.get(selector.slice(1));
  }},
}};

const clipboardWrites = [];
const navigator = {{
  clipboard: {{
    async writeText(value) {{
      clipboardWrites.push(value);
    }},
  }},
}};

const timerQueue = [];
let nextTimerId = 1;
function setTimeoutMock(fn, _delay) {{
  const id = nextTimerId++;
  timerQueue.push({{ id, fn }});
  return id;
}}

function clearTimeoutMock(id) {{
  const index = timerQueue.findIndex((timer) => timer.id === id);
  if (index >= 0) {{
    timerQueue.splice(index, 1);
  }}
}}

async function flushTimers(maxSteps = 1) {{
  let steps = 0;
  while (timerQueue.length && steps < maxSteps) {{
    const timer = timerQueue.shift();
    timer.fn();
    await Promise.resolve();
    await Promise.resolve();
    steps += 1;
  }}
}}

const fetchCalls = [];
const profileResolvers = [];
let statusResponse = {{
  ok: true,
  json: async () => ({{
    phase: "ready",
    message: "Index ready",
    indexed_grants: 42,
    scanned_prefixes: 10,
    total_prefixes: 10,
    failed_prefixes: 0,
    truncated_prefixes: 0,
    embeddings_ready: true,
    matching_available: true,
    coverage_complete: true,
    degraded: false,
    degradation_reasons: [],
  }}),
}};
let matchResponse = {{
  ok: true,
  json: async () => ({{ indexed_grants: 42, results: [] }}),
}};

async function fetchMock(url, options = {{}}) {{
  fetchCalls.push({{ url, options }});
  if (url === "/api/index/status") {{
    return statusResponse;
  }}
  if (url === "/api/profile/resolve") {{
    if (!profileResolvers.length) {{
      throw new Error("No profile resolver queued");
    }}
    return profileResolvers.shift()(url, options);
  }}
  if (url === "/api/match") {{
    return matchResponse;
  }}
  throw new Error(`Unhandled fetch: ${{url}}`);
}}

const context = {{
  console,
  document,
  fetch: fetchMock,
  navigator,
  window: {{
    setTimeout: setTimeoutMock,
    clearTimeout: clearTimeoutMock,
    navigator,
  }},
  setTimeout: setTimeoutMock,
  clearTimeout: clearTimeoutMock,
  AbortController,
  Promise,
}};
context.globalThis = context;

vm.runInNewContext(source, context, {{ filename: "app.js" }});
await Promise.resolve();
await Promise.resolve();
const appContext = context;

const form = elements.get("match-form");
const descriptionInput = elements.get("company-description");
const matchButton = elements.get("match-button");
const quickFillButton = elements.get("quick-fill-openai");
const handoffCopyButton = elements.get("agent-handoff-copy");
const handoffStatus = elements.get("agent-handoff-status");
const handoffInstructions = elements.get("agent-handoff-instructions");
const resolutionBanner = elements.get("resolution-banner");
const resultsEmpty = elements.get("results-empty");
const resultsList = elements.get("results-list");
const resultsMeta = elements.get("results-meta");

function queueProfileResponse(factory) {{
  profileResolvers.push(factory);
}}

function profileJsonResponse(payload) {{
  return async () => ({{
    ok: true,
    json: async () => payload,
  }});
}}

function deferredProfileResponse() {{
  let resolveJson;
  const response = new Promise((resolve) => {{
    resolveJson = (payload) =>
      resolve({{
        ok: true,
        json: async () => payload,
      }});
  }});
  return {{
    response: async () => response,
    resolveJson,
  }};
}}

{test_body}
"""


def test_frontend_resolves_short_company_name_before_submit():
    script = build_frontend_harness(
        """
queueProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "OpenAI full profile for demo.",
    display_name: "OpenAI",
    source: "demo_profile",
    message: null,
  }),
);

descriptionInput.value = "OpenAI";
await descriptionInput.dispatch("input");
await flushTimers(1);
await descriptionInput.dispatch("blur");
await flushTimers(2);

const profileCalls = fetchCalls.filter((call) => call.url === "/api/profile/resolve");
if (profileCalls.length !== 1) {
  throw new Error(`Expected 1 resolve call, got ${profileCalls.length}`);
}
if (descriptionInput.value !== "OpenAI full profile for demo.") {
  throw new Error(`Unexpected resolved value: ${descriptionInput.value}`);
}
if (resolutionBanner.hidden) {
  throw new Error("Expected resolution banner to be visible");
}
if (!resolutionBanner.textContent.includes("Expanded OpenAI")) {
  throw new Error(`Unexpected banner copy: ${resolutionBanner.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_ignores_stale_resolver_response_when_input_changes():
    script = build_frontend_harness(
        """
const stale = deferredProfileResponse();
queueProfileResponse(stale.response);

descriptionInput.value = "OpenAI";
await descriptionInput.dispatch("input");
await flushTimers(2);

descriptionInput.value = "OpenAI platform team";
await descriptionInput.dispatch("input");
await flushTimers(1);

stale.resolveJson({
  resolved: true,
  profile: "Stale profile",
  display_name: "OpenAI",
  source: "demo_profile",
  message: null,
});
await Promise.resolve();
await flushTimers(1);

if (descriptionInput.value !== "OpenAI platform team") {
  throw new Error(`Stale response overwrote input: ${descriptionInput.value}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_skips_pre_resolve_for_full_description_and_keeps_submit_fallback():
    script = build_frontend_harness(
        """
descriptionInput.value = "We build advanced AI safety systems for enterprise deployment across Europe.";
await descriptionInput.dispatch("input");
await flushTimers(1);

let profileCalls = fetchCalls.filter((call) => call.url === "/api/profile/resolve");
if (profileCalls.length !== 0) {
  throw new Error(`Expected no pre-resolve calls, got ${profileCalls.length}`);
}

queueProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "OpenAI full profile for demo submit.",
    display_name: "OpenAI",
    source: "demo_profile",
    message: null,
  }),
);

descriptionInput.value = "OpenAI";
await form.dispatch("submit");
await flushTimers(2);

profileCalls = fetchCalls.filter((call) => call.url === "/api/profile/resolve");
if (profileCalls.length !== 1) {
  throw new Error(`Expected submit fallback resolve call, got ${profileCalls.length}`);
}
if (descriptionInput.value !== "OpenAI full profile for demo submit.") {
  throw new Error(`Submit fallback did not update value: ${descriptionInput.value}`);
}
if (!resultsMeta.textContent.includes("Indexed 42 live grants")) {
  throw new Error(`Unexpected results meta: ${resultsMeta.textContent}`);
}
if (resultsEmpty.hidden !== false) {
  throw new Error("Expected empty results state to remain visible");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_quick_fill_button_uses_profile_resolver():
    script = build_frontend_harness(
        """
queueProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "OpenAI full profile from quick fill.",
    display_name: "OpenAI",
    source: "demo_profile",
    message: null,
  }),
);

await quickFillButton.dispatch("click");
await flushTimers(1);

const profileCalls = fetchCalls.filter((call) => call.url === "/api/profile/resolve");
if (profileCalls.length !== 1) {
  throw new Error(`Expected 1 resolve call, got ${profileCalls.length}`);
}
const requestBody = JSON.parse(profileCalls[0].options.body);
if (requestBody.query !== "OpenAI") {
  throw new Error(`Unexpected quick fill query: ${requestBody.query}`);
}
if (descriptionInput.value !== "OpenAI full profile from quick fill.") {
  throw new Error(`Quick fill did not update value: ${descriptionInput.value}`);
}
if (resolutionBanner.hidden) {
  throw new Error("Expected resolution banner to be visible");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_updates_title_and_score_chip_classes_from_results():
    script = build_frontend_harness(
        """
matchResponse = {
  ok: true,
  json: async () => ({
    indexed_grants: 42,
    results: [
      {
        grant_id: "TOPIC-1",
        title: "AI Safety Grant",
        status: "Open",
        deadline: "2026-08-01",
        days_left: 30,
        budget: "EUR 5M",
        portal_url: "https://example.com/TOPIC-1",
        fit_score: 91,
        why_match: "Strong AI fit.",
        application_angle: "Lead with deployment.",
        framework_programme: "Horizon Europe",
        programme_division: "Cluster 4",
        keywords: ["ai"]
      },
      {
        grant_id: "TOPIC-2",
        title: "Transition Grant",
        status: "Open",
        deadline: "2026-09-01",
        days_left: 60,
        budget: "EUR 2M",
        portal_url: "https://example.com/TOPIC-2",
        fit_score: 55,
        why_match: "Moderate fit.",
        application_angle: "Lead with transition story.",
        framework_programme: "LIFE",
        programme_division: "Climate",
        keywords: ["climate"]
      },
      {
        grant_id: "TOPIC-3",
        title: "Low Fit Grant",
        status: "Open",
        deadline: "2026-10-01",
        days_left: 90,
        budget: "EUR 1M",
        portal_url: "https://example.com/TOPIC-3",
        fit_score: 20,
        why_match: "Weak fit.",
        application_angle: "Only pursue if repositioned.",
        framework_programme: "Digital Europe",
        programme_division: "SME",
        keywords: ["digital"]
      }
    ]
  }),
};

descriptionInput.value = "We build AI safety tooling for enterprise deployment across Europe.";
await form.dispatch("submit");
await flushTimers(1);

if (document.title !== "3 Grants Found | EU Grant Matcher") {
  throw new Error(`Unexpected title after success: ${document.title}`);
}
if (!resultsMeta.textContent.includes("Showing 3 best-fit results")) {
  throw new Error(`Unexpected results meta: ${resultsMeta.textContent}`);
}
if (!resultsList.innerHTML.includes("score-chip score-chip--high")) {
  throw new Error(`Missing high score class in markup: ${resultsList.innerHTML}`);
}
if (!resultsList.innerHTML.includes("score-chip score-chip--medium")) {
  throw new Error(`Missing medium score class in markup: ${resultsList.innerHTML}`);
}
if (!resultsList.innerHTML.includes("score-chip score-chip--low")) {
  throw new Error(`Missing low score class in markup: ${resultsList.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_resets_title_on_empty_results_and_errors():
    script = build_frontend_harness(
        """
document.title = "5 Grants Found | EU Grant Matcher";
matchResponse = {
  ok: true,
  json: async () => ({ indexed_grants: 42, results: [] }),
};

descriptionInput.value = "We build AI safety tooling for enterprise deployment across Europe.";
await form.dispatch("submit");
await flushTimers(1);

if (document.title !== "EU Grant Matcher") {
  throw new Error(`Expected title reset for empty results, got ${document.title}`);
}

matchResponse = {
  ok: false,
  json: async () => ({ detail: { message: "boom" } }),
};

await form.dispatch("submit");
await flushTimers(1);

if (document.title !== "EU Grant Matcher") {
  throw new Error(`Expected title reset for errors, got ${document.title}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_keeps_match_button_clickable_while_index_builds():
    script = build_frontend_harness(
        """
statusResponse = {
  ok: true,
  json: async () => ({
    phase: "building",
    message: "Indexing live grants",
    indexed_grants: 0,
    scanned_prefixes: 0,
    total_prefixes: 46,
    failed_prefixes: 0,
    truncated_prefixes: 0,
    embeddings_ready: false,
    matching_available: false,
    coverage_complete: false,
    degraded: false,
    degradation_reasons: [],
    snapshot_loaded: false,
    refresh_in_progress: true,
    current_prefix: null,
    current_page: null,
    last_progress_at: null,
    snapshot_age_seconds: null,
  }),
};

await flushTimers(1);

if (matchButton.disabled) {
  throw new Error("Expected match button to stay clickable while index is building");
}

matchResponse = {
  ok: false,
  json: async () => ({ detail: { message: "Indexing live grants" } }),
};

descriptionInput.value = "We build AI safety tooling for enterprise deployment across Europe.";
await form.dispatch("submit");
await flushTimers(1);

if (resultsEmpty.textContent !== "Indexing live grants") {
  throw new Error(`Expected readiness error to surface, got: ${resultsEmpty.textContent}`);
}
if (matchButton.disabled) {
  throw new Error("Expected match button to re-enable after not-ready submit response");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_labels_bundled_seed_snapshot_source():
    script = build_frontend_harness(
        """
statusResponse = {
  ok: true,
  json: async () => ({
    phase: "ready_degraded",
    message: "Using bundled seed snapshot while live refresh runs",
    indexed_grants: 12,
    scanned_prefixes: 0,
    total_prefixes: 46,
    failed_prefixes: 0,
    truncated_prefixes: 0,
    embeddings_ready: true,
    matching_available: true,
    coverage_complete: false,
    degraded: true,
    degradation_reasons: ["bundled_seed_mode"],
    snapshot_loaded: true,
    snapshot_source: "bundled",
    refresh_in_progress: true,
    current_prefix: null,
    current_page: null,
    last_progress_at: null,
    snapshot_age_seconds: 120,
  }),
};

appContext.updateStatus(await statusResponse.json());

if (elements.get("status-source").textContent !== "bundled seed snapshot (2m old)") {
  throw new Error(`Unexpected source label: ${elements.get("status-source").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_agent_handoff_copy_writes_expected_instructions():
    script = build_frontend_harness(
        """
if (!handoffInstructions.value.includes("eufundingme match --description")) {
  throw new Error(`Missing match command in handoff text: ${handoffInstructions.value}`);
}
if (!handoffInstructions.value.includes("request_id")) {
  throw new Error(`Missing request_id guidance in handoff text: ${handoffInstructions.value}`);
}

await handoffCopyButton.dispatch("click");
await flushTimers(1);

if (clipboardWrites.length !== 1) {
  throw new Error(`Expected one clipboard write, got ${clipboardWrites.length}`);
}
if (clipboardWrites[0] !== handoffInstructions.value) {
  throw new Error("Expected clipboard contents to match handoff instructions");
}
if (handoffStatus.textContent !== "Instructions copied. Paste them into your agent chat.") {
  throw new Error(`Unexpected copy status: ${handoffStatus.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_agent_handoff_is_ready_before_any_search():
    script = build_frontend_harness(
        """
if (!handoffInstructions.value.includes("python -m venv .venv")) {
  throw new Error("Expected venv setup instructions to be present before any search");
}
if (!handoffInstructions.value.includes("eufundingme health")) {
  throw new Error("Expected health verification instructions to be present");
}
if (!handoffInstructions.value.includes("eufundingme profile --query")) {
  throw new Error("Expected profile command instructions to be present");
}
if (!handoffInstructions.value.includes("INDEX_NOT_READY")) {
  throw new Error("Expected stable error code guidance to be present");
}
if (fetchCalls.some((call) => call.url === "/api/match")) {
  throw new Error("Agent handoff should not trigger match requests on load");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr
