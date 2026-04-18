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
    this.dataset = {{}};
    this.classList = {{
      _values: new Set(),
      add: (...tokens) => {{
        for (const token of tokens) {{
          this.classList._values.add(token);
        }}
      }},
      remove: (...tokens) => {{
        for (const token of tokens) {{
          this.classList._values.delete(token);
        }}
      }},
      contains: (token) => this.classList._values.has(token),
      toggle: (token, force) => {{
        if (force === undefined) {{
          if (this.classList._values.has(token)) {{
            this.classList._values.delete(token);
            return false;
          }}
          this.classList._values.add(token);
          return true;
        }}
        if (force) {{
          this.classList._values.add(token);
          return true;
        }}
        this.classList._values.delete(token);
        return false;
      }},
    }};
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

  select() {{
    this.selected = true;
  }}

  setAttribute(name, value) {{
    this[name] = String(value);
  }}

  removeAttribute(name) {{
    delete this[name];
  }}
}}

const elements = new Map();
const selectorIds = [
  "match-form",
  "company-description",
  "company-website-url",
  "match-button",
  "generate-description",
  "quick-fill-openai",
  "form-feedback",
  "dashboard-total-grants",
  "dashboard-programmes",
  "dashboard-budget",
  "dashboard-deadline",
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
  "comparison-panel",
  "comparison-empty",
  "comparison-table",
  "alert-form",
  "alert-email",
  "alert-status",
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

const consoleErrors = [];
const consoleWarnings = [];
const consoleMock = {{
  ...console,
  error(...args) {{
    consoleErrors.push(args);
  }},
  warn(...args) {{
    consoleWarnings.push(args);
  }},
}};

const clipboardWrites = [];
const openedWindows = [];
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
const websiteProfileResolvers = [];
const detailResponses = new Map();
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
let briefResponse = {{
  ok: true,
  json: async () => ({{
    markdown: "# Brief",
    html: "<article>Brief</article>",
    sections: {{
      company_fit_summary: "Strong fit",
      key_requirements: ["Requirement 1"],
      suggested_consortium_partners: ["Partner 1"],
      timeline: ["Week 1"],
      risks_and_gaps: ["Risk 1"],
    }},
  }}),
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
  if (url === "/api/profile/from-website") {{
    if (!websiteProfileResolvers.length) {{
      throw new Error("No website profile resolver queued");
    }}
    return websiteProfileResolvers.shift()(url, options);
  }}
  if (url === "/api/match") {{
    return matchResponse;
  }}
  if (url === "/api/application-brief") {{
    return briefResponse;
  }}
  if (detailResponses.has(url)) {{
    return detailResponses.get(url);
  }}
  throw new Error(`Unhandled fetch: ${{url}}`);
}}

const context = {{
  console: consoleMock,
  document,
  fetch: fetchMock,
  navigator,
  window: {{
    setTimeout: setTimeoutMock,
    clearTimeout: clearTimeoutMock,
    navigator,
    open() {{
      const popup = {{
        html: "",
        printCalled: false,
        document: {{
          write(value) {{
            popup.html += value;
          }},
          close() {{}},
        }},
        print() {{
          popup.printCalled = true;
        }},
      }};
      openedWindows.push(popup);
      return popup;
    }},
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
const websiteInput = elements.get("company-website-url");
const matchButton = elements.get("match-button");
const generateDescriptionButton = elements.get("generate-description");
const quickFillButton = elements.get("quick-fill-openai");
const handoffCopyButton = elements.get("agent-handoff-copy");
const handoffStatus = elements.get("agent-handoff-status");
const handoffInstructions = elements.get("agent-handoff-instructions");
const resolutionBanner = elements.get("resolution-banner");
const resultsEmpty = elements.get("results-empty");
const resultsList = elements.get("results-list");
const resultsMeta = elements.get("results-meta");
const comparisonPanel = elements.get("comparison-panel");
const comparisonEmpty = elements.get("comparison-empty");
const comparisonTable = elements.get("comparison-table");
const alertForm = elements.get("alert-form");
const alertEmail = elements.get("alert-email");
const alertStatus = elements.get("alert-status");
const formFeedback = elements.get("form-feedback");

function queueProfileResponse(factory) {{
  profileResolvers.push(factory);
}}

function queueWebsiteProfileResponse(factory) {{
  websiteProfileResolvers.push(factory);
}}

function queueDetailResponse(topicId, payload) {{
  detailResponses.set(
    `/api/grants/${{topicId}}`,
    {{
      ok: true,
      json: async () => payload,
    }},
  );
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


def test_frontend_locks_website_generation_when_description_is_manual_and_unlocks_on_clear():
    script = build_frontend_harness(
        """
websiteInput.value = "sentry.io";
await websiteInput.dispatch("input");

descriptionInput.value = "We build AI safety tooling for enterprise deployment across Europe.";
await descriptionInput.dispatch("input");

if (!websiteInput.disabled) {
  throw new Error("Expected website input to be disabled when description is manual");
}
if (!generateDescriptionButton.disabled) {
  throw new Error("Expected generate button to be disabled when description is manual");
}

descriptionInput.value = "";
await descriptionInput.dispatch("input");

if (websiteInput.disabled) {
  throw new Error("Expected website input to re-enable after clearing description");
}
if (generateDescriptionButton.disabled) {
  throw new Error("Expected generate button to enable when website URL is present and description is empty");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_enables_generate_button_when_website_url_has_content_and_description_is_empty():
    script = build_frontend_harness(
        """
websiteInput.value = "https://example.com";
await websiteInput.dispatch("input");

if (websiteInput.disabled) {
  throw new Error("Expected website input to remain enabled with an empty description");
}
if (generateDescriptionButton.disabled) {
  throw new Error("Expected generate button to enable when website URL has content");
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


def test_frontend_generate_description_populates_description_and_shows_success_state():
    script = build_frontend_harness(
        """
queueWebsiteProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "Sentry builds developer observability tooling.",
    display_name: "Sentry",
    source: "website_profile",
    normalized_url: "https://sentry.io",
    message: null,
  }),
);

websiteInput.value = "sentry.io";
await websiteInput.dispatch("input");
await generateDescriptionButton.dispatch("click");

const websiteCalls = fetchCalls.filter((call) => call.url === "/api/profile/from-website");
if (websiteCalls.length !== 1) {
  throw new Error(`Expected 1 website profile call, got ${websiteCalls.length}`);
}

const requestBody = JSON.parse(websiteCalls[0].options.body);
if (requestBody.url !== "sentry.io") {
  throw new Error(`Unexpected website request body: ${requestBody.url}`);
}
if (descriptionInput.value !== "Sentry builds developer observability tooling.") {
  throw new Error(`Generate flow did not populate description: ${descriptionInput.value}`);
}
if (!websiteInput.disabled) {
  throw new Error("Expected website input to lock after generating a description");
}
if (!generateDescriptionButton.disabled) {
  throw new Error("Expected generate button to lock after generating a description");
}
if (formFeedback.hidden) {
  throw new Error("Expected success feedback to be visible");
}
if (!formFeedback.textContent.includes("generated from website")) {
  throw new Error(`Unexpected success feedback: ${formFeedback.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_generate_description_failure_keeps_description_and_shows_error():
    script = build_frontend_harness(
        """
queueWebsiteProfileResponse(async () => ({
  ok: false,
  json: async () => ({
    detail: {
      message: "website profile generation failed",
    },
  }),
}));

descriptionInput.value = "Existing manual description.";
websiteInput.value = "sentry.io";
await websiteInput.dispatch("input");
await generateDescriptionButton.dispatch("click");

const websiteCalls = fetchCalls.filter((call) => call.url === "/api/profile/from-website");
if (websiteCalls.length !== 1) {
  throw new Error(`Expected 1 website profile call, got ${websiteCalls.length}`);
}
if (descriptionInput.value !== "Existing manual description.") {
  throw new Error(`Failure flow overwrote description: ${descriptionInput.value}`);
}
if (websiteInput.disabled) {
  throw new Error("Expected website input to remain editable after failure");
}
if (generateDescriptionButton.disabled) {
  throw new Error("Expected generate button to be re-enabled after failure");
}
if (formFeedback.hidden) {
  throw new Error("Expected error feedback to be visible");
}
if (!formFeedback.classList.contains("is-error")) {
  throw new Error("Expected error feedback to use error styling");
}
if (!formFeedback.textContent.includes("website profile generation failed")) {
  throw new Error(`Unexpected error feedback: ${formFeedback.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_empty_submit_shows_validation_feedback_without_api_calls():
    script = build_frontend_harness(
        """
await form.dispatch("submit");

const actionCalls = fetchCalls.filter((call) =>
  ["/api/profile/resolve", "/api/match"].includes(call.url)
);
if (actionCalls.length !== 0) {
  throw new Error(`Expected no action calls, got ${actionCalls.length}`);
}
if (resolutionBanner.hidden) {
  throw new Error("Expected validation banner to be visible");
}
if (!resolutionBanner.textContent.includes("Add a company name")) {
  throw new Error(`Unexpected validation banner copy: ${resolutionBanner.textContent}`);
}
if (!resultsEmpty.textContent.includes("Add a company name")) {
  throw new Error(`Unexpected empty state copy: ${resultsEmpty.textContent}`);
}
if (resultsMeta.textContent !== "No results available.") {
  throw new Error(`Unexpected results meta: ${resultsMeta.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_reuses_one_request_id_across_journey_calls():
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

appContext.renderResults([
  {
    grant_id: "TOPIC-1",
    title: "AI Grant",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-1",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
  }
], 42);

await quickFillButton.dispatch("click");
descriptionInput.value = "OpenAI";
await form.dispatch("submit");
await appContext.exportApplicationBrief("TOPIC-1");

const interestingCalls = fetchCalls.filter((call) =>
  ["/api/profile/resolve", "/api/match", "/api/application-brief"].includes(call.url)
);
if (interestingCalls.length !== 3) {
  throw new Error(`Expected 3 correlated calls, got ${interestingCalls.length}`);
}
const requestIds = interestingCalls.map((call) => call.options.headers["X-Request-ID"]);
if (requestIds.some((value) => typeof value !== "string" || !value.length)) {
  throw new Error(`Missing journey request IDs: ${JSON.stringify(requestIds)}`);
}
if (new Set(requestIds).size !== 1) {
  throw new Error(`Expected one journey request ID, got ${JSON.stringify(requestIds)}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_starts_new_request_id_for_new_search_journey():
    script = build_frontend_harness(
        """
queueProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "OpenAI full profile one.",
    display_name: "OpenAI",
    source: "demo_profile",
    message: null,
  }),
);
descriptionInput.value = "OpenAI";
await form.dispatch("submit");

queueProfileResponse(
  profileJsonResponse({
    resolved: true,
    profile: "Doctolib full profile two.",
    display_name: "Doctolib",
    source: "demo_profile",
    message: null,
  }),
);
descriptionInput.value = "Doctolib";
await form.dispatch("submit");

const matchCalls = fetchCalls.filter((call) => call.url === "/api/match");
if (matchCalls.length !== 2) {
  throw new Error(`Expected 2 match calls, got ${matchCalls.length}`);
}
const ids = matchCalls.map((call) => call.options.headers["X-Request-ID"]);
if (ids.some((value) => typeof value !== "string" || !value.length)) {
  throw new Error(`Missing journey IDs: ${JSON.stringify(ids)}`);
}
if (ids[0] === ids[1]) {
  throw new Error(`Expected new journey ID for second search, got ${JSON.stringify(ids)}`);
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


def test_frontend_labels_live_retrieval_source_when_snapshot_absent():
    script = build_frontend_harness(
        """
statusResponse = {
  ok: true,
  json: async () => ({
    phase: "idle",
    message: "Live retrieval ready",
    indexed_grants: 0,
    scanned_prefixes: 0,
    total_prefixes: 0,
    failed_prefixes: 0,
    truncated_prefixes: 0,
    embeddings_ready: false,
    embeddings_available: true,
    ai_scoring_available: true,
    live_retrieval_available: true,
    matching_available: false,
    coverage_complete: false,
    degraded: false,
    degradation_reasons: [],
    snapshot_loaded: false,
    snapshot_source: null,
    refresh_in_progress: false,
    current_prefix: null,
    current_page: null,
    last_progress_at: null,
    snapshot_age_seconds: null,
  }),
};

appContext.updateStatus(await statusResponse.json());

if (elements.get("status-source").textContent !== "live retrieval") {
  throw new Error(`Unexpected source label: ${elements.get("status-source").textContent}`);
}
if (elements.get("status-embeddings").textContent !== "on-demand") {
  throw new Error(`Unexpected embeddings label: ${elements.get("status-embeddings").textContent}`);
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


def test_frontend_renders_dashboard_summary_from_status():
    script = build_frontend_harness(
        """
statusResponse = {
  ok: true,
  json: async () => ({
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
    summary: {
      total_grants: 42,
      programme_count: 5,
      total_budget_display: "EUR 380M",
      closest_deadline_days: 3,
    },
  }),
};

appContext.updateStatus(await statusResponse.json());

if (elements.get("dashboard-total-grants").textContent !== "42 grants indexed") {
  throw new Error(`Unexpected grants summary: ${elements.get("dashboard-total-grants").textContent}`);
}
if (elements.get("dashboard-programmes").textContent !== "5 programmes") {
  throw new Error(`Unexpected programme summary: ${elements.get("dashboard-programmes").textContent}`);
}
if (elements.get("dashboard-budget").textContent !== "EUR 380M total available") {
  throw new Error(`Unexpected budget summary: ${elements.get("dashboard-budget").textContent}`);
}
if (elements.get("dashboard-deadline").textContent !== "Closest deadline: 3 days") {
  throw new Error(`Unexpected deadline summary: ${elements.get("dashboard-deadline").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_prefers_live_refresh_count_over_seed_snapshot_count():
    script = build_frontend_harness(
        """
const status = {
  phase: "ready_degraded",
  message: "Using bundled seed snapshot while live refresh runs",
  indexed_grants: 2,
  refresh_indexed_grants: 44,
  scanned_prefixes: 4,
  total_prefixes: 46,
  failed_prefixes: 0,
  truncated_prefixes: 0,
  embeddings_ready: false,
  matching_available: true,
  coverage_complete: false,
  degraded: true,
  degradation_reasons: ["bundled_seed_mode"],
  snapshot_loaded: true,
  snapshot_source: "bundled",
  refresh_in_progress: true,
  summary: {
    total_grants: 2,
    programme_count: 2,
    total_budget_display: "EUR 9M",
    closest_deadline_days: 7,
  },
};

appContext.updateStatus(status);

if (elements.get("status-count").textContent !== "44") {
  throw new Error(`Unexpected live status count: ${elements.get("status-count").textContent}`);
}
if (elements.get("dashboard-total-grants").textContent !== "44 grants found so far") {
  throw new Error(`Unexpected dashboard grants copy: ${elements.get("dashboard-total-grants").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_surfaces_live_refresh_progress_before_it_surpasses_seed_snapshot():
    script = build_frontend_harness(
        """
const status = {
  phase: "ready_degraded",
  message: "Using bundled seed snapshot while live refresh runs",
  indexed_grants: 44,
  refresh_indexed_grants: 10,
  scanned_prefixes: 0,
  total_prefixes: 46,
  failed_prefixes: 0,
  truncated_prefixes: 0,
  embeddings_ready: false,
  matching_available: true,
  coverage_complete: false,
  degraded: true,
  degradation_reasons: ["bundled_seed_mode"],
  snapshot_loaded: true,
  snapshot_source: "bundled",
  refresh_in_progress: true,
  summary: {
    total_grants: 44,
    programme_count: 8,
    total_budget_display: "EUR 380M",
    closest_deadline_days: 3,
  },
};

appContext.updateStatus(status);

if (elements.get("status-count").textContent !== "44") {
  throw new Error(`Unexpected visible indexed count: ${elements.get("status-count").textContent}`);
}
if (elements.get("dashboard-total-grants").textContent !== "44 grants indexed · 10 found in live refresh") {
  throw new Error(`Unexpected dashboard grants copy: ${elements.get("dashboard-total-grants").textContent}`);
}
if (elements.get("status-refresh").textContent !== "refreshing in background · 10 found so far") {
  throw new Error(`Unexpected refresh progress copy: ${elements.get("status-refresh").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_calls_out_lexical_only_mode_as_lower_confidence():
    script = build_frontend_harness(
        """
const status = {
  phase: "ready_degraded",
  message: "Index ready with degraded coverage or matching quality",
  indexed_grants: 44,
  refresh_indexed_grants: 44,
  scanned_prefixes: 46,
  total_prefixes: 46,
  failed_prefixes: 0,
  truncated_prefixes: 0,
  embeddings_ready: false,
  matching_available: true,
  coverage_complete: true,
  degraded: true,
  degradation_reasons: ["lexical_only_mode"],
  snapshot_loaded: false,
  snapshot_source: null,
  refresh_in_progress: false,
  summary: {
    total_grants: 44,
    programme_count: 8,
    total_budget_display: "EUR 380M",
    closest_deadline_days: 3,
  },
};

appContext.updateStatus(status);

if (elements.get("status-embeddings").textContent !== "keyword-only") {
  throw new Error(`Unexpected embeddings label: ${elements.get("status-embeddings").textContent}`);
}
if (elements.get("status-degraded").hidden) {
  throw new Error("Expected degraded banner to be visible");
}
if (!elements.get("status-degraded").textContent.includes("Keyword-only matching is active")) {
  throw new Error(`Unexpected degraded copy: ${elements.get("status-degraded").textContent}`);
}
if (!elements.get("submit-hint").textContent.includes("keyword-based")) {
  throw new Error(`Unexpected submit hint: ${elements.get("submit-hint").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_describes_bundled_snapshot_as_cached_data():
    script = build_frontend_harness(
        """
const status = {
  phase: "ready_degraded",
  message: "Index ready with degraded coverage or matching quality",
  indexed_grants: 44,
  refresh_indexed_grants: 44,
  scanned_prefixes: 46,
  total_prefixes: 46,
  failed_prefixes: 0,
  truncated_prefixes: 0,
  embeddings_ready: false,
  matching_available: true,
  coverage_complete: true,
  degraded: true,
  degradation_reasons: ["bundled_seed_mode"],
  snapshot_loaded: true,
  snapshot_source: "bundled",
  snapshot_age_seconds: 120,
  refresh_in_progress: true,
  summary: {
    total_grants: 44,
    programme_count: 8,
    total_budget_display: "EUR 380M",
    closest_deadline_days: 3,
  },
};

appContext.updateStatus(status);

if (!elements.get("status-copy").textContent.includes("Running with cached data")) {
  throw new Error(`Unexpected cached-data status copy: ${elements.get("status-copy").textContent}`);
}
if (!elements.get("submit-hint").textContent.includes("Bundled snapshot")) {
  throw new Error(`Unexpected cached-data submit hint: ${elements.get("submit-hint").textContent}`);
}
if (elements.get("status-degraded").textContent.startsWith("Degraded")) {
  throw new Error(`Expected non-degraded banner copy: ${elements.get("status-degraded").textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_shows_no_reliable_keyword_matches_copy_in_lexical_mode():
    script = build_frontend_harness(
        """
appContext.renderResults([], 44, {
  degradation_reasons: ["lexical_only_mode"],
});

if (!resultsEmpty.textContent.includes("No reliable keyword matches yet")) {
  throw new Error(`Unexpected lexical empty state: ${resultsEmpty.textContent}`);
}
if (!resultsMeta.textContent.includes("Keyword-only fallback is active")) {
  throw new Error(`Unexpected lexical meta copy: ${resultsMeta.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_describes_live_result_source_in_results_meta():
    script = build_frontend_harness(
        """
appContext.renderResults(
  [
    {
      grant_id: "TOPIC-1",
      title: "Live grant",
      status: "Open",
      portal_url: "https://example.com/TOPIC-1",
      fit_score: 88,
      why_match: "Strong live fit",
      application_angle: "Lead with deployment",
      keywords: ["ai"],
    }
  ],
  18,
  {
    result_source: "live_retrieval",
    degradation_reasons: [],
  },
);

if (!resultsMeta.textContent.includes("from 18 live candidates")) {
  throw new Error(`Unexpected live results meta: ${resultsMeta.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_fetches_grant_details_and_caches_repeat_expansions():
    script = build_frontend_harness(
        """
appContext.renderResults([
  {
    grant_id: "TOPIC-1",
    title: "AI Grant",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-1",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
  }
], 42);

queueDetailResponse("TOPIC-1", {
  topicDetails: {
    summary: { identifier: "TOPIC-1", deadlineDate: "2026-08-01T17:00:00Z" },
    sections: {
      objective: "<p>Detailed grant description.</p>",
      expectedOutcomes: ["<p>Outcome A</p>"],
      eligibilityConditions: "<ul><li>EU entity</li></ul>",
      documents: [{ title: "Guide", url: "https://example.com/guide.pdf" }],
      partnerSearch: true,
    },
  },
});

await appContext.toggleGrantDetails("TOPIC-1");
await appContext.toggleGrantDetails("TOPIC-1");
await appContext.toggleGrantDetails("TOPIC-1");

const detailCalls = fetchCalls.filter((call) => call.url === "/api/grants/TOPIC-1");
if (detailCalls.length !== 1) {
  throw new Error(`Expected one topic detail fetch, got ${detailCalls.length}`);
}
if (!resultsList.innerHTML.includes("Detailed grant description.")) {
  throw new Error(`Expected detail content in results markup: ${resultsList.innerHTML}`);
}
if (!resultsList.innerHTML.includes("EU entity")) {
  throw new Error(`Expected eligibility content in results markup: ${resultsList.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_renders_translation_note_on_results_and_details():
    script = build_frontend_harness(
        """
appContext.renderResults([
  {
    grant_id: "TOPIC-BG",
    title: "National innovation programme",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-BG",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
    source_language: "bg",
    translated_from_source: true,
    translation_note: "Translated from Bulgarian. This grant appears tied to Bulgaria.",
  }
], 42);

queueDetailResponse("TOPIC-BG", {
  grant_id: "TOPIC-BG",
  full_description: "Detailed English description.",
  eligibility_criteria: ["Bulgarian legal entities"],
  submission_deadlines: [{ label: "Main deadline", value: "2026-08-01" }],
  expected_outcomes: ["Support for SMEs"],
  documents: [],
  source: "topic_detail_json",
  fallback_used: false,
  source_language: "bg",
  translated_from_source: true,
  translation_note: "Translated from Bulgarian. This grant appears tied to Bulgaria.",
});
await appContext.toggleGrantDetails("TOPIC-BG");

if (!resultsList.innerHTML.includes("Translated from Bulgarian")) {
  throw new Error(`Expected translation note in result markup: ${resultsList.innerHTML}`);
}
if (!resultsList.innerHTML.includes("This grant appears tied to Bulgaria")) {
  throw new Error(`Expected country note in result markup: ${resultsList.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_limits_comparison_mode_to_three_grants():
    script = build_frontend_harness(
        """
const results = [
  { grant_id: "TOPIC-1", title: "Grant 1", status: "Open", portal_url: "https://example.com/1", fit_score: 91, why_match: "Fit 1", application_angle: "Angle 1", keywords: [], budget: "EUR 5M", deadline: "2026-08-01", days_left: 20, framework_programme: "Horizon", programme_division: "Cluster 4" },
  { grant_id: "TOPIC-2", title: "Grant 2", status: "Open", portal_url: "https://example.com/2", fit_score: 81, why_match: "Fit 2", application_angle: "Angle 2", keywords: [], budget: "EUR 4M", deadline: "2026-08-02", days_left: 21, framework_programme: "LIFE", programme_division: "Climate" },
  { grant_id: "TOPIC-3", title: "Grant 3", status: "Open", portal_url: "https://example.com/3", fit_score: 71, why_match: "Fit 3", application_angle: "Angle 3", keywords: [], budget: "EUR 3M", deadline: "2026-08-03", days_left: 22, framework_programme: "Digital", programme_division: "AI" },
  { grant_id: "TOPIC-4", title: "Grant 4", status: "Open", portal_url: "https://example.com/4", fit_score: 61, why_match: "Fit 4", application_angle: "Angle 4", keywords: [], budget: "EUR 2M", deadline: "2026-08-04", days_left: 23, framework_programme: "CERV", programme_division: "Rights" },
];
appContext.renderResults(results, 42);
appContext.toggleComparisonGrant("TOPIC-1");
appContext.toggleComparisonGrant("TOPIC-2");
appContext.toggleComparisonGrant("TOPIC-3");
appContext.toggleComparisonGrant("TOPIC-4");

if (!comparisonTable.innerHTML.includes("Grant 1") || !comparisonTable.innerHTML.includes("Grant 3")) {
  throw new Error(`Expected first three grants in comparison: ${comparisonTable.innerHTML}`);
}
if (comparisonTable.innerHTML.includes("Grant 4")) {
  throw new Error(`Expected comparison cap at three grants: ${comparisonTable.innerHTML}`);
}
if (comparisonEmpty.hidden !== true) {
  throw new Error("Expected empty comparison state to be hidden");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_renders_corner_remove_toggle_for_favorites():
    script = build_frontend_harness(
        """
const results = [
  { grant_id: "TOPIC-1", title: "Grant 1", status: "Open", portal_url: "https://example.com/1", fit_score: 91, why_match: "Fit 1", application_angle: "Angle 1", keywords: [], budget: "EUR 5M", deadline: "2026-08-01", days_left: 20, framework_programme: "Horizon", programme_division: "Cluster 4" },
  { grant_id: "TOPIC-2", title: "Grant 2", status: "Open", portal_url: "https://example.com/2", fit_score: 81, why_match: "Fit 2", application_angle: "Angle 2", keywords: [], budget: "EUR 4M", deadline: "2026-08-02", days_left: 21, framework_programme: "LIFE", programme_division: "Climate" },
];
appContext.renderResults(results, 42);
appContext.toggleComparisonGrant("TOPIC-1");
appContext.toggleComparisonGrant("TOPIC-2");

if (!comparisonTable.innerHTML.includes("comparison-remove-button")) {
  throw new Error(`Expected remove button in favorites card: ${comparisonTable.innerHTML}`);
}
if (!comparisonTable.innerHTML.includes("Remove Grant 1 from favorites")) {
  throw new Error(`Expected accessible remove label in favorites card: ${comparisonTable.innerHTML}`);
}

appContext.toggleComparisonGrant("TOPIC-1");

if (comparisonTable.innerHTML.includes("Grant 1")) {
  throw new Error(`Expected Grant 1 to be removed from favorites: ${comparisonTable.innerHTML}`);
}
if (!comparisonTable.innerHTML.includes("Grant 2")) {
  throw new Error(`Expected Grant 2 to remain in favorites: ${comparisonTable.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_validates_alert_signup_without_backend():
    script = build_frontend_harness(
        """
alertEmail.value = "not-an-email";
await alertForm.dispatch("submit");
if (!alertStatus.textContent.includes("Enter a valid email")) {
  throw new Error(`Expected validation error, got: ${alertStatus.textContent}`);
}

alertEmail.value = "founder@example.com";
await alertForm.dispatch("submit");
if (!alertStatus.textContent.includes("Alerts coming soon")) {
  throw new Error(`Expected success message, got: ${alertStatus.textContent}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_exports_application_brief_to_print_window():
    script = build_frontend_harness(
        """
appContext.renderResults([
  {
    grant_id: "TOPIC-1",
    title: "AI Grant",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-1",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
  }
], 42);
descriptionInput.value = "We build AI tools for industrial companies.";
appContext.grantDetailsById.set("TOPIC-1", {
  grant_id: "TOPIC-1",
  full_description: "Detailed description",
  eligibility_criteria: ["EU legal entity"],
  submission_deadlines: [{ label: "Main deadline", value: "2026-08-01" }],
  expected_outcomes: ["Outcome A"],
  documents: [],
  partner_search_available: true,
  source: "browser_topic_detail",
  fallback_used: false,
});

await appContext.exportApplicationBrief("TOPIC-1");

const briefCalls = fetchCalls.filter((call) => call.url === "/api/application-brief");
if (briefCalls.length !== 1) {
  throw new Error(`Expected one brief request, got ${briefCalls.length}`);
}
const briefPayload = JSON.parse(briefCalls[0].options.body);
if (briefPayload.company_description !== "We build AI tools for industrial companies.") {
  throw new Error(`Unexpected company description: ${briefPayload.company_description}`);
}
if (briefPayload.match_result.portal_url !== "https://example.com/TOPIC-1") {
  throw new Error(`Expected portal_url in match_result: ${JSON.stringify(briefPayload.match_result)}`);
}
if (briefPayload.match_result.why_match !== "Strong fit") {
  throw new Error(`Expected why_match in match_result: ${JSON.stringify(briefPayload.match_result)}`);
}
if (briefPayload.match_result.application_angle !== "Lead with deployment") {
  throw new Error(`Expected application_angle in match_result: ${JSON.stringify(briefPayload.match_result)}`);
}
if (briefPayload.grant_detail.full_description !== "Detailed description") {
  throw new Error(`Expected grant_detail payload: ${JSON.stringify(briefPayload.grant_detail)}`);
}
if (openedWindows.length !== 1) {
  throw new Error(`Expected one export window, got ${openedWindows.length}`);
}
if (!openedWindows[0].html.includes("Brief")) {
  throw new Error(`Expected brief HTML in export window: ${openedWindows[0].html}`);
}
if (!openedWindows[0].printCalled) {
  throw new Error("Expected print() to be called for export");
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_logs_resolution_failures_before_fallback():
    script = build_frontend_harness(
        """
queueProfileResponse(async () => {
  throw new Error("resolver down");
});

descriptionInput.value = "OpenAI";
await descriptionInput.dispatch("input");
await flushTimers(1);
await flushTimers(2);

if (consoleErrors.length !== 1) {
  throw new Error(`Expected one console.error call, got ${consoleErrors.length}`);
}
if (!String(consoleErrors[0][0]).includes("resolver down")) {
  throw new Error(`Unexpected logged error: ${consoleErrors[0][0]}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_logs_grant_detail_failures_before_fallback():
    script = build_frontend_harness(
        """
appContext.renderResults([
  {
    grant_id: "TOPIC-1",
    title: "AI Grant",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-1",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
  }
], 42);

detailResponses.set("/api/grants/TOPIC-1", {
  ok: false,
  json: async () => ({})
});
detailResponses.set(
  "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/TOPIC-1.json",
  {
    ok: false,
    json: async () => ({}),
  },
);

await appContext.toggleGrantDetails("TOPIC-1");

if (consoleErrors.length !== 1) {
  throw new Error(`Expected one console.error call, got ${consoleErrors.length}`);
}
if (!String(consoleErrors[0][0]).includes("Could not load topic detail")) {
  throw new Error(`Unexpected logged error: ${consoleErrors[0][0]}`);
}
if (!resultsList.innerHTML.includes("Not available")) {
  throw new Error(`Expected fallback details to render: ${resultsList.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr


def test_frontend_fetches_topic_detail_from_browser_when_backend_fails():
    script = build_frontend_harness(
        """
appContext.renderResults([
  {
    grant_id: "TOPIC-1",
    title: "AI Grant",
    status: "Open",
    deadline: "2026-08-01",
    days_left: 20,
    budget: "EUR 5M",
    portal_url: "https://example.com/TOPIC-1",
    fit_score: 90,
    why_match: "Strong fit",
    application_angle: "Lead with deployment",
    framework_programme: "Horizon Europe",
    programme_division: "Cluster 4",
    keywords: ["ai"],
  }
], 42);

detailResponses.set("/api/grants/TOPIC-1", {
  ok: false,
  json: async () => ({})
});
detailResponses.set(
  "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/TOPIC-1.json",
  {
    ok: true,
    json: async () => ({
      topicDetails: {
        summary: { identifier: "TOPIC-1", deadlineDate: "2026-08-01T17:00:00Z" },
        sections: {
          objective: "<p>Detailed grant description.</p>",
          expectedOutcomes: ["<p>Outcome A</p>"],
          eligibilityConditions: "<ul><li>EU entity</li></ul>",
          documents: [{ title: "Guide", url: "https://example.com/guide.pdf" }],
          partnerSearch: true,
        },
      },
    }),
  },
);

await appContext.toggleGrantDetails("TOPIC-1");

if (!resultsList.innerHTML.includes("Detailed grant description.")) {
  throw new Error(`Expected browser detail content in results markup: ${resultsList.innerHTML}`);
}
if (!resultsList.innerHTML.includes("EU entity")) {
  throw new Error(`Expected browser eligibility content in results markup: ${resultsList.innerHTML}`);
}
if (resultsList.innerHTML.includes("No expanded description available yet.")) {
  throw new Error(`Expected browser detail fetch to avoid generic fallback: ${resultsList.innerHTML}`);
}
"""
    )

    result = run_frontend_script_test(script)

    assert result.returncode == 0, result.stderr
