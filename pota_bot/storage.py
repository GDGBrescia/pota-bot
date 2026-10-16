"""Dove finiscono le proposte di temi: in memoria (locale e test) o in Firestore (produzione).

Di chi propone non salviamo né nome né id: solo tema, motivo e data.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class Proposal:
    title: str
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProposalStore(Protocol):
    def add(self, proposal: Proposal) -> None: ...


class MemoryProposalStore:
    def __init__(self):
        self.items: list[Proposal] = []

    def add(self, proposal: Proposal) -> None:
        self.items.append(proposal)


class FirestoreProposalStore:
    COLLECTION = "proposals"

    def __init__(self, client=None):
        if client is None:
            from google.cloud import firestore
            client = firestore.Client()
        self._collection = client.collection(self.COLLECTION)

    def add(self, proposal: Proposal) -> None:
        self._collection.add({
            "title": proposal.title,
            "reason": proposal.reason,
            "created_at": proposal.created_at,
        })
