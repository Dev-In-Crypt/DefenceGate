"""Source connectors.

Every connector fetches and yields payloads and does nothing else. Parsing that
can differ between sources lives in the connector; everything shared lives in
normalise.py, so that a new source cannot quietly invent its own schema.
"""

# Identify the client honestly. These are public administration and NATO agency
# endpoints; anonymous scraping traffic is how access gets withdrawn.
USER_AGENT = "dgate/0.1 (+https://github.com/defencegate; contact in repository)"
