from pota_bot.storage import FirestoreProposalStore, MemoryProposalStore, Proposal


def test_memory_store_keeps_proposals():
    store = MemoryProposalStore()
    store.add(Proposal(title="RAG in azienda", reason="interessa a molti"))
    assert [p.title for p in store.items] == ["RAG in azienda"]


class FakeCollection:
    def __init__(self):
        self.added = []

    def add(self, data):
        self.added.append(data)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


def test_firestore_store_writes_title_reason_and_date_only():
    client = FakeFirestore()
    FirestoreProposalStore(client=client).add(Proposal(title="Agenti", reason="perché sì"))
    [doc] = client.collections["proposals"].added
    assert set(doc) == {"title", "reason", "created_at"}
    assert doc["title"] == "Agenti"
    assert doc["created_at"].tzinfo is not None
