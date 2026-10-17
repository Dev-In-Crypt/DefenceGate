"""Layer 3 of the product: readiness. What separates a company from taking part in a programme.

    content.py   the data shapes (requirements, issuers, programmes, rules)
    engine.py    assess(profile, statuses, programme): the pure rules engine, no model
    roadmap.py   the ordered steps with cost and time, and the timing against a call's deadline
    seed.py      the seed file `seeds/requirements.json`, validated and loaded
    api.py       the public catalogue and the stateless assessment

Nothing about a company is stored: the profile and the statuses are sent with each request.
"""
