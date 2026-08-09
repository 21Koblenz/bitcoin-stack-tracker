# Software Bill of Materials (SBOM)

Bitcoin Stack Tracker ships two complementary software inventories:

1. `SBOM.cdx.json` — release/source inventory for the tracker itself and its direct dependencies.
2. `bitcoin_stack_tracker_dashboard/SBOM.runtime.cdx.json` — generated during the Home Assistant add-on image build from the exact Alpine and Python packages present in that built container.

Both use CycloneDX JSON. An SBOM does **not** make encryption stronger by itself. It improves software-supply-chain security by making third-party components and versions visible so vulnerable or unexpected dependencies can be identified quickly.

The custom Home Assistant integration also pins direct Python requirements in `manifest.json`. Runtime libraries supplied by Home Assistant Core (for example `cryptography`) remain part of the Home Assistant Core runtime and are not vendored by this project.
