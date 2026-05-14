"""
Tests for video, image, ui-ux, and ios-testing skills.

All four have deterministic heuristic implementations so no mocking is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.skill_loader import register_all_as_python_packages
register_all_as_python_packages()

from core.skills.video.main import run as video_run
from core.skills.image.main import run as image_run
from core.skills.ui_ux.main import run as ui_run
from core.skills.ios_testing.main import run as ios_run


# ===========================================================================
# video skill
# ===========================================================================

class TestVideoContract:
    def test_returns_success(self):
        r = video_run({"topic": "real estate fund"})
        assert r["status"] == "success"

    def test_has_data_and_meta(self):
        r = video_run({"topic": "x"})
        assert "data" in r
        assert "meta" in r

    def test_meta_skill_name(self):
        assert video_run({})["meta"]["skill"] == "video"

    def test_invoke_alias(self):
        from core.skills.video.main import invoke
        assert invoke is video_run


class TestVideoScript:
    def test_default_task_is_script(self):
        r = video_run({"topic": "cap rate", "style": "explainer"})
        assert "scenes" in r["data"]
        assert "script" in r["data"]

    def test_scenes_match_style_template(self):
        r = video_run({"topic": "fund", "style": "ad"})
        names = [s["name"] for s in r["data"]["scenes"]]
        assert "hook" in names
        assert "cta" in names

    def test_total_duration_consistent(self):
        r = video_run({"topic": "x", "style": "promo", "duration_seconds": 60})
        scenes = r["data"]["scenes"]
        total = sum(s["duration_seconds"] for s in scenes)
        assert total <= 60

    def test_duration_reflected_in_meta(self):
        r = video_run({"topic": "x", "duration_seconds": 90})
        assert r["meta"]["duration_seconds"] == 90

    def test_each_scene_has_required_keys(self):
        r = video_run({"topic": "real estate", "style": "explainer"})
        for scene in r["data"]["scenes"]:
            assert "name" in scene
            assert "duration_seconds" in scene
            assert "copy" in scene

    def test_unknown_style_falls_back_to_explainer(self):
        r = video_run({"topic": "x", "style": "unknown-style"})
        # explainer has 6 scenes
        assert len(r["data"]["scenes"]) == 6


class TestVideoStoryboard:
    def test_storyboard_has_frames(self):
        r = video_run({"topic": "fund", "task": "storyboard", "style": "ad"})
        assert "frames" in r["data"]
        assert len(r["data"]["frames"]) > 0

    def test_frame_has_scene_and_visual(self):
        r = video_run({"topic": "x", "task": "storyboard"})
        for frame in r["data"]["frames"]:
            assert "scene" in frame
            assert "visual" in frame
            assert "duration" in frame


class TestVideoRenderSpec:
    def test_render_spec_has_codec(self):
        r = video_run({"topic": "x", "task": "render_spec"})
        assert r["data"]["codec"] == "h264"
        assert r["data"]["format"] == "mp4"
        assert r["data"]["fps"] == 30

    def test_16_9_aspect_ratio(self):
        r = video_run({"topic": "x", "task": "render_spec", "aspect_ratio": "16:9"})
        assert r["data"]["width"] == 1920
        assert r["data"]["height"] == 1080

    def test_9_16_aspect_ratio(self):
        r = video_run({"topic": "x", "task": "render_spec", "aspect_ratio": "9:16"})
        assert r["data"]["width"] == 1080
        assert r["data"]["height"] == 1920

    def test_1_1_aspect_ratio(self):
        r = video_run({"task": "render_spec", "aspect_ratio": "1:1"})
        assert r["data"]["width"] == r["data"]["height"]


class TestVideoSceneGraph:
    def test_scene_graph_has_nodes_and_edges(self):
        r = video_run({"topic": "x", "task": "scene_graph", "style": "ad"})
        assert "nodes" in r["data"]
        assert "edges" in r["data"]

    def test_edges_link_sequential_nodes(self):
        r = video_run({"topic": "x", "task": "scene_graph", "style": "ad"})
        nodes = r["data"]["nodes"]
        edges = r["data"]["edges"]
        assert len(edges) == len(nodes) - 1
        for i, edge in enumerate(edges):
            assert edge["from"] == i
            assert edge["to"] == i + 1


# ===========================================================================
# image skill
# ===========================================================================

class TestImageContract:
    def test_returns_success(self):
        assert image_run({"concept": "urban skyline"})["status"] == "success"

    def test_has_data_and_meta(self):
        r = image_run({"concept": "x"})
        assert "data" in r
        assert "meta" in r

    def test_meta_skill_name(self):
        assert image_run({})["meta"]["skill"] == "image"

    def test_invoke_alias(self):
        from core.skills.image.main import invoke
        assert invoke is image_run


class TestImageGeneratePrompt:
    def test_default_task_returns_prompt(self):
        r = image_run({"concept": "multifamily building"})
        assert "prompt" in r["data"]
        assert "full_prompt" in r["data"]

    def test_full_prompt_contains_concept(self):
        r = image_run({"concept": "cap rate chart"})
        assert "cap rate chart" in r["data"]["full_prompt"]

    def test_style_modifier_applied(self):
        r = image_run({"concept": "fund", "style": "luxury"})
        assert "luxury" in r["data"]["full_prompt"] or "gold" in r["data"]["full_prompt"]

    def test_count_generates_multiple_prompts(self):
        r = image_run({"concept": "building", "count": 3})
        assert len(r["data"]["prompts"]) == 3

    def test_negative_prompt_present(self):
        r = image_run({"concept": "aerial view"})
        assert "negative_prompt" in r["data"]
        assert len(r["data"]["negative_prompt"]) > 0

    def test_dimensions_reflected_in_output(self):
        dims = {"width": 512, "height": 512}
        r = image_run({"concept": "x", "dimensions": dims})
        assert r["data"]["dimensions"] == dims


class TestImageBatchPipeline:
    def test_batch_returns_jobs(self):
        r = image_run({"concept": "property", "task": "batch_pipeline", "count": 4})
        assert r["data"]["pipeline"] == "batch"
        assert len(r["data"]["jobs"]) == 4

    def test_jobs_have_required_keys(self):
        r = image_run({"concept": "fund", "task": "batch_pipeline", "count": 2})
        for job in r["data"]["jobs"]:
            assert "id" in job
            assert "prompt" in job
            assert "status" in job

    def test_estimated_seconds_scaled_by_count(self):
        r2 = image_run({"concept": "x", "task": "batch_pipeline", "count": 2})
        r4 = image_run({"concept": "x", "task": "batch_pipeline", "count": 4})
        assert r4["data"]["estimated_seconds"] > r2["data"]["estimated_seconds"]


class TestImageEditSpec:
    def test_edit_spec_has_edits(self):
        r = image_run({"concept": "photo", "task": "edit_spec",
                       "edits": ["crop", "sharpen"]})
        assert r["data"]["edits"] == ["crop", "sharpen"]

    def test_default_edits_applied_when_none_given(self):
        r = image_run({"concept": "photo", "task": "edit_spec"})
        assert len(r["data"]["edits"]) > 0

    def test_output_format_is_png(self):
        r = image_run({"concept": "x", "task": "edit_spec"})
        assert r["data"]["output_format"] == "png"


class TestImageAssetVariants:
    def test_asset_variants_returns_four_sizes(self):
        r = image_run({"concept": "building", "task": "asset_variants"})
        assert len(r["data"]["variants"]) == 4

    def test_variant_names_present(self):
        r = image_run({"concept": "x", "task": "asset_variants"})
        names = {v["name"] for v in r["data"]["variants"]}
        assert {"hero", "square", "story", "thumbnail"} == names

    def test_each_variant_has_dimensions(self):
        r = image_run({"concept": "x", "task": "asset_variants"})
        for v in r["data"]["variants"]:
            assert "dimensions" in v
            assert v["dimensions"]["width"] > 0
            assert v["dimensions"]["height"] > 0


# ===========================================================================
# ui-ux skill
# ===========================================================================

class TestUiUxContract:
    def test_returns_success(self):
        assert ui_run({"product": "dashboard"})["status"] == "success"

    def test_has_data_and_meta(self):
        r = ui_run({"product": "x"})
        assert "data" in r
        assert "meta" in r

    def test_meta_skill_name(self):
        assert ui_run({})["meta"]["skill"] == "ui-ux"

    def test_invoke_alias(self):
        from core.skills.ui_ux.main import invoke
        assert invoke is ui_run


class TestUiUxWireframe:
    def test_default_task_returns_wireframe(self):
        r = ui_run({"product": "investor portal", "platform": "web"})
        assert "components" in r["data"]
        assert "layout" in r["data"]

    def test_dashboard_product_gets_dashboard_layout(self):
        r = ui_run({"product": "deal dashboard"})
        assert r["data"]["layout"] == "dashboard"

    def test_platform_components_are_platform_specific(self):
        r = ui_run({"product": "x", "platform": "ios"})
        components = r["data"]["components"]
        # iOS components should come from the iOS list
        assert any("UI" in c or "SwiftUI" in c for c in components)

    def test_web_platform_gives_web_components(self):
        r = ui_run({"product": "x", "platform": "web"})
        components = r["data"]["components"]
        assert any(c in ("navbar", "sidebar", "cards", "charts", "data-table", "modal", "toast")
                   for c in components)

    def test_spacing_unit_is_eight(self):
        r = ui_run({"product": "x"})
        assert r["data"]["spacing_unit"] == 8


class TestUiUxUserFlow:
    def test_flow_has_steps(self):
        r = ui_run({"product": "portal", "task": "flow"})
        assert len(r["data"]["steps"]) > 0

    def test_each_step_has_id_screen_action(self):
        r = ui_run({"product": "x", "task": "flow"})
        for step in r["data"]["steps"]:
            assert "id" in step
            assert "screen" in step
            assert "action" in step

    def test_entry_and_exit_points_defined(self):
        r = ui_run({"product": "x", "task": "flow"})
        assert "entry_point" in r["data"]
        assert "exit_point" in r["data"]


class TestUiUxComponentSpec:
    def test_component_spec_has_components(self):
        r = ui_run({"product": "x", "task": "component_spec"})
        assert len(r["data"]["components"]) > 0

    def test_each_component_has_name_type_props(self):
        r = ui_run({"product": "x", "task": "component_spec"})
        for comp in r["data"]["components"]:
            assert "name" in comp
            assert "type" in comp
            assert "props" in comp

    def test_design_tokens_present(self):
        r = ui_run({"product": "x", "task": "component_spec"})
        assert "design_tokens" in r["data"]


class TestUiUxDesignSystem:
    def test_minimal_style_returns_inter_font(self):
        r = ui_run({"product": "x", "task": "design_system", "style": "minimal"})
        assert r["data"]["typography"] == "Inter"

    def test_cupertino_style_returns_sf_pro(self):
        r = ui_run({"product": "x", "task": "design_system", "style": "cupertino"})
        assert r["data"]["typography"] == "SF Pro"

    def test_radius_is_numeric(self):
        r = ui_run({"product": "x", "task": "design_system"})
        assert isinstance(r["data"]["radius"], (int, float))


class TestUiUxAccessibilityAudit:
    def test_audit_returns_wcag_level(self):
        r = ui_run({"product": "x", "task": "accessibility_audit"})
        assert r["data"]["wcag_level"] == "AA"

    def test_audit_has_checks(self):
        r = ui_run({"product": "x", "task": "accessibility_audit"})
        assert len(r["data"]["checks"]) > 0

    def test_score_between_zero_and_one(self):
        r = ui_run({"product": "x", "task": "accessibility_audit"})
        assert 0.0 <= r["data"]["score"] <= 1.0


# ===========================================================================
# ios-testing skill
# ===========================================================================

class TestIosTestingContract:
    def test_returns_success(self):
        assert ios_run({"app": "SybilApp"})["status"] == "success"

    def test_has_data_and_meta(self):
        r = ios_run({"app": "x"})
        assert "data" in r
        assert "meta" in r

    def test_meta_skill_name(self):
        assert ios_run({})["meta"]["skill"] == "ios-testing"

    def test_invoke_alias(self):
        from core.skills.ios_testing.main import invoke
        assert invoke is ios_run


class TestIosGenerateTests:
    def test_default_task_generates_tests(self):
        r = ios_run({"app": "MyApp"})
        assert "tests" in r["data"]
        assert len(r["data"]["tests"]) > 0

    def test_test_code_is_string(self):
        r = ios_run({"app": "MyApp"})
        assert isinstance(r["data"]["test_code"], str)

    def test_test_code_contains_xctest_import(self):
        r = ios_run({"app": "MyApp"})
        assert "XCTest" in r["data"]["test_code"]

    def test_test_code_contains_target_class(self):
        r = ios_run({"app": "MyApp", "target": "SybilUITests"})
        assert "SybilUITests" in r["data"]["test_code"]

    def test_custom_test_cases_used(self):
        cases = [
            {"name": "testLogin", "assertion": "XCTAssertTrue(app.buttons['Login'].exists)"},
            {"name": "testLogout", "assertion": "XCTAssertTrue(app.buttons['Logout'].exists)"},
        ]
        r = ios_run({"app": "x", "test_cases": cases})
        assert "testLogin" in r["data"]["tests"]
        assert "testLogout" in r["data"]["tests"]

    def test_coverage_estimate_is_float(self):
        r = ios_run({"app": "x"})
        assert isinstance(r["data"]["coverage_estimate"], float)

    def test_meta_device_reflected(self):
        r = ios_run({"app": "x", "device": "iPhone 15 Pro"})
        assert r["meta"]["device"] == "iPhone 15 Pro"


class TestIosRunSimulation:
    def test_simulation_result_passes(self):
        r = ios_run({"app": "SybilApp", "task": "run_simulation"})
        assert r["data"]["passed"] == r["data"]["tests_run"]
        assert r["data"]["failed"] == 0

    def test_simulation_has_duration(self):
        r = ios_run({"app": "x", "task": "run_simulation"})
        assert r["data"]["duration_seconds"] > 0

    def test_simulation_reflects_device_and_os(self):
        r = ios_run({"app": "x", "task": "run_simulation", "device": "iPad Pro", "os_version": "17.5"})
        assert "iPad Pro" in r["data"]["device"]
        assert "17.5" in r["data"]["os"]


class TestIosUiValidation:
    def test_ui_validation_all_checks_pass(self):
        r = ios_run({"app": "SybilApp", "task": "ui_validation"})
        assert len(r["data"]["failed"]) == 0
        assert len(r["data"]["passed"]) == len(r["data"]["checks"])

    def test_accessibility_score_between_zero_and_one(self):
        r = ios_run({"app": "x", "task": "ui_validation"})
        assert 0.0 <= r["data"]["accessibility_score"] <= 1.0

    def test_result_string_present(self):
        r = ios_run({"app": "MyApp", "task": "ui_validation"})
        assert len(r["data"]["result"]) > 0


class TestIosPerformanceProfile:
    def test_perf_has_launch_time(self):
        r = ios_run({"app": "x", "task": "performance_profile"})
        assert r["data"]["launch_time_ms"] > 0

    def test_perf_has_memory_and_cpu(self):
        r = ios_run({"app": "x", "task": "performance_profile"})
        assert r["data"]["memory_mb"] > 0
        assert r["data"]["cpu_percent_peak"] > 0

    def test_fps_near_60(self):
        r = ios_run({"app": "x", "task": "performance_profile"})
        assert r["data"]["fps_average"] >= 55.0

    def test_thermal_state_nominal(self):
        r = ios_run({"app": "x", "task": "performance_profile"})
        assert r["data"]["thermal_state"] == "nominal"
