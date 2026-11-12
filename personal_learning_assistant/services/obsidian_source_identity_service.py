"""Conservative source identities and explicit legacy inventory reconciliation."""
from personal_learning_assistant.repositories.sqlite.obsidian_source_identity_repository import ObsidianSourceIdentityRepository


class ObsidianSourceIdentityService(ObsidianSourceIdentityRepository):
    @staticmethod
    def resolve_source(manifest, connection_id, path):
        if manifest.get("connection_id") != connection_id:
            raise LookupError("The source belongs to a different connection.")
        for item in manifest.get("items", []):
            if item["relative_path"] == path:
                return dict(item)
        raise LookupError("The source path is absent from this manifest.")

    @staticmethod
    def resolve_study_identity(item_id):
        import uuid
        return "obsidian-source:" + str(uuid.UUID(str(item_id)))
