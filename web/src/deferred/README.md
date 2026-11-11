# deferred — 보관 중인 지도 화면 코드

기획서 MVP 화면은 **영상 위 셀 히트맵 + 그래프 + 알림**이고, "지도·도로망"은 제외, "탑뷰·지도 표시"는 여유 시 3순위다
(`docs/proposal.md` 2절, `docs/server-alignment.md` Q1). 그래서 카카오맵 기반 화면을 이 폴더로 옮겨 두었다.

- `tsconfig.json`의 `exclude`에 들어 있어 **타입 검사·빌드 대상이 아니다.** 어디서도 import 하지 않는다.
- 이 코드는 옛 `Timeline` 모델(여러 구역, 위경도 `bounds`, `rows × cols` 격자, `predicted` 프레임)을 기준으로 쓰였다.
  `docs/timeline-spec.md` v0.1에는 위경도가 없고 셀이 `cell_id` 목록이라, 그대로는 컴파일되지 않는다.

## 되살리려면 (여유 시 기능 ③)
1. 규격에 셀·구역의 위경도(또는 카메라 호모그래피와 카메라 좌표)를 넣는다 (`docs/timeline-spec.md` v0.2, `server-alignment.md` Q9).
2. 이 폴더의 파일을 `src/components`, `src/lib`, `src/views`, `src/types`로 되돌리고 새 타입(`src/types/timeline.ts`)에 맞게 고친다.
3. `src/App.tsx`에 지도 탭과 검색·즐겨찾기 상태를 다시 연결하고, `tsconfig.json`의 `exclude`에서 이 폴더를 뺀다.
4. 카카오 JS 키(`VITE_KAKAO_JS_KEY`)와 도메인 등록이 필요하다. 설정 상수는 `src/config/app.ts`, `src/config/density.ts`에 남아 있다.

파일 이력은 `git mv`로 옮겼으므로 `git log --follow`로 원래 위치의 이력을 볼 수 있다.

| 폴더 | 파일 |
|---|---|
| `components/` | KakaoMap, DensityLayer, HeatmapLayer, DrawLayer, DrawToolbar, MapCenterTracker, MapFocus, MapModeToggle, MapPlace, RegionOutline, ZoneBounds, GridPreview, SearchBox, FavoritesMenu, CenterBadge, ZoneRankList |
| `views/` | MapView |
| `lib/` | customArea, favorites, useFavorites, geo, kakao, place, search, simulation, useRegionName, grid |
| `types/` | kakao.d.ts |
