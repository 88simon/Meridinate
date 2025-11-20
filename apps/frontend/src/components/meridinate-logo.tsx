import React from 'react';

interface MeridianteLogoProps {
  className?: string;
  variant?: 'light' | 'dark';
}

export function MeridinateLogo({
  className = 'h-8 w-8',
  variant = 'light'
}: MeridianteLogoProps) {
  const strokeColor = variant === 'dark' ? '#fff' : 'currentColor';
  const fillColor = variant === 'dark' ? '#fff' : 'currentColor';

  return (
    <svg
      className={className}
      viewBox='0 0 100 100'
      xmlns='http://www.w3.org/2000/svg'
    >
      {/* Central circle */}
      <circle
        cx='50'
        cy='50'
        r='6'
        fill='none'
        stroke={strokeColor}
        strokeWidth='2'
      />

      {/* Ripple rings */}
      <circle
        cx='50'
        cy='50'
        r='14'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1'
        opacity='0.4'
      />
      <circle
        cx='50'
        cy='50'
        r='22'
        fill='none'
        stroke={strokeColor}
        strokeWidth='0.8'
        opacity='0.25'
      />

      {/* Vertical meridian line */}
      <line
        x1='50'
        y1='10'
        x2='50'
        y2='40'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />
      <line
        x1='50'
        y1='60'
        x2='50'
        y2='90'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />

      {/* Flowing curved meridian lines */}
      <path
        d='M 20 30 Q 35 40, 44 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />
      <path
        d='M 80 30 Q 65 40, 56 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />
      <path
        d='M 20 70 Q 35 60, 44 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />
      <path
        d='M 80 70 Q 65 60, 56 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />

      {/* Horizontal flowing line */}
      <path
        d='M 10 50 Q 25 50, 44 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />
      <path
        d='M 90 50 Q 75 50, 56 50'
        fill='none'
        stroke={strokeColor}
        strokeWidth='1.5'
        strokeLinecap='round'
      />

      {/* Small dots at meridian endpoints */}
      <circle cx='20' cy='30' r='2' fill={fillColor} />
      <circle cx='80' cy='30' r='2' fill={fillColor} />
      <circle cx='20' cy='70' r='2' fill={fillColor} />
      <circle cx='80' cy='70' r='2' fill={fillColor} />
      <circle cx='50' cy='10' r='2' fill={fillColor} />
      <circle cx='50' cy='90' r='2' fill={fillColor} />
      <circle cx='10' cy='50' r='2' fill={fillColor} />
      <circle cx='90' cy='50' r='2' fill={fillColor} />

      {/* Small bubbles in center (subtle liquid detail) */}
      <circle cx='46' cy='48' r='1' fill={fillColor} opacity='0.3' />
      <circle cx='54' cy='48' r='1' fill={fillColor} opacity='0.3' />
      <circle cx='50' cy='53' r='1' fill={fillColor} opacity='0.3' />
    </svg>
  );
}
