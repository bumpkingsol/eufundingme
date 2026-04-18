const DEFAULT_TITLE = "EU Grant Matcher";
const DEFAULT_EMPTY_STATE =
  "The top matches will appear here with fit scores, rationale, and the angle to take in the application.";
const MIN_DESCRIPTION_LENGTH = 20;
const PROFILE_RESOLVE_DEBOUNCE_MS = 450;

const form = document.querySelector("#match-form");
const descriptionInput = document.querySelector("#company-description");
const matchButton = document.querySelector("#match-button");
const quickFillOpenAIButton = document.querySelector("#quick-fill-openai");
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
const resultsEmpty = document.querySelector("#results-empty");
const resultsList = document.querySelector("#results-list");
const resultsMeta = document.querySelector("#results-meta");

let latestStatus = null;
let statusPollHandle = null;
let statusPollInFlight = false;
let consecutiveStatusFailures = 0;
let resolveDebounceHandle = null;
let inFlightPreResolveQuery = "";
let lastPreResolvedQuery = "";
let latestResolveToken = 0;

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

function renderResults(results, indexedGrants) {
  if (!results.length) {
    updateDocumentTitle();
    resultsList.innerHTML = "";
    resultsEmpty.hidden = false;
    resultsEmpty.textContent = DEFAULT_EMPTY_STATE;
    resultsMeta.textContent = `Indexed ${indexedGrants} live grants. No strong matches yet.`;
    return;
  }

  updateDocumentTitle(results.length);
  resultsEmpty.hidden = true;
  resultsMeta.textContent = `Showing ${results.length} best-fit results from ${indexedGrants} indexed grants.`;

  resultsList.innerHTML = results
    .map((result) => {
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
        <article class="result-card">
          <div class="result-head">
            <div>
              <h3>${escapeHtml(result.title)}</h3>
              <div class="meta-row">
                ${meta}
                ${urgencyMarkup(result.days_left)}
              </div>
            </div>
            <div>
              <span class="${getScoreChipClass(result.fit_score)}">${escapeHtml(result.fit_score)} / 100</span>
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

          <div class="meta-row result-links">
            <a href="${escapeHtml(result.portal_url)}" target="_blank" rel="noreferrer">Open EC portal</a>
          </div>
        </article>
      `;
    })
    .join("");
}

function showResolutionBanner(text) {
  resolutionBanner.hidden = false;
  resolutionBanner.textContent = text;
}

function hideResolutionBanner() {
  resolutionBanner.hidden = true;
  resolutionBanner.textContent = "";
}

function normalizeCompanyNameInput(value) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
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

function getStatusCopy(status) {
  if (!status) {
    return {
      statusMessage: "Starting live EU grant index...",
      submitMessage: "Live indexing starts on page load. Watch the status panel while matching unlocks.",
    };
  }

  if (status.snapshot_loaded && status.refresh_in_progress) {
    return {
      statusMessage: "Saved index is live while the background refresh catches up.",
      submitMessage: "Matching is live from the saved index while the exhaustive live refresh continues.",
    };
  }

  if (status.phase === "building") {
    return {
      statusMessage: "Indexing live grants now - first load can take a bit, progress updates below.",
      submitMessage: "Waiting for live EU grant data. The first load runs automatically so judges can see progress.",
    };
  }

  if ((status.phase === "ready" || status.phase === "ready_degraded") && status.matching_available) {
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

function clearPendingPreResolve() {
  if (resolveDebounceHandle !== null) {
    window.clearTimeout(resolveDebounceHandle);
    resolveDebounceHandle = null;
  }
}

async function resolveCompanyProfile(query) {
  const response = await fetch("/api/profile/resolve", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error("Could not resolve company name.");
  }

  return response.json();
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
    lastPreResolvedQuery = normalizedQuery;
    showResolutionBanner(`Expanded ${resolution.display_name || "company name"} into a full demo profile.`);
    return resolution.profile;
  } catch (_error) {
    if (source === "submit") {
      throw new Error("Could not expand company name automatically. Add one or two sentences about what the company does.");
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
  const matchingAvailable = isMatchingAvailable(status);
  const snapshotAge = formatDuration(status.snapshot_age_seconds);

  statusCopy.textContent = statusCopyText.statusMessage;
  statusPhase.textContent = status.phase;
  statusCount.textContent = String(status.indexed_grants || 0);
  statusPrefixes.textContent = `${scannedPrefixes} / ${totalPrefixes}`;
  statusFailures.textContent = String(failedPrefixes + truncatedPrefixes);
  statusCoverage.textContent = coverageLabel;
  statusEmbeddings.textContent = status.embeddings_ready ? "ready" : "warming up";
  statusSource.textContent = status.snapshot_loaded ? `saved index (${snapshotAge} old)` : "live crawl";
  statusRefresh.textContent = status.refresh_in_progress
    ? status.snapshot_loaded
      ? "refreshing in background"
      : "building live index"
    : "idle";
  statusProgress.textContent =
    status.current_prefix && status.current_page
      ? `${status.current_prefix} p.${status.current_page}`
      : "—";
  statusUpdated.textContent = formatLastProgress(status.last_progress_at);
  statusBar.style.width = `${status.phase === "ready" || status.phase === "ready_degraded" ? 100 : ratio}%`;
  matchButton.disabled = !matchingAvailable;
  submitHint.textContent = statusCopyText.submitMessage;

  if (status.degraded && status.degradation_reasons?.length) {
    statusDegraded.hidden = false;
    statusDegraded.textContent = `Degraded mode: ${humanizeReasons(status.degradation_reasons).join(", ")}.`;
  } else {
    statusDegraded.hidden = true;
    statusDegraded.textContent = "";
  }
}

function getValidationMessage(errorPayload) {
  const details = errorPayload?.detail;
  if (Array.isArray(details) && details.length) {
    return details
      .map((detail) => detail.msg || detail.message)
      .filter(Boolean)
      .join(". ");
  }
  return errorPayload?.detail?.message || errorPayload?.message || null;
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
    });
    scheduleStatusPoll(Math.min(15000, 2500 * (consecutiveStatusFailures + 1)));
  } finally {
    window.clearTimeout(timeoutHandle);
    statusPollInFlight = false;
  }
}

async function applyQuickFillDemoProfile() {
  quickFillOpenAIButton.disabled = true;
  try {
    const resolvedProfile = await maybeResolveCompanyProfile("OpenAI", { source: "quick-fill", force: true });
    if (!resolvedProfile) {
      throw new Error("Could not load the OpenAI demo profile.");
    }
    resultsEmpty.hidden = false;
    resultsEmpty.textContent = DEFAULT_EMPTY_STATE;
    resultsList.innerHTML = "";
    resultsMeta.textContent = "OpenAI demo profile loaded. Ready to match.";
    updateDocumentTitle();
    descriptionInput.focus();
  } catch (error) {
    showResolutionBanner(error.message || "Could not load the OpenAI demo profile.");
  } finally {
    quickFillOpenAIButton.disabled = false;
  }
}

async function submitMatch(event) {
  event.preventDefault();

  let companyDescription = descriptionInput.value.trim();
  if (!companyDescription) {
    descriptionInput.focus();
    return;
  }

  matchButton.disabled = true;
  matchButton.textContent = "Matching…";

  try {
    if (looksLikeCompanyNameInput(companyDescription)) {
      const resolvedProfile = await maybeResolveCompanyProfile(companyDescription, { source: "submit", force: true });
      if (!resolvedProfile) {
        throw new Error("Could not expand company name automatically. Add one or two sentences about what the company does.");
      }
      companyDescription = resolvedProfile;
    } else {
      hideResolutionBanner();
      if (companyDescription.length < MIN_DESCRIPTION_LENGTH) {
        throw new Error(`Add at least ${MIN_DESCRIPTION_LENGTH} characters so the matcher has enough company context.`);
      }
    }

    const response = await fetch("/api/match", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ company_description: companyDescription }),
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      const errorMessage = getValidationMessage(errorPayload) || "Matching failed. Try again after the index finishes building.";
      throw new Error(errorMessage);
    }

    const payload = await response.json();
    renderResults(payload.results || [], payload.indexed_grants || 0);
  } catch (error) {
    updateDocumentTitle();
    resultsEmpty.hidden = false;
    resultsEmpty.textContent = error.message || "Matching failed.";
    resultsList.innerHTML = "";
    resultsMeta.textContent = "No results available.";
  } finally {
    matchButton.textContent = "Find Grants";
    matchButton.disabled = !isMatchingAvailable(latestStatus);
  }
}

descriptionInput.addEventListener("input", () => {
  if (!looksLikeCompanyNameInput(descriptionInput.value)) {
    clearPendingPreResolve();
    hideResolutionBanner();
    return;
  }
  scheduleCompanyResolution();
});

descriptionInput.addEventListener("blur", () => {
  clearPendingPreResolve();
  return maybeResolveCompanyProfile(descriptionInput.value, { source: "blur" });
});

quickFillOpenAIButton.addEventListener("click", applyQuickFillDemoProfile);
matchButton.disabled = true;
submitHint.textContent = getStatusCopy(null).submitMessage;
updateDocumentTitle();
form.addEventListener("submit", submitMatch);
fetchStatus();
