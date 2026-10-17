from dgate.listcache import snapshot_key


def test_the_key_names_every_argument_but_the_connection_in_a_fixed_order():
    a = snapshot_key("tenders", {"status": "closed", "country": None, "conn": object(), "with_meta": True})
    b = snapshot_key("tenders", {"with_meta": True, "country": None, "status": "closed", "conn": object()})
    assert a == b == "tenders?country=None&status=closed&with_meta=True"


def test_the_meta_flag_is_a_flag_not_a_dependency_object():
    assert snapshot_key("t", {"with_meta": object()}) == "t?with_meta=False"
