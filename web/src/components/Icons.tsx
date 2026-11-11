import type { ReactNode } from 'react';

/** 가벼운 선형 아이콘 모음 (24px 격자, currentColor). 외부 아이콘 패키지 없이 필요한 것만 둔다. */
function Icon({ children, size = 18, stroke = 2 }: { children: ReactNode; size?: number; stroke?: number }) {
  return (
    <svg
      viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const AlertIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 17h.01" />
  </Icon>
);
export const PulseIcon = (p: { size?: number }) => (
  <Icon {...p}><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></Icon>
);
export const UsersIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </Icon>
);
export const EyeIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
);
export const PinIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z" />
    <circle cx="12" cy="10" r="3" />
  </Icon>
);
export const ChevronIcon = (p: { size?: number }) => (
  <Icon {...p}><path d="m9 18 6-6-6-6" /></Icon>
);

export const HomeIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <path d="M9 22V12h6v10" />
  </Icon>
);
export const MapIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4z" />
    <path d="M8 2v16M16 6v16" />
  </Icon>
);
export const ChartIcon = (p: { size?: number }) => (
  <Icon {...p}><path d="M18 20V10M12 20V4M6 20v-6" /></Icon>
);
export const BellIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.7 21a2 2 0 0 1-3.4 0" />
  </Icon>
);
export const ArrowRightIcon = (p: { size?: number }) => (
  <Icon {...p}><path d="M5 12h14M12 5l7 7-7 7" /></Icon>
);
export const LayersIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="m12 2 10 5-10 5L2 7z" />
    <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
  </Icon>
);
export const SearchIcon = (p: { size?: number }) => (
  <Icon {...p} stroke={1.75}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </Icon>
);
export const RectIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <rect x="4" y="5" width="16" height="14" rx="1.5" strokeDasharray="3 2.5" />
  </Icon>
);
export const PolygonIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <path d="M12 3.5 20.5 9.7 17.3 19.5H6.7L3.5 9.7z" strokeDasharray="3 2.5" />
  </Icon>
);
export const StarIcon = (p: { size?: number }) => (
  <Icon {...p} stroke={1.8}>
    <path d="m12 2.8 2.8 5.8 6.4.9-4.6 4.5 1.1 6.3L12 17.3l-5.7 3 1.1-6.3-4.6-4.5 6.4-.9z" fill="currentColor" />
  </Icon>
);
export const FlameIcon = (p: { size?: number }) => (
  <Icon {...p} stroke={1.8}>
    <path d="M12 3c1 3.5 5 5.6 5 10a5 5 0 0 1-10 0c0-2 1-3.2 2-4.3.2 1.3.9 2 1.7 2.3C10.2 8.6 10.5 5.6 12 3z" />
  </Icon>
);
export const GridIcon = (p: { size?: number }) => (
  <Icon {...p} stroke={1.8}>
    <rect x="3.5" y="3.5" width="17" height="17" rx="2" />
    <path d="M3.5 9.2h17M3.5 14.8h17M9.2 3.5v17M14.8 3.5v17" />
  </Icon>
);
export const CircleIcon = (p: { size?: number }) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8" strokeDasharray="3 2.5" />
    <path d="M12 12h8" />
  </Icon>
);
