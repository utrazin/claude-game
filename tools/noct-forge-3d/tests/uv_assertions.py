"""Compare concrete UV coordinates in tests without production signatures."""
def uv_state(data):
    return {"resolution": data.get("resolution"), "faces": [
        {name: {key: face.get(key) for key in ("uv", "rotation", "vertices")}
         for name, face in element.get("faces", {}).items()}
        for element in data.get("elements", [])]}
