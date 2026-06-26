from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.registry_errors import MissingMetadataError
import dataclasses


class StrategyManifest:
    def __init__(self, contract: StrategyContract, file_path: str, module_path: str):
        self.contract = contract
        self.file_path = file_path
        self.module_path = module_path
        self.validate()

    def validate(self):
        # Validate that no field in the contract is empty (for lists and strings)
        contract_dict = dataclasses.asdict(self.contract)

        required_non_empty_fields = [
            "strategy_id",
            "version",
            "market_hypothesis",
            "entry_rules_summary",
            "exit_rules_summary",
            "stop_logic_summary",
            "target_logic_summary",
            "required_indicators",
            "required_market_data",
        ]

        for field in required_non_empty_fields:
            val = contract_dict.get(field)
            if val is None or (isinstance(val, (str, list)) and len(val) == 0):
                raise MissingMetadataError(
                    f"Strategy {self.contract.strategy_id} is missing critical metadata: {field}"
                )
