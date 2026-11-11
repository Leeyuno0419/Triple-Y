interface Props {
  values: number[];
  /** 지금 보고 있는 프레임 위치 */
  current: number;
  /** 예측 프레임이 시작되는 인덱스 (없으면 -1) */
  predictedFrom: number;
  label: string;
}

const W = 100;
const H = 32;

/** 최대 밀도 추이 미니 그래프. 예측 구간은 점선, 현재 위치는 세로선. */
export function Sparkline({ values, current, predictedFrom, label }: Props) {
  if (values.length < 2) return null;
  const maxV = Math.max(1, ...values);
  const x = (i: number) => (i / (values.length - 1)) * W;
  const y = (v: number) => H - 3 - (v / maxV) * (H - 8);
  const pts = (from: number, to: number) =>
    values.slice(from, to + 1).map((v, k) => `${x(from + k).toFixed(2)},${y(v).toFixed(2)}`).join(' ');

  const obsEnd = predictedFrom > 0 ? predictedFrom - 1 : values.length - 1;
  const area = `${x(0)},${H} ${pts(0, values.length - 1)} ${x(values.length - 1)},${H}`;

  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <polygon points={area} className="spark-area" />
      <polyline points={pts(0, obsEnd)} className="spark-line" />
      {predictedFrom > 0 && <polyline points={pts(predictedFrom - 1, values.length - 1)} className="spark-line pred" />}
      <line x1={x(current)} x2={x(current)} y1="0" y2={H} className="spark-now" />
    </svg>
  );
}
