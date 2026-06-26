import os
import re


def discover_and_generate(strategies_dir: str, docs_dir: str):
    inventory_01 = [
        "# Strategy Inventory\n\n",
        "A reverse-engineered list of discovered strategies.\n\n",
    ]
    inventory_02 = [
        "# Strategy Inventory Report\n\n",
        "Detailed report of existing strategies.\n\n",
    ]
    heuristics_03 = [
        "# Strategy Heuristic Audit\n\n",
        "Code scan for magic numbers, TODOs, FIXMEs, hardcoded thresholds, and heuristics.\n\n",
    ]

    heuristics_terms = [
        r"TODO",
        r"FIXME",
        r"heuristic",
        r"hardcoded",
        r"confidence",
        r"chance",
        r"probability",
        r"edge",
        r"\b\d+\.\d+\b",
        r"\b\d{2,}\b",
    ]

    for root, _, files in os.walk(strategies_dir):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                file_path = os.path.join(root, file)
                module_path = file_path.replace(os.sep, ".")
                if module_path.startswith("strategies."):
                    module_path = module_path

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    lines = content.split("\n")

                # Simple extraction of class names
                classes = re.findall(r"class\s+([A-Za-z0-9_]+Strategy)\b", content)
                classes += re.findall(r"class\s+([A-Za-z0-9_]+Arbitrage)\b", content)
                classes += re.findall(r"class\s+([A-Za-z0-9_]+Intraday)\b", content)
                classes += re.findall(
                    r"class\s+([A-Za-z0-9_]+[A-Za-z0-9_])\b(?=\(.*\):|:)", content
                )

                # Heuristics Audit
                findings = []
                for idx, line in enumerate(lines):
                    for term in heuristics_terms:
                        if re.search(term, line, re.IGNORECASE):
                            findings.append((idx + 1, line.strip(), term))

                # We filter to classes that look like strategies based on naming or being in the strategies folder
                if classes:
                    strategy_name = classes[0]
                    inventory_01.append(f"## {strategy_name}\n")
                    inventory_01.append(f"- **Strategy ID**: `pending_migration`\n")
                    inventory_01.append(f"- **File Path**: `{file_path}`\n")
                    inventory_01.append(f"- **Module**: `{module_path}`\n")
                    inventory_01.append(f"- **Current Status**: UNKNOWN\n")
                    inventory_01.append(f"- **Candidate Generation Path**: Unknown\n")
                    inventory_01.append(f"- **Ranking Path**: Unknown\n")
                    inventory_01.append(f"- **Execution Path**: Unknown\n\n")

                    inventory_02.append(f"## {strategy_name}\n")
                    inventory_02.append(f"- **Implementation File**: `{file_path}`\n")
                    inventory_02.append(
                        f"- **Dependencies**: Unknown (pending contract)\n"
                    )
                    inventory_02.append(f"- **Indicators**: Unknown\n")
                    inventory_02.append(f"- **Parameters**: Unknown\n")
                    inventory_02.append(f"- **Lifecycle Status**: NOT_STARTED\n")
                    inventory_02.append(f"- **Missing Metadata**: ALL\n")
                    inventory_02.append(f"- **Audit Readiness**: UNAUDITED\n\n")

                if findings:
                    heuristics_03.append(f"### {file_path}\n")
                    for ln, text, term in findings:
                        # Limit text length to avoid huge markdown files
                        if len(text) > 100:
                            text = text[:100] + "..."
                        heuristics_03.append(
                            f"- **Line {ln}** (Matched `{term}`): `{text}`\n"
                        )
                    heuristics_03.append("\n")

    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "01_strategy_inventory.md"), "w") as f:
        f.writelines(inventory_01)
    with open(os.path.join(docs_dir, "02_strategy_inventory_report.md"), "w") as f:
        f.writelines(inventory_02)
    with open(os.path.join(docs_dir, "03_strategy_heuristic_inventory.md"), "w") as f:
        f.writelines(heuristics_03)


if __name__ == "__main__":
    discover_and_generate("strategies", "docs/strategy_registry")
