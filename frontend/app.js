const DEFAULT_TITLE = "EU Grant Matcher";
const DEFAULT_EMPTY_STATE =
  "The top matches will appear here with fit scores, rationale, and the angle to take in the application.";
const MIN_DESCRIPTION_LENGTH = 20;
const PROFILE_RESOLVE_DEBOUNCE_MS = 450;
const MAX_COMPARISON_GRANTS = 3;

const form = document.querySelector("#match-form");
const descriptionInput = document.querySelector("#company-description");
const websiteUrlInput = document.querySelector("#company-website-url");
const matchButton = document.querySelector("#match-button");
const generateDescriptionButton = document.querySelector("#generate-description");
const quickFillOpenAIButton = document.querySelector("#quick-fill-openai");
const agentHandoffCopyButton = document.querySelector("#agent-handoff-copy");
const agentHandoffStatus = document.querySelector("#agent-handoff-status");
const agentHandoffDisclosure = document.querySelector("#agent-handoff-disclosure");
const agentHandoffInstructions = document.querySelector("#agent-handoff-instructions");
const formFeedback = document.querySelector("#form-feedback");
const submitHint = document.querySelector("#submit-hint");
const statusCopy = document.querySelector("#status-copy");
const statusBar = document.querySelector("#status-bar");
const statusPhase = document.querySelector("#status-phase");
const statusCount = document.querySelector("#status-count");
const statusPrefixes = document.querySelector("#status-prefixes");
const statusFailures = document.querySelector("#status-failures");
const statusCoverage = document.querySelector("#status-coverage");
const statusEmbeddings = document.querySelector("#status-embeddings");
const statusSource = document.querySelector("#status-source");
const statusRefresh = document.querySelector("#status-refresh");
const statusProgress = document.querySelector("#status-progress");
const statusUpdated = document.querySelector("#status-updated");
const statusDegraded = document.querySelector("#status-degraded");
const resolutionBanner = document.querySelector("#resolution-banner");
const resultsRegion = document.querySelector("#results-region");
const resultsEmpty = document.querySelector("#results-empty");
const resultsList = document.querySelector("#results-list");
const resultsMeta = document.querySelector("#results-meta");
const dashboardTotalGrants = document.querySelector("#dashboard-total-grants");
const dashboardProgrammes = document.querySelector("#dashboard-programmes");
const dashboardBudget = document.querySelector("#dashboard-budget");
const dashboardDeadline = document.querySelector("#dashboard-deadline");
const comparisonPanel = document.querySelector("#comparison-panel");
const comparisonEmpty = document.querySelector("#comparison-empty");
const comparisonTable = document.querySelector("#comparison-table");
const alertForm = document.querySelector("#alert-form");
const alertEmail = document.querySelector("#alert-email");
const alertStatus = document.querySelector("#alert-status");

let latestStatus = null;
let latestResults = [];
let statusPollHandle = null;
let statusPollInFlight = false;
let consecutiveStatusFailures = 0;
let resolveDebounceHandle = null;
let inFlightPreResolveQuery = "";
let lastPreResolvedQuery = "";
let latestResolveToken = 0;
let currentJourneyRequestId = null;
let currentJourneySeed = null;
let latestMatchMeta = null;
const resultsById = new Map();
const grantDetailsById = new Map();
const loadingGrantIds = new Set();
const expandedGrantIds = new Set();
const comparisonGrantIds = [];

const AGENT_HANDOFF_INSTRUCTIONS = `Act as an autonomous shell agent for this repository.

Goal:
- Set up and use the eufundingme CLI tool from a fresh environment.
- Prefer machine-readable JSON output.
- Preserve and report request_id values in downstream summaries.

Execution order:
1. Enter the project repository root.
2. Create and activate the virtual environment:
   python -m venv .venv
   . .venv/bin/activate
3. Install dependencies and the CLI entrypoint:
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt pytest
   python -m pip install -e .
4. Verify the tool is installed:
   eufundingme --help
5. Run a lightweight preflight check:
   eufundingme health
   If that fails, run:
   python -m backend.cli health
6. Check index readiness:
   eufundingme status
7. If you only have a short company name, optionally expand it first:
   eufundingme profile --query "<company>"
8. Run the match command with the full company description:
   eufundingme match --description "<company description>"
   Fallback if the installed command is unavailable:
   python -m backend.cli match --description "<company description>"

Machine contract:
- Default output is JSON.
- Successful and error responses include request_id for tracing.
- Treat INDEX_NOT_READY and MATCH_TIMEOUT as intentional automation signals.
- Surface INTERNAL_ERROR verbatim if it occurs.

Success criteria:
- Return the ranked grant results.
- Include the request_id in your final report.
- If the command fails, report the exact error code and message verbatim.`;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function urgencyMarkup(daysLeft) {
  if (daysLeft === null || daysLeft === undefined) {
    return "";
  }
  if (daysLeft <= 14) {
    return `<span class="urgency is-soon">${daysLeft} days left</span>`;
  }
  return `<span class="urgency">${daysLeft} days left</span>`;
}

function getScoreChipClass(fitScore) {
  if (fitScore >= 70) {
    return "score-chip score-chip--high";
  }
  if (fitScore >= 40) {
    return "score-chip score-chip--medium";
  }
  return "score-chip score-chip--low";
}

function updateDocumentTitle(resultCount = 0) {
  document.title = resultCount > 0 ? `${resultCount} Grants Found | ${DEFAULT_TITLE}` : DEFAULT_TITLE;
}

function getEffectiveIndexedGrantCount(status, summary = null) {
  const summaryCount = Number(summary?.total_grants || 0);
  const indexedCount = Number(status?.indexed_grants || 0);
  const refreshCount = Number(status?.refresh_indexed_grants || 0);
  return Math.max(summaryCount, indexedCount, refreshCount);
}

function getRefreshProgressCount(status) {
  return Number(status?.refresh_indexed_grants || 0);
}

function hydrateAgentHandoff() {
  agentHandoffInstructions.value = AGENT_HANDOFF_INSTRUCTIONS;
}

async function copyAgentHandoffInstructions() {
  if (agentHandoffDisclosure) {
    agentHandoffDisclosure.open = true;
  }
  try {
    await navigator.clipboard.writeText(agentHandoffInstructions.value);
    agentHandoffStatus.textContent = "Instructions copied. Paste them into your agent chat.";
  } catch (error) {
    console.error(error);
    agentHandoffStatus.textContent =
      "Copy failed. Select the instructions manually and paste them into your agent chat.";
    agentHandoffInstructions.focus();
    agentHandoffInstructions.select();
  }
}

function showResolutionBanner(text) {
  resolutionBanner.hidden = false;
  resolutionBanner.textContent = text;
}

function hideResolutionBanner() {
  resolutionBanner.hidden = true;
  resolutionBanner.textContent = "";
}

function setFormFeedback(message = "", tone = "info") {
  if (!formFeedback) {
    return;
  }
  if (!message) {
    formFeedback.hidden = true;
    formFeedback.textContent = "";
    formFeedback.classList.remove("is-error");
    return;
  }
  formFeedback.hidden = false;
  formFeedback.textContent = message;
  formFeedback.classList.toggle("is-error", tone === "error");
}

function setDescriptionInvalid(isInvalid) {
  descriptionInput.classList.toggle("is-invalid", isInvalid);
  descriptionInput.setAttribute("aria-invalid", isInvalid ? "true" : "false");
}

function updateWebsiteGenerationControls() {
  if (!websiteUrlInput || !generateDescriptionButton) {
    return;
  }

  const hasManualDescription = Boolean(descriptionInput.value.trim());
  const hasWebsiteUrl = Boolean(websiteUrlInput.value.trim());

  websiteUrlInput.disabled = hasManualDescription;
  generateDescriptionButton.disabled = hasManualDescription || !hasWebsiteUrl;
}

function setResultsBusy(isBusy) {
  if (resultsRegion) {
    resultsRegion.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
}

function buildEmptyStateMarkup({ variant = "intro", title, copy, bullets = [] }) {
  const bulletMarkup = bullets.length
    ? `<ul class="results-empty-list">${bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";

  return `
    ${title ? `<p class="results-empty-title">${escapeHtml(title)}</p>` : ""}
    ${copy ? `<p class="results-empty-copy">${escapeHtml(copy)}</p>` : ""}
    ${bulletMarkup}
  `;
}

function showResultsEmptyState(config) {
  const markup = buildEmptyStateMarkup(config);
  resultsList.innerHTML = "";
  resultsEmpty.hidden = false;
  resultsEmpty.className = `results-empty results-empty--${config.variant || "intro"}`;
  resultsEmpty.innerHTML = markup;
  resultsEmpty.textContent = [config.title, config.copy, ...(config.bullets || [])].filter(Boolean).join(" ");
}

function showIntroResultsState(message = DEFAULT_EMPTY_STATE, meta = "No search run yet.") {
  latestMatchMeta = null;
  updateDocumentTitle();
  setResultsBusy(false);
  showResultsEmptyState({
    variant: "intro",
    title: "Ready to shortlist grants",
    copy: message,
    bullets: [
      "Paste a company description or try the OpenAI demo profile.",
      "Matching will rank the strongest live opportunities and suggest an application angle.",
    ],
  });
  resultsMeta.textContent = meta;
}

function showLoadingResultsState() {
  setResultsBusy(true);
  showResultsEmptyState({
    variant: "loading",
    title: "Matching grants…",
    copy: "Scoring live programmes against your company profile and preparing judge-ready rationale.",
    bullets: [
      "Ranking by fit score and strategic relevance.",
      "Generating application angles for the strongest opportunities.",
    ],
  });
  resultsMeta.textContent = "Searching the current grant index…";
}

function showMatchFeedback(message) {
  latestMatchMeta = null;
  hideResolutionBanner();
  updateDocumentTitle();
  setResultsBusy(false);
  showResultsEmptyState({
    variant: "error",
    title: "Matching is temporarily unavailable",
    copy: message,
    bullets: [
      "Wait for the index panel to reach ready, then retry.",
      "If you entered only a short company name, add one or two sentences of detail.",
    ],
  });
  resultsEmpty.textContent = message;
  resultsMeta.textContent = "No results available.";
}

function normalizeCompanyNameInput(value) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function createJourneyRequestId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `journey-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildJourneySeed(value) {
  return normalizeCompanyNameInput(value);
}

function ensureJourneyRequestId(seed = null) {
  if (!currentJourneyRequestId || (seed && currentJourneySeed && currentJourneySeed !== seed)) {
    currentJourneyRequestId = createJourneyRequestId();
  }
  if (seed) {
    currentJourneySeed = seed;
  }
  return currentJourneyRequestId;
}

function looksLikeCompanyNameInput(value) {
  const normalizedValue = value.trim();
  if (!normalizedValue) {
    return false;
  }
  if (normalizedValue.length < MIN_DESCRIPTION_LENGTH) {
    return true;
  }

  const words = normalizedValue.split(/\s+/).filter(Boolean);
  return words.length <= 3 && !/[.,;:!?]/.test(normalizedValue);
}

function isMatchingAvailable(status) {
  if (typeof status?.matching_available === "boolean") {
    return status.matching_available;
  }
  return status?.phase === "ready" || status?.phase === "ready_degraded";
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h`;
}

function formatLastProgress(timestamp) {
  if (!timestamp) {
    return "—";
  }
  const progressTime = new Date(timestamp);
  if (Number.isNaN(progressTime.getTime())) {
    return "—";
  }
  const diffSeconds = Math.max(0, Math.round((Date.now() - progressTime.getTime()) / 1000));
  return `${formatDuration(diffSeconds)} ago`;
}

function humanizeReasons(reasons) {
  return (reasons || []).map((reason) => reason.replaceAll("_", " "));
}

function hasReason(reasons, reason) {
  return Array.isArray(reasons) && reasons.includes(reason);
}

function isLexicalOnlyMode(reasons) {
  return hasReason(reasons, "lexical_only_mode");
}

function isBundledSeedMode(reasons) {
  return hasReason(reasons, "bundled_seed_mode");
}

function getStatusCopy(status) {
  if (!status) {
    return {
      statusMessage: "Starting live EU grant index...",
      submitMessage: "Live indexing starts on page load. Watch the status panel while matching unlocks.",
    };
  }

  if (status.snapshot_source === "bundled" && status.refresh_in_progress) {
    return {
      statusMessage: "Running with cached data while the live refresh catches up.",
      submitMessage:
        "Bundled snapshot is live for the demo while the exhaustive live refresh continues in the background.",
    };
  }

  if (status.snapshot_loaded && status.refresh_in_progress) {
    return {
      statusMessage: "Running with cached data while the live refresh catches up.",
      submitMessage: "Cached results are live while the exhaustive live refresh continues in the background.",
    };
  }

  if (status.phase === "building") {
    return {
      statusMessage: "Indexing live grants now - first load can take a bit, progress updates below.",
      submitMessage: "Waiting for live EU grant data. The first load runs automatically so judges can see progress.",
    };
  }

  if ((status.phase === "ready" || status.phase === "ready_degraded") && status.matching_available) {
    if (isLexicalOnlyMode(status.degradation_reasons)) {
      return {
        statusMessage: "Index ready in keyword-only fallback mode.",
        submitMessage:
          "OpenAI is unavailable, so matching is keyword-based and lower confidence until AI features are enabled.",
      };
    }
    return {
      statusMessage: "Index ready - matching is now live.",
      submitMessage: "Matching is live. Short names like OpenAI auto-expand into full demo profiles.",
    };
  }

  if (status.phase === "error" || status.degraded) {
    return {
      statusMessage: "Indexing hit a problem - matching is paused until the data build recovers.",
      submitMessage: "The live data build needs attention before matching can run.",
    };
  }

  return {
    statusMessage: "Starting live EU grant index...",
    submitMessage: "Live indexing starts on page load. Watch the status panel while matching unlocks.",
  };
}

function renderDashboardSummary(summary, status = null) {
  if (!dashboardTotalGrants) {
    return;
  }
  const effectiveGrantCount = getEffectiveIndexedGrantCount(status, summary);
  const summaryCount = Number(summary?.total_grants || 0);
  const refreshCount = getRefreshProgressCount(status);
  if (status?.refresh_in_progress && status?.snapshot_loaded && refreshCount > 0 && refreshCount < summaryCount) {
    dashboardTotalGrants.textContent = `${summaryCount} grants indexed · ${refreshCount} found in live refresh`;
  } else if (status?.refresh_in_progress && status?.snapshot_loaded && effectiveGrantCount > summaryCount) {
    dashboardTotalGrants.textContent = `${effectiveGrantCount} grants found so far`;
  } else {
    dashboardTotalGrants.textContent = effectiveGrantCount ? `${effectiveGrantCount} grants indexed` : "0 grants indexed";
  }
  dashboardProgrammes.textContent = summary?.programme_count ? `${summary.programme_count} programmes` : "0 programmes";
  dashboardBudget.textContent = summary?.total_budget_display
    ? `${summary.total_budget_display} total available`
    : "Budget pending";
  dashboardDeadline.textContent =
    summary?.closest_deadline_days !== null && summary?.closest_deadline_days !== undefined
      ? `Closest deadline: ${summary.closest_deadline_days} days`
      : "Closest deadline: —";
}

function renderComparisonPanel() {
  if (!comparisonTable || !comparisonEmpty) {
    return;
  }
  const grants = comparisonGrantIds.map((grantId) => resultsById.get(grantId)).filter(Boolean);
  if (!grants.length) {
    comparisonEmpty.hidden = false;
    comparisonTable.innerHTML = "";
    return;
  }

  comparisonEmpty.hidden = true;
  const columns = grants
    .map((grant) => {
      const detail = grantDetailsById.get(grant.grant_id);
      const outcomes = detail?.expected_outcomes?.join(", ") || "—";
      const eligibility = detail?.eligibility_criteria?.join(", ") || grant.why_match;
      return `
        <div class="comparison-card">
          <h3>${escapeHtml(grant.title)}</h3>
          <p><strong>Budget</strong> ${escapeHtml(grant.budget || "—")}</p>
          <p><strong>Deadline</strong> ${escapeHtml(grant.deadline || "—")}</p>
          <p><strong>Fit</strong> ${escapeHtml(grant.fit_score)} / 100</p>
          <p><strong>Programme</strong> ${escapeHtml(grant.framework_programme || "—")}</p>
          <p><strong>Outcomes</strong> ${escapeHtml(outcomes)}</p>
          <p><strong>Requirements</strong> ${escapeHtml(eligibility)}</p>
        </div>
      `;
    })
    .join("");
  comparisonTable.innerHTML = columns;
}

function renderGrantDetail(result) {
  if (!expandedGrantIds.has(result.grant_id)) {
    return "";
  }
  if (loadingGrantIds.has(result.grant_id)) {
    return `<div class="grant-detail"><p class="submit-hint">Loading grant details…</p></div>`;
  }
  const detail = grantDetailsById.get(result.grant_id);
  if (!detail) {
    return `<div class="grant-detail"><p class="submit-hint">Grant detail unavailable.</p></div>`;
  }
  const deadlines = (detail.submission_deadlines || [])
    .map((entry) => `<li>${escapeHtml(entry.label)}: ${escapeHtml(entry.value)}</li>`)
    .join("");
  const outcomes = (detail.expected_outcomes || [])
    .map((entry) => `<li>${escapeHtml(entry)}</li>`)
    .join("");
  const eligibility = (detail.eligibility_criteria || [])
    .map((entry) => `<li>${escapeHtml(entry)}</li>`)
    .join("");
  const documents = (detail.documents || [])
    .map(
      (entry) =>
        `<li><a href="${escapeHtml(entry.url)}" target="_blank" rel="noreferrer">${escapeHtml(entry.title)}</a></li>`,
    )
    .join("");

  return `
    <div class="grant-detail">
      <div class="copy-block">
        <strong>Full description</strong>
        <span>${escapeHtml(detail.full_description || "No expanded description available yet.")}</span>
      </div>
      <div class="detail-grid">
        <div>
          <strong>Eligibility criteria</strong>
          <ul>${eligibility || "<li>Not available</li>"}</ul>
        </div>
        <div>
          <strong>Submission deadlines</strong>
          <ul>${deadlines || "<li>Not available</li>"}</ul>
        </div>
        <div>
          <strong>Expected outcomes</strong>
          <ul>${outcomes || "<li>Not available</li>"}</ul>
        </div>
        <div>
          <strong>Documents</strong>
          <ul>${documents || "<li>Not available</li>"}</ul>
        </div>
      </div>
    </div>
  `;
}

function renderResults(results, indexedGrants, matchMeta = latestMatchMeta) {
  latestResults = results;
  latestMatchMeta = matchMeta || null;
  setResultsBusy(false);
  resultsById.clear();
  for (const result of results) {
    resultsById.set(result.grant_id, result);
  }

  if (!results.length) {
    comparisonGrantIds.length = 0;
    renderComparisonPanel();
    updateDocumentTitle();
    const zeroResultsBullets = isLexicalOnlyMode(matchMeta?.degradation_reasons)
      ? [
          "Add sector-specific terms, target markets, and expected project outcomes.",
          "Keyword-only fallback is active, so weaker near-matches are intentionally hidden.",
        ]
      : [
          "Add your sector, growth stage or TRL, intended EU geography, and partnership needs.",
          "Include product maturity, deployment context, and the type of project you want funded.",
        ];

    if (isLexicalOnlyMode(matchMeta?.degradation_reasons)) {
      showResultsEmptyState({
        variant: "zero",
        title: "No reliable keyword matches yet",
        copy: "Keyword-only fallback is active, so the matcher is suppressing weak near-matches instead of showing misleading results.",
        bullets: zeroResultsBullets,
      });
      resultsMeta.textContent = `Indexed ${indexedGrants} live grants. Keyword-only fallback is active, so weak near-matches are hidden.`;
    } else {
      showResultsEmptyState({
        variant: "zero",
        title: "No strong matches found",
        copy: "The current profile did not clear the relevance threshold across the live grant set.",
        bullets: zeroResultsBullets,
      });
      resultsMeta.textContent = `Indexed ${indexedGrants} live grants. No strong matches yet.`;
    }
    return;
  }

  updateDocumentTitle(results.length);
  resultsEmpty.hidden = true;
  resultsMeta.textContent = isLexicalOnlyMode(matchMeta?.degradation_reasons)
    ? `Showing ${results.length} keyword-based results from ${indexedGrants} indexed grants. Treat scores as lower confidence.`
    : `Showing ${results.length} best-fit results from ${indexedGrants} indexed grants.`;

  resultsList.innerHTML = results
    .map((result, index) => {
      const keywords = (result.keywords || [])
        .map((keyword) => `<span class="keyword-pill">${escapeHtml(keyword)}</span>`)
        .join("");

      const meta = [
        result.framework_programme && `<span class="meta-pill">${escapeHtml(result.framework_programme)}</span>`,
        result.programme_division && `<span class="meta-pill">${escapeHtml(result.programme_division)}</span>`,
        result.deadline && `<span class="meta-pill">Deadline ${escapeHtml(result.deadline)}</span>`,
        result.budget && `<span class="meta-pill">${escapeHtml(result.budget)}</span>`,
      ]
        .filter(Boolean)
        .join("");

      return `
        <article class="result-card" style="animation-delay: ${index * 70}ms">
          <div class="result-head">
            <div class="result-head-main">
              <h3>${escapeHtml(result.title)}</h3>
              <div class="meta-row">
                ${meta}
                ${urgencyMarkup(result.days_left)}
              </div>
            </div>
            <div class="result-head-side">
              <div class="score-wrap">
                <span class="score-label">Fit score</span>
                <span class="${getScoreChipClass(result.fit_score)}">${escapeHtml(result.fit_score)} / 100</span>
              </div>
            </div>
          </div>

          <div class="result-copy">
            <div class="copy-block">
              <strong>Why this matches</strong>
              <span>${escapeHtml(result.why_match)}</span>
            </div>
            <div class="copy-block">
              <strong>Application angle</strong>
              <span>${escapeHtml(result.application_angle)}</span>
            </div>
          </div>

          <div class="keyword-row">${keywords}</div>

          <div class="meta-row result-links result-actions">
            <button class="secondary-button" type="button" onclick="toggleGrantDetails('${escapeHtml(result.grant_id)}')">
              ${expandedGrantIds.has(result.grant_id) ? "Hide details" : "View details"}
            </button>
            <button class="secondary-button" type="button" onclick="toggleComparisonGrant('${escapeHtml(result.grant_id)}')">
              ${comparisonGrantIds.includes(result.grant_id) ? "Remove favorite" : "Add to favorites"}
            </button>
            <button class="export-button" type="button" onclick="exportApplicationBrief('${escapeHtml(result.grant_id)}')">Export application brief</button>
            <a href="${escapeHtml(result.portal_url)}" target="_blank" rel="noreferrer">Open EC portal</a>
          </div>

          ${renderGrantDetail(result)}
        </article>
      `;
    })
    .join("");

  renderComparisonPanel();
}

function getValidationMessage(errorPayload) {
  const details = errorPayload?.detail;
  if (Array.isArray(details) && details.length) {
    return details
      .map((detail) => detail.msg || detail.message)
      .filter(Boolean)
      .join(". ");
  }
  return errorPayload?.detail?.message || errorPayload?.detail || errorPayload?.message || null;
}

function clearPendingPreResolve() {
  if (resolveDebounceHandle !== null) {
    window.clearTimeout(resolveDebounceHandle);
    resolveDebounceHandle = null;
  }
}

async function resolveCompanyProfile(query) {
  const journeyRequestId = ensureJourneyRequestId(buildJourneySeed(query));
  const response = await fetch("/api/profile/resolve", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": journeyRequestId,
    },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error("Could not resolve company name.");
  }

  return response.json();
}

async function requestWebsiteProfile(url) {
  const journeyRequestId = ensureJourneyRequestId(buildJourneySeed(url));
  const response = await fetch("/api/profile/from-website", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": journeyRequestId,
    },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch((error) => {
      console.error(error);
      return {};
    });
    throw new Error(getValidationMessage(errorPayload) || "Could not generate a description from the website.");
  }

  const payload = await response.json();
  if (!payload?.resolved || !payload.profile) {
    throw new Error("Could not generate a description from the website.");
  }

  return payload;
}

async function maybeResolveCompanyProfile(value, { source = "typing", force = false } = {}) {
  const normalizedQuery = normalizeCompanyNameInput(value);
  if (!normalizedQuery) {
    if (source !== "submit") {
      hideResolutionBanner();
    }
    return null;
  }

  if (!force && !looksLikeCompanyNameInput(value)) {
    return null;
  }

  if (!force && (normalizedQuery === inFlightPreResolveQuery || normalizedQuery === lastPreResolvedQuery)) {
    return null;
  }

  const resolveToken = ++latestResolveToken;
  if (!force) {
    inFlightPreResolveQuery = normalizedQuery;
  }

  try {
    const resolution = await resolveCompanyProfile(value);
    const currentQuery = normalizeCompanyNameInput(descriptionInput.value);
    const responseStillRelevant = force || (resolveToken === latestResolveToken && currentQuery === normalizedQuery);
    if (!responseStillRelevant) {
      return null;
    }

    if (!resolution.resolved || !resolution.profile) {
      return null;
    }

    descriptionInput.value = resolution.profile;
    updateWebsiteGenerationControls();
    lastPreResolvedQuery = normalizedQuery;
    showResolutionBanner(`Expanded ${resolution.display_name || "company name"} into a full demo profile.`);
    return resolution.profile;
  } catch (error) {
    console.error(error);
    if (source === "submit") {
      throw new Error(
        "Could not expand company name automatically. Add one or two sentences about what the company does.",
      );
    }
    return null;
  } finally {
    if (!force && inFlightPreResolveQuery === normalizedQuery) {
      inFlightPreResolveQuery = "";
    }
  }
}

function scheduleCompanyResolution() {
  clearPendingPreResolve();
  const value = descriptionInput.value;
  if (!looksLikeCompanyNameInput(value)) {
    return;
  }

  resolveDebounceHandle = window.setTimeout(() => {
    resolveDebounceHandle = null;
    return maybeResolveCompanyProfile(value, { source: "typing" });
  }, PROFILE_RESOLVE_DEBOUNCE_MS);
}

function updateStatus(status) {
  latestStatus = status;
  const effectiveGrantCount = getEffectiveIndexedGrantCount(status, status.summary);
  const refreshCount = getRefreshProgressCount(status);
  const totalPrefixes = status.total_prefixes || 0;
  const scannedPrefixes = status.scanned_prefixes || 0;
  const ratio = totalPrefixes ? Math.max(8, Math.round((scannedPrefixes / totalPrefixes) * 100)) : 8;
  const failedPrefixes = status.failed_prefixes || 0;
  const truncatedPrefixes = status.truncated_prefixes || 0;
  const coverageLabel = status.coverage_complete
    ? "complete"
    : truncatedPrefixes > 0
      ? "truncated"
      : status.phase === "building"
        ? "building"
        : "partial";
  const statusCopyText = getStatusCopy(status);
  const snapshotAge = formatDuration(status.snapshot_age_seconds);

  statusCopy.textContent = statusCopyText.statusMessage;
  statusPhase.textContent = status.phase;
  statusCount.textContent = String(effectiveGrantCount || 0);
  statusPrefixes.textContent = `${scannedPrefixes} / ${totalPrefixes}`;
  statusFailures.textContent = String(failedPrefixes + truncatedPrefixes);
  statusCoverage.textContent = coverageLabel;
  statusEmbeddings.textContent = isLexicalOnlyMode(status.degradation_reasons)
    ? "keyword-only"
    : status.embeddings_ready
      ? "ready"
      : "warming up";
  statusSource.textContent = status.snapshot_loaded
    ? status.snapshot_source === "bundled"
      ? `bundled seed snapshot (${snapshotAge} old)`
      : `saved index (${snapshotAge} old)`
    : "live crawl";
  statusRefresh.textContent = status.refresh_in_progress
    ? status.snapshot_loaded
      ? refreshCount > 0
        ? `refreshing in background · ${refreshCount} found so far`
        : "refreshing in background"
      : "building live index"
    : "idle";
  statusProgress.textContent =
    status.current_prefix && status.current_page ? `${status.current_prefix} p.${status.current_page}` : "—";
  statusUpdated.textContent = formatLastProgress(status.last_progress_at);
  statusBar.style.width = `${status.phase === "ready" || status.phase === "ready_degraded" ? 100 : ratio}%`;
  statusBar.dataset.phase = status.phase || "idle";
  if (matchButton.textContent !== "Matching…") {
    matchButton.disabled = false;
  }
  submitHint.textContent = statusCopyText.submitMessage;
  renderDashboardSummary(status.summary, status);

  if (status.degraded && status.degradation_reasons?.length) {
    statusDegraded.hidden = false;
    statusDegraded.textContent = isLexicalOnlyMode(status.degradation_reasons)
      ? "Keyword-only matching is active because OpenAI is unavailable. Treat scores as lower confidence and add domain-specific detail for better results."
      : isBundledSeedMode(status.degradation_reasons)
        ? "Running with cached data while the live refresh completes in the background."
      : `Degraded mode: ${humanizeReasons(status.degradation_reasons).join(", ")}.`;
  } else {
    statusDegraded.hidden = true;
    statusDegraded.textContent = "";
  }
}

function scheduleStatusPoll(delayMs) {
  window.clearTimeout(statusPollHandle);
  statusPollHandle = window.setTimeout(fetchStatus, delayMs);
}

async function fetchStatus() {
  if (statusPollInFlight) {
    return;
  }

  statusPollInFlight = true;
  const controller = new AbortController();
  const timeoutHandle = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("/api/index/status", { signal: controller.signal });
    if (!response.ok) {
      throw new Error("Could not read index status.");
    }
    const status = await response.json();
    consecutiveStatusFailures = 0;
    updateStatus(status);
    scheduleStatusPoll(status.phase === "building" || status.refresh_in_progress ? 2500 : 5000);
  } catch (error) {
    console.error(error);
    consecutiveStatusFailures += 1;
    updateStatus({
      phase: "error",
      message: error.message || "Could not read index status.",
      indexed_grants: 0,
      scanned_prefixes: 0,
      total_prefixes: 0,
      failed_prefixes: 0,
      truncated_prefixes: 0,
      embeddings_ready: false,
      degraded: true,
      coverage_complete: false,
      matching_available: false,
      degradation_reasons: ["status_poll_failed"],
      snapshot_loaded: false,
      refresh_in_progress: false,
      current_prefix: null,
      current_page: null,
      last_progress_at: null,
      snapshot_age_seconds: null,
      summary: null,
    });
    scheduleStatusPoll(Math.min(15000, 2500 * (consecutiveStatusFailures + 1)));
  } finally {
    window.clearTimeout(timeoutHandle);
    statusPollInFlight = false;
  }
}

function normalizeTopicDetailPayload(payload, topicId) {
  const topicDetails = payload?.topicDetails || {};
  const summary = typeof topicDetails.summary === "object" && topicDetails.summary ? topicDetails.summary : {};
  const sections = typeof topicDetails.sections === "object" && topicDetails.sections ? topicDetails.sections : {};

  return {
    grant_id: summary.identifier || topicId,
    full_description: stripHtmlToText(sections.objective || sections.description || ""),
    eligibility_criteria: normalizeTextList(sections.eligibilityConditions),
    submission_deadlines: normalizeDeadlines(sections.submissionConditions, summary),
    expected_outcomes: normalizeTextList(sections.expectedOutcomes),
    documents: normalizeDocuments(sections.documents),
    partner_search_available: normalizeBool(sections.partnerSearch),
    source: "browser_topic_detail",
    fallback_used: false,
  };
}

function normalizeGrantDetailResponse(payload, grantId) {
  if (payload && typeof payload === "object" && typeof payload.grant_id === "string") {
    return payload;
  }
  return normalizeTopicDetailPayload(payload, grantId);
}

function stripHtmlToText(value) {
  return String(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeTextList(value) {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  const items = [];
  for (const entry of values) {
    const stringValue = String(entry || "");
    const matches = [...stringValue.matchAll(/<li[^>]*>(.*?)<\/li>/gi)];
    if (matches.length) {
      for (const match of matches) {
        const cleaned = stripHtmlToText(match[1]);
        if (cleaned) {
          items.push(cleaned);
        }
      }
      continue;
    }
    const cleaned = stripHtmlToText(stringValue);
    if (cleaned) {
      items.push(cleaned);
    }
  }
  return [...new Set(items)];
}

function normalizeDeadlines(submissionConditions, summary) {
  const deadlines = [];
  const detailDeadline = submissionConditions?.deadlineDate?.slice?.(0, 10);
  if (detailDeadline) {
    deadlines.push({ label: "Main deadline", value: detailDeadline });
  }
  const summaryDeadline = summary?.deadlineDate?.slice?.(0, 10);
  if (summaryDeadline && !deadlines.some((entry) => entry.value === summaryDeadline)) {
    deadlines.push({ label: "Main deadline", value: summaryDeadline });
  }
  return deadlines;
}

function normalizeDocuments(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((entry) => entry && typeof entry.title === "string" && typeof entry.url === "string")
    .map((entry) => ({ title: entry.title, url: entry.url }));
}

function normalizeBool(value) {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return ["true", "1", "yes"].includes(value.toLowerCase());
  }
  return null;
}

async function toggleGrantDetails(grantId) {
  if (expandedGrantIds.has(grantId)) {
    expandedGrantIds.delete(grantId);
    renderResults(latestResults, latestStatus?.indexed_grants || latestResults.length, latestMatchMeta);
    return;
  }

  expandedGrantIds.add(grantId);
  if (grantDetailsById.has(grantId)) {
    renderResults(latestResults, latestStatus?.indexed_grants || latestResults.length, latestMatchMeta);
    return;
  }

  loadingGrantIds.add(grantId);
  renderResults(latestResults, latestStatus?.indexed_grants || latestResults.length, latestMatchMeta);

  try {
    const response = await fetch(`/api/grants/${encodeURIComponent(grantId)}`);
    if (!response.ok) {
      throw new Error("Could not load topic detail.");
    }
    const payload = await response.json();
    grantDetailsById.set(grantId, normalizeGrantDetailResponse(payload, grantId));
  } catch (error) {
    console.error(error);
    grantDetailsById.set(grantId, buildFallbackGrantDetail(grantId));
  } finally {
    loadingGrantIds.delete(grantId);
    renderResults(latestResults, latestStatus?.indexed_grants || latestResults.length, latestMatchMeta);
  }
}

function buildFallbackGrantDetail(grantId) {
  const result = resultsById.get(grantId);
  return {
    grant_id: grantId,
    full_description: "",
    eligibility_criteria: [],
    submission_deadlines:
      result?.deadline ? [{ label: "Main deadline", value: result.deadline }] : [],
    expected_outcomes: [],
    documents: [],
    partner_search_available: null,
    source: "match_result_fallback",
    fallback_used: true,
  };
}

function toggleComparisonGrant(grantId) {
  const existingIndex = comparisonGrantIds.indexOf(grantId);
  if (existingIndex >= 0) {
    comparisonGrantIds.splice(existingIndex, 1);
    renderComparisonPanel();
    return;
  }
  if (comparisonGrantIds.length >= MAX_COMPARISON_GRANTS) {
    renderComparisonPanel();
    return;
  }
  comparisonGrantIds.push(grantId);
  renderComparisonPanel();
}

async function exportApplicationBrief(grantId) {
  const matchResult = resultsById.get(grantId);
  if (!matchResult) {
    return;
  }
  try {
    const companyDescription = descriptionInput.value.trim();
    const grantDetail = grantDetailsById.get(grantId) || buildFallbackGrantDetail(grantId);
    const journeyRequestId = ensureJourneyRequestId();
    const response = await fetch("/api/application-brief", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": journeyRequestId,
      },
      body: JSON.stringify({
        company_description: companyDescription,
        match_result: matchResult,
        grant_detail: grantDetail,
      }),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch((error) => {
        console.error(error);
        return {};
      });
      throw new Error(getValidationMessage(errorPayload) || "Could not export application brief.");
    }

    const payload = await response.json();
    const exportWindow = window.open("", "_blank");
    if (!exportWindow) {
      throw new Error("Could not open export window.");
    }
    exportWindow.document.write(payload.html);
    exportWindow.document.close();
    exportWindow.print();
    setFormFeedback("Application brief prepared. Your print dialog should open in a new tab.");
  } catch (error) {
    console.error(error);
    setFormFeedback(error.message || "Could not export the application brief.", "error");
  }
}

async function applyQuickFillDemoProfile() {
  quickFillOpenAIButton.disabled = true;
  try {
    const resolvedProfile = await maybeResolveCompanyProfile("OpenAI", { source: "quick-fill", force: true });
    if (!resolvedProfile) {
      throw new Error("Could not load the OpenAI demo profile.");
    }
    latestMatchMeta = null;
    setDescriptionInvalid(false);
    setFormFeedback("OpenAI demo profile loaded. Run matching to see ranked grant opportunities.");
    showIntroResultsState(DEFAULT_EMPTY_STATE, "OpenAI demo profile loaded. Ready to match.");
    descriptionInput.focus();
  } catch (error) {
    console.error(error);
    showResolutionBanner(error.message || "Could not load the OpenAI demo profile.");
    setFormFeedback(error.message || "Could not load the OpenAI demo profile.", "error");
  } finally {
    quickFillOpenAIButton.disabled = false;
  }
}

async function applyWebsiteDescriptionFromUrl() {
  const websiteUrl = websiteUrlInput.value.trim();
  if (!websiteUrl) {
    setFormFeedback("Add a company website URL before generating a description.", "error");
    return;
  }

  generateDescriptionButton.disabled = true;
  setFormFeedback("");
  let generationFailed = false;
  try {
    const resolution = await requestWebsiteProfile(websiteUrl);
    descriptionInput.value = resolution.profile;
    setDescriptionInvalid(false);
    hideResolutionBanner();
    showResolutionBanner(`Generated description from ${resolution.display_name || websiteUrl}.`);
    setFormFeedback("Description generated from website. Run matching to see ranked grant opportunities.");
    descriptionInput.focus();
  } catch (error) {
    generationFailed = true;
    console.error(error);
    showResolutionBanner(error.message || "Could not generate a description from the website.");
    setFormFeedback(error.message || "Could not generate a description from the website.", "error");
  } finally {
    updateWebsiteGenerationControls();
    if (generationFailed) {
      websiteUrlInput.disabled = false;
      generateDescriptionButton.disabled = !websiteUrlInput.value.trim();
    }
  }
}

async function submitMatch(event) {
  event.preventDefault();

  let companyDescription = descriptionInput.value.trim();
  setDescriptionInvalid(false);
  setFormFeedback("");
  if (!companyDescription) {
    const message = "Add a company name or a short company description before matching.";
    setDescriptionInvalid(true);
    setFormFeedback(message, "error");
    showMatchFeedback(message);
    showResolutionBanner(message);
    descriptionInput.focus();
    return;
  }
  const journeySeed = buildJourneySeed(companyDescription);
  const journeyRequestId = ensureJourneyRequestId(journeySeed);

  matchButton.disabled = true;
  matchButton.textContent = "Matching…";
  matchButton.classList.add("is-loading");
  showLoadingResultsState();

  try {
    if (looksLikeCompanyNameInput(companyDescription)) {
      const resolvedProfile = await maybeResolveCompanyProfile(companyDescription, { source: "submit", force: true });
      if (!resolvedProfile) {
        throw new Error(
          "Could not expand company name automatically. Add one or two sentences about what the company does.",
        );
      }
      companyDescription = resolvedProfile;
    } else {
      hideResolutionBanner();
      if (companyDescription.length < MIN_DESCRIPTION_LENGTH) {
        setDescriptionInvalid(true);
        throw new Error(
          `Add at least ${MIN_DESCRIPTION_LENGTH} characters so the matcher has enough company context.`,
        );
      }
    }

    const response = await fetch("/api/match", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": journeyRequestId,
      },
      body: JSON.stringify({ company_description: companyDescription }),
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch((error) => {
        console.error(error);
        return {};
      });
      const errorMessage =
        getValidationMessage(errorPayload) || "Matching failed. Try again after the index finishes building.";
      throw new Error(errorMessage);
    }

    const payload = await response.json();
    setFormFeedback(`Match completed. Showing ${payload.results?.length || 0} shortlisted grants.`);
    renderResults(payload.results || [], payload.indexed_grants || 0, payload);
  } catch (error) {
    console.error(error);
    const message = error.message || "Matching failed.";
    const looksLikeInputError =
      message.includes("Add at least") ||
      message.includes("Could not expand company name automatically") ||
      message.includes("Add a company name");
    setDescriptionInvalid(looksLikeInputError);
    setFormFeedback(message, "error");
    showMatchFeedback(message);
  } finally {
    matchButton.textContent = "Find Grants";
    matchButton.disabled = false;
    matchButton.classList.remove("is-loading");
  }
}

function handleAlertSignup(event) {
  event.preventDefault();
  const value = alertEmail.value.trim();
  const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  if (!isValid) {
    alertEmail.classList.add("is-invalid");
    alertStatus.textContent = "Enter a valid email to preview grant alerts.";
    return;
  }
  alertEmail.classList.remove("is-invalid");
  alertStatus.textContent = "Alerts coming soon. We’ll notify you when new grants match this profile.";
}

descriptionInput.addEventListener("input", () => {
  setDescriptionInvalid(false);
  if (formFeedback?.classList.contains("is-error")) {
    setFormFeedback("");
  }
  updateWebsiteGenerationControls();
  if (!looksLikeCompanyNameInput(descriptionInput.value)) {
    clearPendingPreResolve();
    hideResolutionBanner();
    return;
  }
  scheduleCompanyResolution();
});

websiteUrlInput?.addEventListener("input", updateWebsiteGenerationControls);

descriptionInput.addEventListener("blur", () => {
  clearPendingPreResolve();
  return maybeResolveCompanyProfile(descriptionInput.value, { source: "blur" });
});

quickFillOpenAIButton.addEventListener("click", applyQuickFillDemoProfile);
generateDescriptionButton.addEventListener("click", applyWebsiteDescriptionFromUrl);
agentHandoffCopyButton.addEventListener("click", copyAgentHandoffInstructions);
agentHandoffDisclosure?.addEventListener("toggle", () => {
  if (agentHandoffDisclosure.open) {
    agentHandoffStatus.textContent = "Copy and paste this block into your agent chat.";
  } else {
    agentHandoffStatus.textContent = "Expand this block to copy and paste it into your agent chat.";
  }
});
alertForm?.addEventListener("submit", handleAlertSignup);
alertEmail?.addEventListener("input", () => {
  alertEmail.classList.remove("is-invalid");
});
matchButton.disabled = false;
submitHint.textContent = getStatusCopy(null).submitMessage;
updateDocumentTitle();
hydrateAgentHandoff();
updateWebsiteGenerationControls();
form.addEventListener("submit", submitMatch);
renderDashboardSummary(null);
renderComparisonPanel();
showIntroResultsState();
fetchStatus();

window.grantDetailsById = grantDetailsById;
window.renderResults = renderResults;
window.updateStatus = updateStatus;
window.toggleGrantDetails = toggleGrantDetails;
window.toggleComparisonGrant = toggleComparisonGrant;
window.exportApplicationBrief = exportApplicationBrief;
globalThis.grantDetailsById = grantDetailsById;
