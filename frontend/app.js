const form = document.querySelector("#match-form");
const descriptionInput = document.querySelector("#company-description");
const matchButton = document.querySelector("#match-button");
const submitHint = document.querySelector("#submit-hint");
const demoPresets = document.querySelector("#demo-presets");
const presetButtons = document.querySelector("#preset-buttons");
const statusCopy = document.querySelector("#status-copy");
const statusBar = document.querySelector("#status-bar");
const statusPhase = document.querySelector("#status-phase");
const statusCount = document.querySelector("#status-count");
const statusPrefixes = document.querySelector("#status-prefixes");
const statusFailures = document.querySelector("#status-failures");
const statusCoverage = document.querySelector("#status-coverage");
const statusEmbeddings = document.querySelector("#status-embeddings");
const statusDegraded = document.querySelector("#status-degraded");
const resolutionBanner = document.querySelector("#resolution-banner");
const resultsEmpty = document.querySelector("#results-empty");
const resultsList = document.querySelector("#results-list");
const resultsMeta = document.querySelector("#results-meta");
const demoPresetProfiles = Array.isArray(window.__DEMO_PRESETS__) ? window.__DEMO_PRESETS__ : [];

let latestStatus = null;
let statusPollHandle = null;
let statusPollInFlight = false;
let consecutiveStatusFailures = 0;
let activePresetName = null;
const DEFAULT_EMPTY_STATE =
  "The top matches will appear here with fit scores, rationale, and the angle to take in the application.";
const MIN_DESCRIPTION_LENGTH = 20;
const DEFAULT_SUBMIT_HINT =
  "The first run builds a live grant index, then matching becomes instant.";

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

function renderResults(results, indexedGrants) {
  if (!results.length) {
    resultsList.innerHTML = "";
    resultsEmpty.hidden = false;
    resultsEmpty.textContent = DEFAULT_EMPTY_STATE;
    resultsMeta.textContent = `Indexed ${indexedGrants} live grants. No strong matches yet.`;
    return;
  }

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
              <span class="score-chip">${escapeHtml(result.fit_score)} / 100</span>
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

function syncPresetSelection() {
  const buttons = presetButtons.querySelectorAll("[data-preset-name]");
  for (const button of buttons) {
    button.classList.toggle("is-active", button.dataset.presetName === activePresetName);
  }
}

function applyDemoPreset(preset) {
  descriptionInput.value = preset.profile;
  activePresetName = preset.name;
  syncPresetSelection();
  showResolutionBanner(`Loaded saved ${preset.name} demo profile.`);
  resultsEmpty.hidden = false;
  resultsEmpty.textContent = DEFAULT_EMPTY_STATE;
  resultsList.innerHTML = "";
  resultsMeta.textContent = `Ready to match ${preset.name}.`;
  descriptionInput.focus();
}

function renderDemoPresets() {
  if (!demoPresetProfiles.length) {
    demoPresets.hidden = true;
    return;
  }

  presetButtons.innerHTML = demoPresetProfiles
    .map(
      (preset) => `
        <button
          type="button"
          class="preset-button"
          data-preset-name="${escapeHtml(preset.name)}"
        >
          ${escapeHtml(preset.name)}
        </button>
      `,
    )
    .join("");

  for (const button of presetButtons.querySelectorAll("[data-preset-name]")) {
    button.addEventListener("click", () => {
      const preset = demoPresetProfiles.find((item) => item.name === button.dataset.presetName);
      if (preset) {
        applyDemoPreset(preset);
      }
    });
  }

  syncPresetSelection();
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

  statusCopy.textContent = status.message;
  statusPhase.textContent = status.phase;
  statusCount.textContent = String(status.indexed_grants || 0);
  statusPrefixes.textContent = `${scannedPrefixes} / ${totalPrefixes}`;
  statusFailures.textContent = String(failedPrefixes + truncatedPrefixes);
  statusCoverage.textContent = coverageLabel;
  statusEmbeddings.textContent = status.embeddings_ready ? "ready" : "warming up";
  statusBar.style.width = `${status.phase === "ready" ? 100 : ratio}%`;
  matchButton.disabled = !isMatchingAvailable(status);
  submitHint.textContent = isMatchingAvailable(status)
    ? DEFAULT_SUBMIT_HINT
    : status.message || "Matching becomes available when the live grant index is ready.";

  if (status.degraded && status.degradation_reasons?.length) {
    statusDegraded.hidden = false;
    statusDegraded.textContent = `Degraded mode: ${status.degradation_reasons.join(", ").replaceAll("_", " ")}.`;
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
    scheduleStatusPoll(status.phase === "building" ? 2500 : 5000);
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
    });
    scheduleStatusPoll(Math.min(15000, 2500 * (consecutiveStatusFailures + 1)));
  } finally {
    window.clearTimeout(timeoutHandle);
    statusPollInFlight = false;
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
      hideResolutionBanner();
      const resolution = await resolveCompanyProfile(companyDescription);
      if (!resolution.resolved || !resolution.profile) {
        throw new Error(
          resolution.message || "Could not expand company name automatically. Add one or two sentences about what the company does.",
        );
      }

      companyDescription = resolution.profile;
      descriptionInput.value = companyDescription;
      activePresetName = null;
      syncPresetSelection();
      if (resolution.source === "demo_profile") {
        showResolutionBanner(`Using saved ${resolution.display_name} demo profile.`);
      } else {
        showResolutionBanner(`Expanded ${resolution.display_name || "company name"} with AI.`);
      }
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
  hideResolutionBanner();
  if (activePresetName !== null) {
    activePresetName = null;
    syncPresetSelection();
  }
});

form.addEventListener("submit", submitMatch);
renderDemoPresets();
fetchStatus();
