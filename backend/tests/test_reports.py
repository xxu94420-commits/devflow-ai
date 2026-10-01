def test_report_has_cohort_previous_period_and_limits(client):
    client.post("/api/demo/seed")
    result = client.get("/api/reports?mode=demo")
    assert result.status_code == 200
    data = result.json()
    assert "synthetic/demo data" in data["markdown"]
    assert "前期" in data["markdown"]
    assert "Task #" in data["markdown"]
    assert "不代表统计显著性" in data["markdown"]
    assert data["previous"]["end"] == data["current"]["start"]


def test_empty_live_report_does_not_invent_cases(client):
    result = client.get("/api/reports?mode=live").json()
    assert "无已完成任务案例" in result["markdown"]
    assert result["current"]["metrics"]["ai_time_saving"]["value"] is None
