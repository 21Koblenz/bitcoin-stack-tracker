"""Native Home Assistant frontend registration for Bitcoin Stack Tracker."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "bitcoin-stack-tracker"
PANEL_ELEMENT = "bitcoin-stack-tracker-panel"
STATIC_URL = "/api/bitcoin_stack_tracker/frontend"


async def async_register_native_panel(hass: HomeAssistant) -> bool:
    """Register the Bitcoin Stack native Home Assistant sidebar panel.

    Secrets therefore travel directly from the browser-side native panel to
    Home Assistant Core; the Tor/network add-on is not part of that data path.

    Registration is deliberately idempotent and may be called from both
    ``async_setup`` and ``async_setup_entry``.  This makes upgrades robust when
    Home Assistant reloads a config entry or when the frontend has already
    created an older copy of the same panel path.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})

    frontend_dir = Path(__file__).parent / "frontend"
    if not domain_data.get("_native_static_registered"):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_URL, str(frontend_dir), cache_headers=False)]
            )
        except RuntimeError as err:
            # A custom integration reload can leave the same static route in
            # aiohttp.  That is safe: the route still points at this integration
            # directory, whose files were replaced on disk during the upgrade.
            _LOGGER.debug("Bitcoin Stack frontend static path already registered: %s", err)
        domain_data["_native_static_registered"] = True

    if domain_data.get("_native_panel_registered") and frontend.async_panel_exists(
        hass, PANEL_URL_PATH
    ):
        return True

    # When upgrading/reloading in a running Core, replace an older registration
    # instead of letting panel_custom raise "Overwriting panel ...".
    if frontend.async_panel_exists(hass, PANEL_URL_PATH):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)

    try:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name=PANEL_ELEMENT,
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title="Bitcoin Stack",
            sidebar_icon="mdi:bitcoin",
            module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
            embed_iframe=False,
            require_admin=False,
            config={
                "frontend_url": f"{STATIC_URL}/index.html?native=1&v={VERSION}",
                "version": VERSION,
                "architecture": "native-core-panel",
            },
        )
    except Exception:  # noqa: BLE001 - never take the whole integration down for UI registration
        domain_data["_native_panel_registered"] = False
        _LOGGER.exception(
            "Could not register Bitcoin Stack native panel. The tracker backend remains loaded; "
            "restart Home Assistant Core after updating the custom integration."
        )
        return False

    domain_data["_native_panel_registered"] = True
    _LOGGER.info("Bitcoin Stack native panel registered at /%s", PANEL_URL_PATH)
    return True
