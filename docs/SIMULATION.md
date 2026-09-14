# Simulation mode

```bash
APP_MODE=simulation
drop-agent-sim --query hoodie
```

The simulation uses fixture products and a configured USD/EUR rate plus explicitly labeled eBay test fees. It demonstrates the complete lifecycle and emits audit events. It does not publish listings, spend ad money, create supplier orders, contact customers, or call live integrations.

The simulation is the required pre-live acceptance gate. A live configuration must not be considered safe until it has equivalent integration, approval, and rollback tests.
