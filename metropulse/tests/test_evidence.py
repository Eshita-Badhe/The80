from datetime import timedelta
from pathlib import Path

from metropulse.engines import EvidenceEngine, IncidentEngine
from metropulse.ingest import load_dataset
from metropulse.schemas import EvidenceType


DATA = Path(__file__).parents[2] / "data"


def test_ticket_resolution_is_hidden_until_closed():
    dataset = load_dataset(DATA)
    incident = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])[0]
    ticket = next((item for item in dataset["tickets"] if item.equipment_id in incident.equipment_ids), None)
    if ticket is None or ticket.closed_at is None:
        return
    engine = EvidenceEngine(dataset["topology"])
    before = engine.build(incident, dataset["events"], [ticket], [], as_of=ticket.closed_at - timedelta(seconds=1))
    after = engine.build(incident, dataset["events"], [ticket], [], as_of=ticket.closed_at + timedelta(seconds=1))
    before_ticket = next((item for item in before if item.type is EvidenceType.TICKET), None)
    after_ticket = next((item for item in after if item.type is EvidenceType.TICKET), None)
    if before_ticket is not None:
        assert "resolution" not in before_ticket.attributes
    if after_ticket is not None:
        assert "resolution" in after_ticket.attributes
