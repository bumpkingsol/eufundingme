# Website Description Generation Design

## Goal

Add an optional company website URL input to the grant matcher flow so a user can click `Generate description` and have the app derive a company description from the website homepage. The generated description should populate the existing company description field and then flow through the current matching pipeline unchanged.

## Scope

### In scope

- Add an optional `Company website URL` field to the frontend form.
- Add a `Generate description` button for the URL-based flow.
- Make manual description entry and website generation mutually exclusive.
- Fetch one homepage URL server-side.
- Extract a compact text payload from the fetched page.
- Use OpenAI to turn that payload into a concise company description for grant matching.
- Populate the generated description into the existing description textarea.
- Add focused backend and frontend tests for the new flow.

### Out of scope

- Multi-page crawling.
- JavaScript-rendered browsing.
- OCR or PDF extraction.
- Website trust scoring or domain allowlists.
- Merging manual description text with generated text.
- Replacing the existing match pipeline.

## User Experience

### Form behavior

- The existing `Company description` textarea remains the primary match input.
- A new optional `Company website URL` text input is shown near the description field.
- A new `Generate description` button is shown next to the website input.
- If the user types any non-whitespace content into `Company description`, the website URL input and generate button become disabled.
- If the user clears the description field, the website URL input becomes usable again.
- If the website URL field has content while the description field is empty, the generate button is enabled.
- Clicking `Generate description` fills the description textarea with the generated company description and returns the form to the normal match flow.

### Error states

- If URL normalization fails, show a short validation message and do not call the backend.
- If the backend cannot fetch or extract meaningful website content, show a user-facing error banner and leave the textarea unchanged.
- If OpenAI generation fails, show a user-facing error banner and leave the textarea unchanged.

## Architecture

### Frontend

- Extend the existing form in `frontend/index.html` with:
  - optional website URL input
  - `Generate description` button
- Extend `frontend/app.js` with:
  - input locking rules between description and website URL
  - URL validation and button enabled state
  - request flow for a new backend endpoint dedicated to website-derived descriptions
  - success handling that writes the generated description into the description textarea
  - error handling that reuses the current banner or feedback pattern

### Backend

- Add a dedicated route such as `POST /api/profile/from-website`.
- The route accepts one URL string.
- The route normalizes the input into an absolute URL, defaulting to `https://` for bare domains.
- The backend fetches only that page.
- The backend extracts:
  - document title
  - meta description if present
  - visible body text with scripts and styles removed
- The backend passes the extracted site content to a new OpenAI-backed generator that returns a concise company description.
- The backend returns the generated description and a small amount of metadata such as normalized URL and source.

## Component Design

### URL normalization

Rules:

- Accept bare domains like `sentry.io`.
- Accept `http://` and `https://` URLs.
- Reject obviously malformed values.
- Strip surrounding whitespace.
- If no scheme is present, prepend `https://`.

### Website fetcher

Responsibilities:

- Fetch one normalized URL with a short timeout.
- Send a normal browser-like user agent.
- Return raw HTML only for successful HTML responses.
- Reject non-HTML responses and empty bodies.

This should live in a small backend helper so the route and OpenAI logic stay testable.

### Website text extractor

Responsibilities:

- Parse title and meta description.
- Remove scripts, styles, noscript blocks, and markup noise.
- Extract visible text from the homepage body.
- Collapse whitespace and trim the result.
- Enforce a size cap before sending content to OpenAI.

For the MVP, a lightweight extractor based on standard-library parsing and regex cleanup is acceptable if it remains deterministic and tested.

### Description generator

Add a website-aware OpenAI generator alongside the current company-name expander.

Prompt contract:

- Input: normalized URL, page title, meta description, extracted text.
- Output: 4-6 factual sentences describing what the company builds, who it serves, and its strategic focus.
- The output should be optimized as a useful grant-matching company description, not as marketing copy.
- If the page content is too weak to support a result, the generator may return no result and the route should fail gracefully.

## Data Contracts

### Request

`POST /api/profile/from-website`

```json
{
  "url": "sentry.io"
}
```

### Response

```json
{
  "resolved": true,
  "profile": "Sentry provides developer tooling for application monitoring, error tracking, and performance observability...",
  "display_name": "Sentry",
  "source": "website_profile",
  "normalized_url": "https://sentry.io"
}
```

Failure responses should follow the existing API style with a short machine-readable error payload where practical.

## Testing

### Backend tests

- URL normalization for bare domains and fully qualified URLs.
- Website extractor returns compact text from representative HTML.
- Route returns generated description when fetch and generation succeed.
- Route returns a controlled error when fetch fails.
- Route returns a controlled error when extracted text is empty.

### Frontend tests

- Typing a manual description disables the website field and generate button.
- Clearing the manual description re-enables website generation.
- Clicking `Generate description` calls the new endpoint and fills the description textarea.
- Generate failures show an error without overwriting the textarea.

## Risks

- Some sites are JS-rendered and may return thin HTML.
- Some domains may block bot-like fetches.
- Weak homepage content may produce low-quality descriptions.

These risks are acceptable for the MVP because the user still has a manual description fallback.

## Recommendation

Implement the feature as a separate website-to-description endpoint and keep the existing match endpoint unchanged. This keeps the new behavior isolated, preserves the current manual flow, and is realistic for a one-hour MVP.
