"""WP-97: the primes beyond SIPRI (each with its public source) and the dealers of parts and tyres that "who to approach" sets apart
as competitors or distributors (`demand.prime_of`, `demand.distributor_of`), read on the stored normal form of a name."""

from __future__ import annotations

import pytest

from dgate import demand
from dgate.normalise import normalise_org_name


@pytest.mark.parametrize("raw, group", [
    ("URO, Vehículos Especiales, S.A.", "URO Vehículos Especiales"),
    ("IVECO DEFENCE VEHICLES S.P.A.", "Iveco Defence Vehicles (Leonardo)"),
    ("Escribano Mechanical & Engineering, S.L.U.", "Escribano Mechanical & Engineering"),
    ("Rheinmetall Expal Munitions S.A.", "Rheinmetall"),
    ("Santa Bárbara Sistemas, S.A.", "General Dynamics (GDELS)"),
    ("Navantia S.A., S.M.E.", "Navantia"),
])
def test_spanish_and_eu_vehicle_and_defence_makers_are_marked_with_a_source(raw, group):
    p = demand.prime_of(normalise_org_name(raw))
    assert p is not None and p["group"] == group
    assert p["sourceUrl"].startswith("https://") and p["source"]


@pytest.mark.parametrize("raw", ["Iveco España SL", "Talleres URO SL", "Escribano Reformas SL"])
def test_civil_namesakes_are_not_marked(raw):
    assert demand.prime_of(normalise_org_name(raw)) is None


@pytest.mark.parametrize("raw, dealer", [
    ("Recambios Fran SL", True), ("REPUESTOS MENENDEZ, S.L.", True), ("Neumáticos Soledad SL", True),
    ("Continental Tires España SA", True), ("Euromaster Automoción y Servicios SA", True), ("Ferretería Industrial Sur SL", True),
    ("Fundiciones del Norte SA", False), ("URO, Vehículos Especiales, S.A.", False), ("Talleres Mecánicos Pérez SL", False),
])
def test_dealers_of_parts_tyres_and_hardware_are_told_apart_by_name(raw, dealer):
    assert demand.distributor_of(normalise_org_name(raw)) is dealer
