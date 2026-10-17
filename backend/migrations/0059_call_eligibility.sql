-- Eligibility of EU calls read from their call documents (17 October 2026).
-- The portal's own condition text is a template that points to the call document, so the
-- rules (countries, who may apply, consortium, ownership control, rate) have to be read from
-- the PDF. Three tables, all derived and replaceable:
--   call_document_text  the text of one call document, by URL, with its hash: quotes can be
--                       checked against it and a re-run does not fetch again
--   call_eligibility    what the model said about that document, field by field, each with a
--                       confidence, a quote, and whether the quote was found in the text
--   llm_usage           what the language model cost, by day, task and model: the monthly cap
CREATE TABLE IF NOT EXISTS call_document_text (
    url         TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    pages       INT NOT NULL,
    chars       INT NOT NULL,
    truncated   BOOLEAN NOT NULL DEFAULT FALSE,
    text        TEXT NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_eligibility (
    url             TEXT PRIMARY KEY REFERENCES call_document_text(url),
    fields          JSONB NOT NULL,
    model           TEXT NOT NULL,
    prompt_version  INT NOT NULL,
    input_tokens    INT NOT NULL,
    output_tokens   INT NOT NULL,
    cost_usd        NUMERIC(10, 5) NOT NULL,
    extracted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_usage (
    day            DATE NOT NULL,
    task           TEXT NOT NULL,
    model          TEXT NOT NULL,
    requests       INT NOT NULL DEFAULT 0,
    input_tokens   BIGINT NOT NULL DEFAULT 0,
    output_tokens  BIGINT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(10, 5) NOT NULL DEFAULT 0,
    PRIMARY KEY (day, task, model)
);

GRANT SELECT ON call_eligibility TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON call_document_text, call_eligibility, llm_usage TO dgate_worker;
