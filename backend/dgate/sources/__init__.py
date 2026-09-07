"""Source connectors.

Every connector fetches and yields payloads and does nothing else. Parsing that
can differ between sources lives in the connector; everything shared lives in
normalise.py, so that a new source cannot quietly invent its own schema.
"""

# Identify the client honestly. These are public administration and NATO agency
# endpoints; anonymous scraping traffic is how access gets withdrawn.
USER_AGENT = "dgate/0.1 (+https://github.com/Dev-In-Crypt/DefenceGate)"


def _use_system_trust_store() -> bool:
    """Trust the operating system's certificate store when we can.

    Corporate and cloud networks routinely terminate TLS with their own CA. On
    such a machine every connector fails with CERTIFICATE_VERIFY_FAILED against
    endpoints that are perfectly healthy, which reads as an outage rather than
    a local trust problem. `truststore` hands Python the OS trust store, where
    that CA already lives. Optional: absent, behaviour is unchanged.
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


SYSTEM_TRUST_STORE = _use_system_trust_store()
