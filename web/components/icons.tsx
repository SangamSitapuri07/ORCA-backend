import { ReactNode } from "react";

function Svg({ children, size = 18, className = "" }: { children: ReactNode; size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const IconWave = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M2 6c2.5 0 2.5 2 5 2s2.5-2 5-2 2.5 2 5 2 2.5-2 5-2" />
    <path d="M2 12c2.5 0 2.5 2 5 2s2.5-2 5-2 2.5 2 5 2 2.5-2 5-2" />
    <path d="M2 18c2.5 0 2.5 2 5 2s2.5-2 5-2 2.5 2 5 2 2.5-2 5-2" />
  </Svg>
);

export const IconMap = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M14.1 5.1 9 3 3.8 5.2a1 1 0 0 0-.8 1v14a1 1 0 0 0 1.4.9L9 19l6 2.2 5.2-2a1 1 0 0 0 .8-1v-14a1 1 0 0 0-1.4-.9L14.1 5.1Z" />
    <path d="M9 3v16" />
    <path d="M15 5.1v16" />
  </Svg>
);

export const IconChat = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.3c-1.4 0-2.8-.3-4-.9L3 20l1.2-4A7.9 7.9 0 0 1 3 11.5 8.4 8.4 0 0 1 11.5 3h1A8.4 8.4 0 0 1 21 11.5Z" />
    <path d="M8 10.5h.01M12 10.5h.01M16 10.5h.01" />
  </Svg>
);

export const IconShield = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M12 2.5 4.5 5.5v6c0 4.6 3.2 8.3 7.5 10 4.3-1.7 7.5-5.4 7.5-10v-6L12 2.5Z" />
    <path d="m9 11.8 2.2 2.2 4-4" />
  </Svg>
);

export const IconBell = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M18 9a6 6 0 1 0-12 0c0 6-2.5 7-2.5 7h17S18 15 18 9Z" />
    <path d="M10.2 20a2 2 0 0 0 3.6 0" />
  </Svg>
);

export const IconSettings = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.54V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.54-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.54V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.51 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.23.6.86 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1Z" />
  </Svg>
);

export const IconAnchor = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <circle cx="12" cy="5" r="2.5" />
    <path d="M12 7.5V22" />
    <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
  </Svg>
);

export const IconRefresh = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-2.6-6.4" />
    <path d="M21 3v6h-6" />
  </Svg>
);

export const IconCheck = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Svg>
);

export const IconSend = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="m3 11 18-8-8 18-2.5-7.5L3 11Z" />
  </Svg>
);

export const IconActivity = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="M22 12h-4l-3 8-6-16-3 8H2" />
  </Svg>
);

export const IconSatellite = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <path d="m13 7 4.5 4.5" />
    <path d="M16.5 3.5 21 8" />
    <rect x="8.5" y="8.5" width="7" height="7" rx="1" transform="rotate(45 12 12)" />
    <path d="m9 15-5.5 5.5" />
    <path d="m14 20-1.5-4L8 17.5" />
  </Svg>
);

export const IconGlobe = (p: { size?: number; className?: string }) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18Z" />
  </Svg>
);
