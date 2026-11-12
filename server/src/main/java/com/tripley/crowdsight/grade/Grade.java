package com.tripley.crowdsight.grade;

/**
 * 위험 등급 (api-spec 4.1, proposal 3.2). 선언 순서가 곧 등급 순서다.
 * compareTo·max·GradeHysteresis가 이 순서에 의존하므로 상수 순서를 바꾸지 않는다.
 * JSON에는 이름(NORMAL 등)으로 나간다 (S3). 화면 표기는 label이다.
 */
public enum Grade {
    NORMAL("정상"),
    CAUTION("주의"),
    ALERT("경계"),
    CRITICAL("심각");

    private static final Grade[] ALL = values();

    private final String label;

    Grade(String label) {
        this.label = label;
    }

    /** 화면 표기 (정상·주의·경계·심각). */
    public String label() {
        return label;
    }

    /** 한 단계 아래 등급. NORMAL은 그대로. */
    public Grade lower() {
        return this == NORMAL ? NORMAL : ALL[ordinal() - 1];
    }

    /** 둘 중 높은 등급. */
    public static Grade max(Grade a, Grade b) {
        return a.compareTo(b) >= 0 ? a : b;
    }
}
