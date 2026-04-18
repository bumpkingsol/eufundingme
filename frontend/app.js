const form = document.querySelector("#match-form");
const descriptionInput = document.querySelector("#company-description");
const matchButton = document.querySelector("#match-button");
const statusCopy = document.querySelector("#status-copy");
const statusBar = document.querySelector("#status-bar");
const statusPhase = document.querySelector("#status-phase");
const statusCount = document.querySelector("#status-count");
const statusPrefixes = document.querySelector("#status-prefixes");
const statusEmbeddings = document.querySelector("#status-embeddings");
const resultsEmpty = document.querySelector("#results-empty");
const resultsList = document.querySelector("#results-list");
const resultsMeta = document.querySelector("#results-meta");

let latestStatus = null;

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

function updateStatus(status) {
  latestStatus = status;
  const totalPrefixes = status.total_prefixes || 0;
  const scannedPrefixes = status.scanned_prefixes || 0;
  const ratio = totalPrefixes ? Math.max(8, Math.round((scannedPrefixes / totalPrefixes) * 100)) : 8;

  statusCopy.textContent = status.message;
  statusPhase.textContent = status.phase;
  statusCount.textContent = String(status.indexed_grants || 0);
  statusPrefixes.textContent = `${scannedPrefixes} / ${totalPrefixes}`;
  statusEmbeddings.textContent = status.embeddings_ready ? "ready" : "warming up";
  statusBar.style.width = `${status.phase === "ready" ? 100 : ratio}%`;
  matchButton.disabled = status.phase !== "ready";
}

async function fetchStatus() {
  try {
    const response = await fetch("/api/index/status");
    if (!response.ok) {
      throw new Error("Could not read index status.");
    }
    const status = await response.json();
    updateStatus(status);
  } catch (error) {
    updateStatus({
      phase: "error",
      message: error.message || "Could not read index status.",
      indexed_grants: 0,
      scanned_prefixes: 0,
      total_prefixes: 0,
      embeddings_ready: false,
    });
  }
}

async function submitMatch(event) {
  event.preventDefault();

  const companyDescription = descriptionInput.value.trim();
  if (!companyDescription) {
    descriptionInput.focus();
    return;
  }

  matchButton.disabled = true;
  matchButton.textContent = "Matching…";

  try {
    const response = await fetch("/api/match", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ company_description: companyDescription }),
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      const errorMessage =
        errorPayload?.detail?.message ||
        errorPayload?.message ||
        "Matching failed. Try again after the index finishes building.";
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
    matchButton.disabled = latestStatus?.phase !== "ready";
  }
}

form.addEventListener("submit", submitMatch);
fetchStatus();
window.setInterval(fetchStatus, 2500);
