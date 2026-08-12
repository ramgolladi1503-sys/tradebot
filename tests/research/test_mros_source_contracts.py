import pytest
from research.mros_certification.source_contracts import SourceContract, freeze_source_contracts
def test_contracts_freeze_without_inventing_authority():
    result=freeze_source_contracts((SourceContract('India VIX','repository-authority','Asia/Kolkata','index','09:00',300),))
    assert result['status']=='SPEC_FROZEN' and result['immutable']
def test_unknown_authority_is_rejected():
    with pytest.raises(ValueError,match='SOURCE_AUTHORITY_REQUIRED'):
        freeze_source_contracts((SourceContract('GIFT Nifty','', 'Asia/Kolkata','index','09:00',300),))
