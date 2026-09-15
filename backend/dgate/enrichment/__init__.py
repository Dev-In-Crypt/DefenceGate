"""LLM enrichment: translation, summaries and classification of archived notices.

Three parts, plan task M1-04:

    base.py     what a task is -- model, output schema, prompt, input hash
    queue.py    which notices need a task run, as rows in enrichment_job
    runner.py   running the jobs, synchronously or through the Batches API

The rule the whole package is built around: a result is keyed by a hash of
exactly what was sent, so the same input is never paid for twice -- not on a
re-run, not after a restart, not for a second notice with identical text.
"""
