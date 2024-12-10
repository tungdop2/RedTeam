import pytest
from unittest.mock import patch, MagicMock
from neurons.validator.validator import Validator
import datetime

@patch('redteam_core.validator.validator.get_config', MagicMock(return_value=MagicMock()))
@patch('neurons.validator.validator.bt.wallet', MagicMock())
@patch('neurons.validator.validator.bt.dendrite', MagicMock())
def test_scoring_processed_when_time():
    validator = MagicMock(Validator)
    validator.update_miner_commit.return_value = None
    validator.get_revealed_commits.return_value = {"challenge1": (["commit1"], [0])}

    validator.scoring_dates = []

    with patch('neurons.validator.validator.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2023, 10, 10, 15, 0, 0)
        mock_datetime.datetime.strftime.return_value = "2023-10-10"
        validator.get_revealed_commits = MagicMock(return_value={"challenge1": (["commit1"], [0])})
        validator.forward()
        assert "2023-10-10" in validator.scoring_dates

@patch('neurons.validator.validator.bt.wallet', MagicMock())
@patch('neurons.validator.validator.bt.dendrite', MagicMock())
def test_scoring_not_processed_when_not_time():
    validator = Validator()
    validator.scoring_dates = []

    with patch('neurons.validator.validator.datetime') as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2023, 10, 10, 10, 0, 0)
        mock_datetime.datetime.strftime.return_value = "2023-10-10"
        validator.get_revealed_commits = MagicMock(return_value={"challenge1": (["commit1"], [0])})
        validator.forward()
        assert "2023-10-10" not in validator.scoring_dates