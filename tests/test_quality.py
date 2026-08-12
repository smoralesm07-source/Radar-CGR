from radar_cgr.quality import public_provider_collisions


def test_public_organization_is_not_kept_as_provider():
    orgs=[{"organization_id":"O1","name":"Corporación Nacional Forestal"}]
    providers=[{"provider_id":"P1","name":"Corporación Nacional Forestal"},{"provider_id":"P2","name":"Spill Tech SpA"}]
    assert public_provider_collisions(orgs,providers)=={"P1"}
