package com.tripley.crowdsight;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * CrowdSight 서버 시작점.
 * 타임라인을 1초씩 재생해 등급을 판정하고, WebSocket·REST로 화면에 보낸다.
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class CrowdsightServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrowdsightServerApplication.class, args);
    }

}
