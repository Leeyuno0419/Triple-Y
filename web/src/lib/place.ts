import { loadKakaoSdk } from './kakao';

export interface PlaceHit {
  name: string;
  address: string;
  lat: number;
  lng: number;
}

/**
 * 카카오 장소 검색(Places 키워드 검색)으로 첫 번째 결과를 찾는다.
 * 결과가 없으면 null. SDK 로드나 검색 자체가 실패하면 Error.
 * (SDK 는 services 라이브러리를 포함해 로드한다 — lib/kakao.ts)
 */
export async function searchPlace(query: string, appKey: string): Promise<PlaceHit | null> {
  await loadKakaoSdk(appKey);
  const services = window.kakao?.maps.services;
  if (!services) throw new Error('카카오 장소 검색 라이브러리(services)를 불러오지 못했습니다.');

  return new Promise<PlaceHit | null>((resolve, reject) => {
    new services.Places().keywordSearch(query, (data, status) => {
      if (status === services.Status.OK && data.length > 0) {
        const first = data[0];
        resolve({ name: first.place_name, address: first.address_name, lat: Number(first.y), lng: Number(first.x) });
      } else if (status === services.Status.ZERO_RESULT) {
        resolve(null);
      } else {
        reject(new Error('장소 검색 중 오류가 발생했습니다.'));
      }
    });
  });
}

/**
 * 좌표의 행정구역 이름을 "서울 중구 정동 일대" 형태로 돌려준다. 찾지 못하면 null.
 * 카카오 좌표→행정구역 변환(Geocoder)을 쓰므로 랜드마크 이름이 아니라 행정동 단위다.
 */
export async function reverseRegion(lat: number, lng: number, appKey: string): Promise<string | null> {
  await loadKakaoSdk(appKey);
  const services = window.kakao?.maps.services;
  if (!services) throw new Error('카카오 라이브러리(services)를 불러오지 못했습니다.');

  return new Promise<string | null>((resolve) => {
    new services.Geocoder().coord2RegionCode(lng, lat, (result, status) => {
      if (status !== services.Status.OK || result.length === 0) return resolve(null);
      const r = result.find((x) => x.region_type === 'H') ?? result[0]; // H = 행정동
      const city = r.region_1depth_name.replace(/(특별자치시|특별자치도|특별시|광역시)$/, '').replace(/도$/, '');
      resolve(`${[city, r.region_2depth_name, r.region_3depth_name].filter(Boolean).join(' ')} 일대`);
    });
  });
}
