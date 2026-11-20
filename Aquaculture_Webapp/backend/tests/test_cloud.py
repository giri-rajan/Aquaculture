"""Cloud persistence against in-memory stand-ins for Firestore and Cloud Storage (no Google account needed)."""
from aquasentinel.cloud import CloudMirror
from aquasentinel.store import Store


class _Snap:
    def __init__(self, col, key):
        self.col, self.key = col, key
        self.reference = self

    def to_dict(self):
        return self.col.docs[self.key]

    def delete(self):
        self.col.docs.pop(self.key, None)


class _Doc:
    def __init__(self, col, key):
        self.col, self.key = col, key

    def set(self, data):
        self.col.docs[self.key] = data


class _Col:
    def __init__(self):
        self.docs = {}

    def document(self, key):
        return _Doc(self, key)

    def stream(self):
        return [_Snap(self, k) for k in list(self.docs)]


class FakeFirestore:
    def __init__(self):
        self.cols = {}

    def collection(self, name):
        return self.cols.setdefault(name, _Col())


class _Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_string(self, data, content_type=None):
        self.store[self.name] = data

    def exists(self):
        return self.name in self.store

    def download_as_bytes(self):
        return self.store[self.name]


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return _Blob(self.blobs, name)


def test_findings_survive_a_new_container(tmp_path):
    fs = FakeFirestore()
    first = Store(tmp_path / "a.db", mirror=CloudMirror(fs))
    aid = first.insert("anomalies", started=1.0, zone="SW", params=["ph"], peak={"ph": 9.1}, status="open")
    first.update("anomalies", aid, status="traced", source_info={"place": "South-west drain"})
    first.insert("missions", ts=2.0, request="survey", waypoints=[[11.0, 77.0], [11.1, 77.1]], status="active")
    first.add_reading({"ts": 3.0, "zone": "SW", "ph": 9.0})          # readings stay local: too many for Firestore
    first.mirror.flush()
    assert "aquasentinel_readings" not in fs.cols

    # Cloud Run scaled to zero: a new container starts with an empty database and the same Firestore
    second = Store(tmp_path / "b.db", mirror=CloudMirror(fs))
    row = second.get("anomalies", aid)
    assert row["status"] == "traced" and row["source_info"]["place"] == "South-west drain" and row["params"] == ["ph"]
    assert second.latest("missions")[0]["waypoints"] == [[11.0, 77.0], [11.1, 77.1]]
    assert second.insert("anomalies", started=4.0, zone="N", status="open") == aid + 1    # ids carry on, no reuse

    second.reset()
    second.mirror.flush()
    assert all(not c.docs for c in fs.cols.values())


def test_frames_and_pdfs_go_to_the_bucket(tmp_path):
    bucket = FakeBucket()
    m = CloudMirror(bucket=bucket)
    m.put_blob("frames/3-source.jpg", b"jpeg", "image/jpeg")
    m.flush()
    assert m.get_blob("frames/3-source.jpg") == b"jpeg" and m.get_blob("frames/missing.jpg") is None


def test_a_failed_cloud_write_does_not_break_the_store(tmp_path):
    class Broken(FakeFirestore):
        def collection(self, name):
            raise RuntimeError("network down")

    st = Store(tmp_path / "c.db", mirror=CloudMirror(Broken()))
    aid = st.insert("anomalies", started=1.0, zone="S", status="open")
    st.mirror.flush()
    assert st.get("anomalies", aid)["zone"] == "S"
