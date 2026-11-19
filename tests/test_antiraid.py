import pytest
from pydantic import ValidationError

from nexus_core.modules import REGISTRY, parse_config
from nexus_core.modules.antiraid import AntiraidConfig, antiraid_default


def test_defaults_are_safe():
    cfg = antiraid_default("es")
    assert REGISTRY["antiraid"].available
    assert cfg.verification.enabled is False and cfg.verification.method == "captcha"
    assert cfg.min_account_age_days == 0  # el detector de cuentas nuevas empieza apagado
    assert cfg.raid_action == "alert"  # por defecto solo avisa, nunca expulsa
    assert parse_config("antiraid", {}, "en").verification.button_label == "Verify me"


def test_verification_needs_channel_and_role():
    data = antiraid_default().model_dump(mode="json")
    data["verification"]["enabled"] = True
    with pytest.raises(ValidationError, match="verification_incomplete"):
        AntiraidConfig.model_validate(data)
    data["verification"]["channel_id"] = "111111111111111111"
    data["verification"]["role_id"] = "222222222222222222"
    assert AntiraidConfig.model_validate(data).verification.enabled


def test_quarantine_action_needs_role():
    data = antiraid_default().model_dump(mode="json") | {"min_account_age_days": 7, "young_action": "quarantine"}
    with pytest.raises(ValidationError, match="quarantine_role_required"):
        AntiraidConfig.model_validate(data)
    data["quarantine_role_id"] = "333333333333333333"
    assert AntiraidConfig.model_validate(data).young_action == "quarantine"


def test_limits():
    data = antiraid_default().model_dump(mode="json") | {"raid_joins": 1}
    with pytest.raises(ValidationError):
        AntiraidConfig.model_validate(data)


def test_gate_plan_hides_only_public_channels():
    from nexus_core.modules.antiraid import GateChannel, plan_gate

    chans = [
        GateChannel(id=1, is_category=True),                       # categoría «Texto»
        GateChannel(id=2, in_category=True, synced=True),          # #general (hereda)
        GateChannel(id=3, in_category=True, synced=True),          # #reglas (pública, hereda)
        GateChannel(id=4, in_category=True, synced=False),         # #memes (permisos propios)
        GateChannel(id=5, in_category=True, everyone_can_view=False),  # #staff (privado)
        GateChannel(id=6),                                         # canal sin categoría
        GateChannel(id=7, is_category=True, everyone_can_view=False),  # categoría privada
    ]
    public, hidden = plan_gate(chans, {3})
    assert public == [3]
    assert hidden == [1, 4, 6]  # #general se oculta al heredar de su categoría; lo privado no se toca


def test_gate_fields_roundtrip():
    data = antiraid_default().model_dump(mode="json")
    data["verification"]["public_channel_ids"] = ["111111111111111111"]
    data["verification"]["gate_backup"] = {"e:111111111111111111": [1024, 0], "r:222222222222222222": None}
    cfg = AntiraidConfig.model_validate(data)
    assert cfg.verification.public_channel_ids == [111111111111111111]
    assert cfg.verification.gate_backup["r:222222222222222222"] is None
