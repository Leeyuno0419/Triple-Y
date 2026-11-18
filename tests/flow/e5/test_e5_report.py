"""E5 테스트 경계: src.flow.e5.report의 CSV 읽기·쓰기·md·그림과 build_report.

실행기 CSV는 e5_helpers.write_runner_csvs가 Java와 같은 머리줄로 쓴
합성 파일이다. md는 9.2절 제목·기본 행 굵게·서버 확인 절(있음/없음)·
결정적 출력을 본다. write_report·main 시험(파일 쓰기·PNG)만
matplotlib가 필요해 그 시험 안에서 importorskip한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from e5_helpers import make_timeline, write_runner_csvs
from src.flow.e5 import report as e5_report
from src.flow.e5.analysis import build_report
from src.flow.e5.report import (
    ALERTS_COLUMNS, INFLOW_COLUMNS, INSTABILITY_COLUMNS, SUMMARY_COLUMNS,
    TICKS_COLUMNS, read_runner_csv, render_markdown, write_csv,
    write_report,
)

N_T = 40
SUMMARY = {"n_instability": "1", "n_grade_up": "1", "n_inflow": "1",
           "first_instability_t": "31", "first_grade_up_t": "32",
           "first_inflow_t": "12", "unstable_s": "3", "critical_s": "8",
           "inflow_on_s": "13"}
NO_ALERT = {**SUMMARY, "n_instability": "0", "n_grade_up": "0",
            "first_instability_t": None, "first_grade_up_t": None,
            "unstable_s": "0", "critical_s": "0"}


def report_timeline() -> dict:
    """40초, 셀 2개(4.0·1.5㎡). P는 t ≥ 29부터, t31~33은 0.03."""
    pressure = [[None, None] if t < 29 else [0.01, 0.5] for t in range(N_T)]
    for t in (31, 32, 33):
        pressure[t][0] = 0.03
    return make_timeline(
        areas=[4.0, 1.5], density=[[1.0, 1.0]] * N_T, pressure=pressure,
        inflow=[None] * 10 + [0.8] * 5 + [0.1] * 25,
        count=[1.0] * 30 + [float(t - 29) for t in range(30, N_T)],
    )


def runner_rows() -> tuple[list[dict], ...]:
    """실행기 CSV 네 종류의 합성 행 (값은 문자열)."""
    ticks = [{"t": str(t), "zone_grade": "NORMAL", "max_density": "1.0",
              "inflow_avg": "0.8" if 12 <= t <= 14 else None,
              "inflow_alert": "true" if 12 <= t <= 24 else "false",
              "n_unstable": "0", "unstable_cells": None, "events": None}
             for t in range(N_T)]
    alerts = [{"t": "12", "reason": "INFLOW", "level": "CAUTION",
               "value": "0.8", "cell_ids": None},
              {"t": "31", "reason": "INSTABILITY", "level": "CRITICAL",
               "value": "0.03", "cell_ids": "c-0000"}]
    instability = [
        {"pressure": "0.02", "seconds": "3", "is_default": "true",
         **SUMMARY},
        {"pressure": "0.04", "seconds": "3", "is_default": "false",
         **NO_ALERT},
    ]
    inflow = [
        {"ratio": "0.6", "window_seconds": "5", "min_samples": "3",
         "min_count": "3.0", "off_seconds": "10", "is_default": "true",
         **SUMMARY},
        {"ratio": "0.6", "window_seconds": "10", "min_samples": "6",
         "min_count": "3.0", "off_seconds": "10", "is_default": "false",
         **SUMMARY},
    ]
    return ticks, alerts, instability, inflow


def read_back(tmp_path: Path) -> tuple[list[dict], ...]:
    """합성 실행기 CSV를 쓰고 read_runner_csv로 다시 읽는다."""
    write_runner_csvs(tmp_path, "TEST_001", *runner_rows())
    return (
        read_runner_csv(tmp_path / "TEST_001_ticks.csv", TICKS_COLUMNS),
        read_runner_csv(tmp_path / "TEST_001_alerts.csv", ALERTS_COLUMNS),
        read_runner_csv(tmp_path / "TEST_001_sweep_instability.csv",
                        INSTABILITY_COLUMNS),
        read_runner_csv(tmp_path / "TEST_001_sweep_inflow.csv",
                        INFLOW_COLUMNS),
    )


def make_report(tmp_path: Path, server: list[dict] | None = None) -> dict:
    """합성 timeline과 합성 실행기 CSV로 만든 보고서 dict."""
    return build_report(report_timeline(), *read_back(tmp_path),
                        server_alerts=server)


def test_columns_match_java_headers() -> None:
    """Python 열 상수는 Java E5Sweep 머리줄 문자열과 같다 (9.1절 약속)."""
    assert ",".join(TICKS_COLUMNS) == (
        "t,zone_grade,max_density,inflow_avg,inflow_alert,n_unstable,"
        "unstable_cells,events")
    assert ",".join(ALERTS_COLUMNS) == "t,reason,level,value,cell_ids"
    assert ",".join(SUMMARY_COLUMNS) == (
        "n_instability,n_grade_up,n_inflow,first_instability_t,"
        "first_grade_up_t,first_inflow_t,unstable_s,critical_s,inflow_on_s")
    assert ",".join(INSTABILITY_COLUMNS) == (
        "pressure,seconds,is_default," + ",".join(SUMMARY_COLUMNS))
    assert ",".join(INFLOW_COLUMNS) == (
        "ratio,window_seconds,min_samples,min_count,off_seconds,is_default,"
        + ",".join(SUMMARY_COLUMNS))


def test_read_runner_csv_blank_is_none(tmp_path: Path) -> None:
    """값은 문자열 그대로, 빈칸은 None이다."""
    ticks, alerts, _, _ = read_back(tmp_path)
    assert len(ticks) == N_T
    assert ticks[12]["inflow_avg"] == "0.8"
    assert ticks[0]["inflow_avg"] is None
    assert alerts[0]["cell_ids"] is None
    assert alerts[1]["cell_ids"] == "c-0000"


def test_read_runner_csv_missing_column_raises(tmp_path: Path) -> None:
    """머리줄에 약속한 열이 없으면 ValueError (열 이름을 알려 준다)."""
    path = tmp_path / "x_alerts.csv"
    path.write_text("t,reason,level,value\n2,GRADE_UP,ALERT,4.1\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="cell_ids"):
        read_runner_csv(path, ALERTS_COLUMNS)


def test_write_csv_formats_values(tmp_path: Path) -> None:
    """첫 행 키가 머리줄, None은 빈칸, bool은 0/1, float는 repr."""
    path = tmp_path / "a.csv"
    write_csv(path, [{"t": 0, "x": None, "ok": True, "v": 0.1},
                     {"t": 1, "x": 2.5, "ok": False, "v": 1 / 3}])
    assert path.read_bytes().decode("utf-8") == (
        "t,x,ok,v\n0,,1,0.1\n1,2.5,0,0.3333333333333333\n")


def test_write_csv_without_rows_writes_empty_file(tmp_path: Path) -> None:
    """행이 없으면 머리줄 없이 빈 파일이다."""
    path = tmp_path / "empty.csv"
    write_csv(path, [])
    assert path.read_bytes() == b""


def test_build_report_keys_and_values(tmp_path: Path) -> None:
    """보고서 키 목록과 기본 행·사건 표·시계열 값."""
    report = make_report(tmp_path)
    assert set(report) == {
        "series", "cells", "quantiles", "peaks", "window",
        "recompute_check", "lag_rows", "best_lag", "events",
        "sweep_instability", "sweep_inflow", "default_instability",
        "default_inflow", "server_check", "meta", "cell_pressure",
        "inflow_avg",
    }
    assert list(report["cell_pressure"]) == ["c-0000"]  # 판정 대상만
    assert report["cell_pressure"]["c-0000"][31] == 0.03
    assert report["cell_pressure"]["c-0000"][0] is None
    assert report["inflow_avg"][12] == 0.8
    assert report["inflow_avg"][0] is None
    assert report["server_check"] is None
    assert report["default_instability"]["pressure"] == "0.02"
    assert report["default_inflow"]["window_seconds"] == "5"
    assert report["meta"] == {
        "video_id": "TEST_001", "duration_s": N_T,
        "models": {"counter": "fixture", "flow": "fixture",
                   "predictor": "none"},
        "n_cells": 2, "n_eligible": 1,
    }
    row = report["series"][31]
    assert set(row) == {"t", "count", "count_smooth", "count_rate",
                        "inflow_ratio", "zone_pressure", "n_pressure"}
    assert (row["t"], row["zone_pressure"], row["n_pressure"]) == (
        31, 0.03, 1)
    assert report["series"][0]["count_smooth"] is None  # 평활 창 밖
    assert report["series"][0]["zone_pressure"] is None
    assert all(r["t_in"] == 12 and r["t_alarm"] == 12
               for r in report["events"])
    assert [p[0] for p in report["peaks"]][0] == 31


def test_build_report_rejects_ticks_of_other_timeline(
    tmp_path: Path,
) -> None:
    """ticks 행의 t가 timeline 초와 다르면 ValueError (다른 파일)."""
    ticks, alerts, instability, inflow = read_back(tmp_path)
    with pytest.raises(ValueError, match="ticks"):
        build_report(report_timeline(), ticks[:-1], alerts, instability,
                     inflow)


def test_build_report_server_check(tmp_path: Path) -> None:
    """서버 알림이 있으면 실행기 alerts와 대조한 결과를 담는다."""
    server = [
        {"t": 12, "reason": "INFLOW", "level": "CAUTION", "value": 0.8,
         "cell_ids": [], "alert_id": "a-1"},
        {"t": 31, "reason": "INSTABILITY", "level": "CRITICAL",
         "value": 0.03, "cell_ids": ["c-0000"], "alert_id": "a-2"},
    ]
    assert make_report(tmp_path, server)["server_check"]["match"] is True


def test_render_markdown_sections_and_default_bold(tmp_path: Path) -> None:
    """9.2절 제목이 모두 있고 기본 설정 행은 굵게 표시된다."""
    md = render_markdown(make_report(tmp_path), "data/x/TEST_001.json")
    for title in (
        "# E5 TEST_001: 불안정 지표·기준값 민감도·유입 시간 차",
        "## 1. 불안정 지표 P 시계열", "## 2. 기준값 민감도",
        "### 2.1 불안정", "### 2.2 유입", "### 2.3 창 길이 T",
        "## 3. 유입 → 인원 증가 시간 차", "### 3.1 상호상관",
        "### 3.2 사건 기준", "## 4. 서버 확인", "## 5. 한계",
    ):
        assert title in md
    assert "| timeline | data/x/TEST_001.json |" in md
    window = md.split("### 2.3 창 길이 T")[1].split("## 3.")[0]
    assert "non-null 비율의 분모는 모든 t" in window
    assert "T=60" in window
    assert "| **0.02** | **3** |" in md
    assert "| 0.04 | 3 |" in md
    assert "정답 클립이 없어 감지 성능은 주장하지 않는다" in md


def test_render_markdown_server_section(tmp_path: Path) -> None:
    """서버 알림이 없으면 '하지 않음', 있으면 일치 여부와 다른 행."""
    no_server = render_markdown(make_report(tmp_path), "t.json")
    assert "하지 않음" in no_server.split("## 4. 서버 확인")[1]
    server = [{"t": 12, "reason": "INFLOW", "level": "CAUTION",
               "value": 0.8, "cell_ids": []}]
    md = render_markdown(make_report(tmp_path, server), "t.json")
    section = md.split("## 4. 서버 확인")[1].split("## 5.")[0]
    assert "| 1 | 2 | 아니오 |" in section
    assert "INSTABILITY" in section


def test_render_markdown_is_deterministic(tmp_path: Path) -> None:
    """같은 입력이면 같은 문자열이다."""
    first = render_markdown(make_report(tmp_path), "t.json")
    second = render_markdown(make_report(tmp_path), "t.json")
    assert first == second


D_FILES = ("TEST_001_e5.md", "TEST_001_series.csv", "TEST_001_window.csv",
           "TEST_001_lag.csv", "TEST_001_series.png", "TEST_001_sweep.png",
           "TEST_001_lag.png")


def report_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """합성 timeline 파일과 실행기 CSV 폴더. (timeline 경로, sweep 폴더)."""
    timeline_path = tmp_path / "TEST_001.json"
    timeline_path.write_text(json.dumps(report_timeline()), encoding="utf-8")
    sweep_dir = tmp_path / "sweep"
    write_runner_csvs(sweep_dir, "TEST_001", *runner_rows())
    return timeline_path, sweep_dir


def test_write_report_writes_all_files(tmp_path: Path) -> None:
    """9.1절 D 파일을 모두 쓰고, PNG는 PNG 머리로 시작한다."""
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = report_inputs(tmp_path)
    out_dir = tmp_path / "out"
    paths = write_report(timeline_path, sweep_dir, out_dir)
    assert sorted(p.name for p in paths) == sorted(D_FILES)
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(D_FILES)
    for name in D_FILES:
        if name.endswith(".png"):
            assert (out_dir / name).read_bytes().startswith(b"\x89PNG")
    series = (out_dir / "TEST_001_series.csv").read_text(encoding="utf-8")
    assert series.splitlines()[0] == (
        "t,count,count_smooth,count_rate,inflow_ratio,zone_pressure,"
        "n_pressure")
    assert (out_dir / "TEST_001_window.csv").read_text(
        encoding="utf-8").splitlines()[0] == (
        "window_s,nonnull_ratio,p95,over_ratio")
    assert (out_dir / "TEST_001_lag.csv").read_text(
        encoding="utf-8").splitlines()[0] == "lag_s,r,n_pairs"


def test_write_report_is_deterministic(tmp_path: Path) -> None:
    """두 번 쓰면 CSV·md 바이트가 같다."""
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = report_inputs(tmp_path)
    first, second = tmp_path / "a", tmp_path / "b"
    write_report(timeline_path, sweep_dir, first)
    write_report(timeline_path, sweep_dir, second)
    for name in D_FILES:
        if not name.endswith(".png"):
            assert (first / name).read_bytes() == (second / name).read_bytes()


def test_write_report_without_runner_csv_raises(tmp_path: Path) -> None:
    """실행기 CSV가 없으면 e5Sweep을 먼저 돌리라는 FileNotFoundError.

    그림을 그리기 전에 멈추므로 matplotlib가 없어도 돈다.
    """
    timeline_path, _ = report_inputs(tmp_path)
    with pytest.raises(FileNotFoundError, match="e5Sweep"):
        write_report(timeline_path, tmp_path / "empty", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_write_report_refuses_data_raw(tmp_path: Path) -> None:
    """출력 폴더가 data/raw 아래면 PermissionError, 아무것도 쓰지 않는다.

    그림을 그리기 전에 멈추므로 matplotlib가 없어도 돈다.
    """
    timeline_path, sweep_dir = report_inputs(tmp_path)
    with pytest.raises(PermissionError):
        write_report(timeline_path, sweep_dir, tmp_path / "data" / "raw")
    assert not (tmp_path / "data").exists()


def test_main_cli_with_server_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI: --sweep-dir 기본값은 --out, 서버 JSON을 주면 md 4절이 일치."""
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = report_inputs(tmp_path)
    server_path = tmp_path / "server_alerts.json"
    server_path.write_text(json.dumps([
        {"t": 12, "reason": "INFLOW", "level": "CAUTION", "value": 0.8,
         "cell_ids": [], "alert_id": "a-1"},
        {"t": 31, "reason": "INSTABILITY", "level": "CRITICAL",
         "value": 0.03, "cell_ids": ["c-0000"], "alert_id": "a-2"},
    ]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "report", "--timeline", str(timeline_path), "--server-alerts",
        str(server_path), "--out", str(sweep_dir)])
    e5_report.main()
    md = (sweep_dir / "TEST_001_e5.md").read_text(encoding="utf-8")
    section = md.split("## 4. 서버 확인")[1].split("## 5.")[0]
    assert "| 2 | 2 | 예 |" in section


def stem_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """파일 이름(TEST_001_limit3)이 video_id(TEST_001)와 다른 timeline과,
    Java처럼 파일 이름으로 쓴 실행기 CSV. (timeline 경로, sweep 폴더).
    """
    timeline_path = tmp_path / "TEST_001_limit3.json"
    timeline_path.write_text(json.dumps(report_timeline()), encoding="utf-8")
    sweep_dir = tmp_path / "sweep"
    write_runner_csvs(sweep_dir, "TEST_001_limit3", *runner_rows())
    return timeline_path, sweep_dir


def test_write_report_finds_csv_by_timeline_file_stem(tmp_path: Path) -> None:
    """실행기 CSV는 timeline 파일 이름(확장자 뺌)으로 찾는다 (E5Sweep과
    같은 규칙). video_id 이름 CSV가 없어도 된다.
    """
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = stem_inputs(tmp_path)
    write_report(timeline_path, sweep_dir, tmp_path / "out")
    assert (tmp_path / "out" / "TEST_001_e5.md").exists()


def test_write_report_ignores_stale_video_id_csv(tmp_path: Path) -> None:
    """같은 폴더의 옛 {video_id}_*.csv(다른 실행 결과)는 읽지 않는다."""
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = stem_inputs(tmp_path)
    ticks, alerts, instability, inflow = runner_rows()
    stale_alerts = [{**alerts[0], "t": "99"}]
    write_runner_csvs(sweep_dir, "TEST_001", ticks[:5], stale_alerts,
                      instability, inflow)  # 길이가 달라 읽으면 ValueError
    write_report(timeline_path, sweep_dir, tmp_path / "out")
    md = (tmp_path / "out" / "TEST_001_e5.md").read_text(encoding="utf-8")
    assert "| 99 |" not in md  # 옛 알림 초(t_alarm 99)가 보이지 않는다


def write_server_json(path: Path, value: object, encoding: str) -> None:
    """서버 알림 JSON을 주어진 인코딩으로 쓴다 (utf-8-sig면 BOM)."""
    path.write_text(json.dumps(value, ensure_ascii=False), encoding=encoding)


SERVER_OK = [
    {"t": 12, "reason": "INFLOW", "level": "CAUTION", "value": 0.8,
     "cell_ids": [], "alert_id": "a-1", "message": "구역으로 들어오는 인원"},
    {"t": 31, "reason": "INSTABILITY", "level": "CRITICAL", "value": 0.03,
     "cell_ids": ["c-0000"], "alert_id": "a-2", "message": "불안정"},
]


def test_write_report_reads_server_json_with_bom(tmp_path: Path) -> None:
    """PowerShell이 BOM을 붙여 저장한 서버 JSON도 읽는다."""
    pytest.importorskip("matplotlib")
    timeline_path, sweep_dir = report_inputs(tmp_path)
    server_path = tmp_path / "server_alerts.json"
    write_server_json(server_path, SERVER_OK, "utf-8-sig")
    assert server_path.read_bytes().startswith(b"\xef\xbb\xbf")
    write_report(timeline_path, sweep_dir, tmp_path / "out", server_path)
    md = (tmp_path / "out" / "TEST_001_e5.md").read_text(encoding="utf-8")
    assert "| 2 | 2 | 예 |" in md.split("## 4. 서버 확인")[1]


def test_write_report_rejects_server_json_not_list(tmp_path: Path) -> None:
    """서버 JSON 최상위가 목록이 아니면 ValueError, 아무것도 쓰지 않는다.

    그림을 그리기 전에 멈추므로 matplotlib가 없어도 돈다.
    """
    timeline_path, sweep_dir = report_inputs(tmp_path)
    server_path = tmp_path / "server_alerts.json"
    write_server_json(server_path, {"alerts": SERVER_OK}, "utf-8")
    with pytest.raises(ValueError, match="목록"):
        write_report(timeline_path, sweep_dir, tmp_path / "out",
                     server_path)
    assert not (tmp_path / "out").exists()
