import os
from core.strategy_registry.strategy_registry import StrategyRegistry
from core.strategy_registry.registry_loader import RegistryLoader


def generate_inventory_report(registry: StrategyRegistry, output_dir: str):
    strategies = registry.get_all_strategies()

    with open(os.path.join(output_dir, "02_strategy_inventory_report.md"), "w") as f:
        f.write("# Strategy Inventory Report\n\n")
        f.write(
            "This report provides a comprehensive view of all registered strategies, their dependencies, indicators, and current validation states.\n\n"
        )

        for manifest in strategies:
            c = manifest.contract
            f.write(f"## {c.strategy_name} (`{c.strategy_id}`)\n\n")
            f.write(f"- **Implementation File**: `{manifest.file_path}`\n")
            f.write(f"- **Module**: `{manifest.module_path}`\n")
            f.write(f"- **Version**: {c.version}\n")
            f.write(f"- **Owner**: {c.owner}\n")
            f.write(f"- **Primary Market**: {c.primary_market}\n")
            f.write(f"- **Hypothesis**: {c.market_hypothesis}\n")

            f.write("\n### Dependencies & Requirements\n")
            f.write(
                f"- **Indicators**: {', '.join(c.required_indicators) if c.required_indicators else 'None'}\n"
            )
            f.write(
                f"- **Market Data**: {', '.join(c.required_market_data) if c.required_market_data else 'None'}\n"
            )
            f.write(
                f"- **Option Data**: {', '.join(c.required_option_data) if c.required_option_data else 'None'}\n"
            )
            f.write(
                f"- **Required Sessions**: {', '.join(c.required_sessions) if c.required_sessions else 'None'}\n"
            )
            f.write(f"- **Required Liquidity**: {c.required_liquidity}\n")

            f.write("\n### Lifecycle Status\n")
            f.write(f"- **Implementation**: {c.implementation_status.name}\n")
            f.write(f"- **Audit**: {c.audit_status.name}\n")
            f.write(f"- **Replay**: {c.replay_status.name}\n")
            f.write(f"- **Certification**: {c.certification_status.name}\n")
            f.write(f"- **Paper Validation**: {c.paper_validation_status.name}\n")
            f.write(f"- **Production**: {c.production_status.name}\n")
            f.write("\n---\n\n")


if __name__ == "__main__":
    registry = StrategyRegistry()
    # Assume we run from project root
    loader = RegistryLoader(registry, "strategies")
    count, errors = loader.load_all()

    out_dir = "docs/strategy_registry"
    os.makedirs(out_dir, exist_ok=True)

    generate_inventory_report(registry, out_dir)
    print(f"Generated 02_strategy_inventory_report.md for {count} loaded strategies.")
    if errors:
        print("Validation errors during load:")
        for err in errors:
            print(f" - {err}")
