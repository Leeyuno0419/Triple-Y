package com.tripley.crowdsight.grade;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Iterator;

/**
 * 셀 하나의 등급 히스테리시스 (api-spec 4.2). 시작 등급은 NORMAL.
 * 올림: 최근 upSeconds개 관측이 모두 현재보다 높으면 그중 가장 낮은 등급으로 올린다. 기록은 비우지 않는다.
 * 내림: 최근 downSeconds개 관측이 모두 현재보다 낮으면 한 단계만 내리고 기록을 비운다.
 * null 관측은 세지 않는다. 등급을 유지하고 연속도 끊지 않는다 (결정 기록 4).
 * 올림·내림 조건은 둘 다 최신 관측을 포함하므로 동시에 참일 수 없다.
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class GradeHysteresis {

    private final int upSeconds;
    private final int downSeconds;
    private final int capacity;
    private final Deque<Grade> recent = new ArrayDeque<>();   // null이 아닌 관측, 마지막이 최신
    private Grade current = Grade.NORMAL;

    public GradeHysteresis(int upSeconds, int downSeconds) {
        if (upSeconds < 1 || downSeconds < 1) {
            throw new IllegalArgumentException(
                    "올림·내림 관측 수는 1 이상이어야 합니다: up=" + upSeconds + ", down=" + downSeconds);
        }
        this.upSeconds = upSeconds;
        this.downSeconds = downSeconds;
        this.capacity = Math.max(upSeconds, downSeconds);
    }

    /** 관측 1개를 반영하고 현재 등급을 돌려준다. observed가 null이면 아무것도 바꾸지 않는다. */
    public Grade update(Grade observed) {
        if (observed == null) {
            return current;
        }
        recent.addLast(observed);
        if (recent.size() > capacity) {
            recent.removeFirst();
        }
        if (recent.size() >= upSeconds) {
            Grade lowest = minOfLast(upSeconds);
            if (lowest.compareTo(current) > 0) {
                current = lowest;
                return current;
            }
        }
        if (recent.size() >= downSeconds && maxOfLast(downSeconds).compareTo(current) < 0) {
            current = current.lower();
            recent.clear();
        }
        return current;
    }

    /** 현재 등급. */
    public Grade current() {
        return current;
    }

    /** NORMAL로 되돌리고 기록을 비운다 (반복·이동). */
    public void reset() {
        current = Grade.NORMAL;
        recent.clear();
    }

    private Grade minOfLast(int n) {
        Grade min = Grade.CRITICAL;
        Iterator<Grade> it = recent.descendingIterator();
        for (int i = 0; i < n; i++) {
            Grade g = it.next();
            if (g.compareTo(min) < 0) {
                min = g;
            }
        }
        return min;
    }

    private Grade maxOfLast(int n) {
        Grade max = Grade.NORMAL;
        Iterator<Grade> it = recent.descendingIterator();
        for (int i = 0; i < n; i++) {
            max = Grade.max(max, it.next());
        }
        return max;
    }
}
