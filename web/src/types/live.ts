/**
 * 서버 → 화면 WebSocket 메시지 타입 (docs/api-spec.md 3절, 초안 v0.2).
 * 메시지는 hello · zone_state · alert · playback 4종이고, 모르는 type 은 화면이 무시한다.
 */
import type { Frame, Meta } from './timeline';
import type { Grade } from './grade';

/** hello.thresholds: 표시용(범례·그래프 기준선). 판정은 서버가 한다. */
export interface Thresholds {
  density: { caution: number; alert: number; critical: number };
  pressure: number;
  inflow_ratio: number;
}

export type PlaybackState = 'playing' | 'ended';

export interface Playback {
  state: PlaybackState;
  /** 영상 시작 뒤 경과 초 */
  t: number;
  /** 끝나면 처음부터 반복하는가 */
  loop: boolean;
  /** hello 에만 있다 */
  duration_s: number | null;
}

/** 서버 알림 (3.3절). 같은 알림을 hello 와 alert 로 두 번 받을 수 있어 alert_id 로 거른다. */
export interface ServerAlert {
  /** a-yyyyMMdd-NNNN */
  alert_id: string;
  zone_id: string;
  /** 영상 시작 뒤 경과 초 */
  t: number;
  /** 서버가 보낸 시각(ISO 8601) */
  frame_ts: string;
  level: Grade;
  /** GRADE_UP | INFLOW | INSTABILITY (모르는 값도 그대로 받는다) */
  reason: string;
  message: string;
  /** GRADE_UP=최대 밀도, INFLOW=유입 비율 5초 평균, INSTABILITY=최대 pressure */
  value: number | null;
  cell_ids: string[];
}

/** 확인(ack) 요청 상태: idle=아직, pending=요청 중, error=실패(다시 누를 수 있다) */
export type AckState = 'idle' | 'pending' | 'error';

/** 화면에 보관하는 알림 = 서버 알림 + 확인 요청 상태 */
export interface LiveAlert extends ServerAlert {
  ack: AckState;
}

export interface HelloMessage {
  type: 'hello';
  /** API 메시지의 버전. 타임라인 파일의 schema_version 과 별개다. */
  schema_version: string;
  zone_id: string;
  meta: Meta;
  playback: Playback | null;
  thresholds: Thresholds | null;
  unacked_alerts: ServerAlert[];
}

export interface ZoneStateMessage {
  type: 'zone_state';
  zone_id: string;
  /**
   * 그 초의 프레임 후보. 셀 순서·필드는 meta 가 있어야 검증할 수 있어 applyLiveMessage 에서 검증한다.
   * 서버 판정값은 frame.cells[].grade·grade_pred_60s 와 frame.zone 에 담긴다.
   */
  frame: Omit<Frame, 'cells'> & { cells: unknown[] };
}

export interface AlertMessage {
  type: 'alert';
  alert: ServerAlert;
}

export interface PlaybackMessage {
  type: 'playback';
  zone_id: string;
  playback: Playback;
}

export type LiveMessage = HelloMessage | ZoneStateMessage | AlertMessage | PlaybackMessage;
