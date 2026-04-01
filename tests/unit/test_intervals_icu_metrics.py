"""Tests for Intervals.icu athlete metric updates."""

import pytest
from unittest.mock import patch, MagicMock
from server.services.intervals_icu import update_ftp, update_weight

@patch("server.services.intervals_icu._get_credentials")
@patch("httpx.put")
def test_update_ftp_success(mock_put, mock_credentials):
    """Test successful FTP update."""
    mock_credentials.return_value = ("api_key", "12345")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ftp": 280}
    mock_put.return_value = mock_response

    result = update_ftp(280)

    assert result["status"] == "success"
    assert result["data"] == {"ftp": 280}
    
    # Check that it called the correct URL with athlete ID 0
    args, kwargs = mock_put.call_args
    assert args[0] == "https://intervals.icu/api/v1/athlete/0/sport-settings/Ride"
    assert kwargs["json"] == {"ftp": 280}
    assert kwargs["auth"] == ("API_KEY", "api_key")

@patch("server.services.intervals_icu._get_credentials")
@patch("httpx.put")
def test_update_weight_success(mock_put, mock_credentials):
    """Test successful weight update."""
    mock_credentials.return_value = ("api_key", "12345")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"weight": 75.5}
    mock_put.return_value = mock_response

    # Test with explicit date
    result = update_weight(75.5, "2026-03-25")

    assert result["status"] == "success"
    assert result["data"] == {"weight": 75.5}
    
    args, kwargs = mock_put.call_args
    assert args[0] == "https://intervals.icu/api/v1/athlete/12345/wellness/2026-03-25"
    assert kwargs["json"] == {"weight": 75.5}
    assert kwargs["auth"] == ("API_KEY", "api_key")

@patch("server.services.intervals_icu._get_credentials")
def test_update_ftp_not_configured(mock_credentials):
    """Test update when intervals.icu is not configured."""
    mock_credentials.return_value = (None, None)
    
    result = update_ftp(280)
    assert result["status"] == "error"
    assert "not configured" in result["message"]

@patch("server.services.intervals_icu._get_credentials")
@patch("httpx.put")
def test_update_ftp_failure(mock_put, mock_credentials):
    """Test FTP update failure (e.g. 401)."""
    mock_credentials.return_value = ("api_key", "12345")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_put.return_value = mock_response

    result = update_ftp(280)

    assert result["status"] == "error"
    assert result["code"] == 401
    assert result["message"] == "Unauthorized"
