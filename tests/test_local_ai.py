from core.local_ai import model_plan


def test_model_plan_chooses_high_accuracy_team_for_large_machine():
    plan = model_plan({"ram_gb": 64, "vram_gb": 24, "free_disk_gb": 120})
    assert plan["primary_model"] == "qwen3.8:27b"
    assert plan["verifier_model"] == "deepseek-r1:14b"
    assert plan["enable_reranker"] is True


def test_model_plan_has_small_local_fallback_for_limited_machine():
    plan = model_plan({"ram_gb": 16, "vram_gb": 0, "free_disk_gb": 40})
    assert plan["primary_model"] == "qwen3.5:4b"
    assert plan["verifier_model"] == ""
    assert plan["enable_reranker"] is False


def test_model_plan_refuses_insufficient_disk():
    plan = model_plan({"ram_gb": 64, "vram_gb": 24, "free_disk_gb": 10})
    assert plan["tier"] == "Lightweight"
    assert plan["primary_model"] == "qwen3.5:4b"
    assert plan["verifier_model"] == ""