"""Integration tests for athlete metric synchronization."""

import pytest
from unittest.mock import patch, MagicMock

def test_router_update_ftp_triggers_sync(client):
    """Verify that updating FTP via the router calls update_ftp."""
    with patch("server.routers.athlete.require_write"), \
         patch("server.routers.athlete.set_athlete_setting"), \
         patch("server.services.intervals_icu.update_ftp") as mock_update_ftp:
        
        mock_update_ftp.return_value = {"status": "success"}
        
        response = client.put(
            "/api/athlete/settings",
            json={"key": "ftp", "value": "285"}
        )
        
        assert response.status_code == 200
        mock_update_ftp.assert_called_once_with(285)

def test_router_update_weight_triggers_sync(client):
    """Verify that updating weight via the router calls update_weight."""
    with patch("server.routers.athlete.require_write"), \
         patch("server.routers.athlete.set_athlete_setting"), \
         patch("server.services.intervals_icu.update_weight") as mock_update_weight:
        
        mock_update_weight.return_value = {"status": "success"}
        
        response = client.put(
            "/api/athlete/settings",
            json={"key": "weight_kg", "value": "75.5"}
        )
        
        assert response.status_code == 200
        mock_update_weight.assert_called_once_with(75.5)

def test_planning_tool_update_ftp_triggers_sync():
    """Verify that updating FTP via planning tools calls update_ftp."""
    from server.coaching.planning_tools import update_athlete_setting
    
    with patch("server.coaching.planning_tools.set_athlete_setting"), \
         patch("server.services.intervals_icu.update_ftp") as mock_update_ftp:
        
        mock_update_ftp.return_value = {"status": "success"}
        
        result = update_athlete_setting("ftp", "290")
        
        assert result["status"] == "success"
        assert result["sync_status"] == "synced"
        mock_update_ftp.assert_called_once_with(290)

def test_planning_tool_update_weight_triggers_sync():
    """Verify that updating weight via planning tools calls update_weight."""
    from server.coaching.planning_tools import update_athlete_setting
    
    with patch("server.coaching.planning_tools.set_athlete_setting"), \
         patch("server.services.intervals_icu.update_weight") as mock_update_weight:
        
        mock_update_weight.return_value = {"status": "success"}
        
        result = update_athlete_setting("weight_kg", "76.0", "2026-03-25")
        
        assert result["status"] == "success"
        assert result["sync_status"] == "synced"
        mock_update_weight.assert_called_once_with(76.0, "2026-03-25")
